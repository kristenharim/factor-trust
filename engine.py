"""
Factor Trust engine — exact low-dimensional Monte Carlo for PCA direction error.

Model: Y = U diag(sqrt(p*a)) Phi + Z, U orthonormal p x k, Z iid N(0, d2).
Simulates the n x n dual Gram directly (no p-dimensional arrays):
  M = (S+E)^T (S+E) + C,   S = diag(sqrt(p*a)) Phi,  E = U^T Z ~ iid N(0,d2),
  C = Z_perp^T Z_perp ~ d2 * Wishart_n(I, p-k)   (independent of E; equality
  with Y^T Y holds in distribution).

Audit fixes (LLM council 2026-07-16, runtime/council/...4caebb31.md):
  - Wishart: Bartlett only when p-k >= n; otherwise sample the (p-k) x n
    Gaussian block directly (singular Wishart), so any p is handled correctly.
  - cos uses |.| explicitly.
  - swap-rate tracked: fraction of paths where h_j is closer to some b_i, i != j.
  - "a" = calibration signal strengths (inputs), distinct from the theorem's
    realized eigenvalues.

Validated against pca_factor_trust.py (full p-dim engine) and the paper's
Figure 1 calibration; see validate_lowdim.py one directory up.
"""
import numpy as np

try:
    from scipy.linalg import eigh as _sp_eigh
except ImportError:      # numpy-only deployments (the vault's stdlib server)
    _sp_eigh = None

SEED = 20260716
QS = (0.025, 0.10, 0.25, 0.50, 0.75, 0.80, 0.90, 0.95, 0.975)


def _phi(rng, k, n, dist, dof):
    if dist == "normal":
        return rng.standard_normal((k, n))
    t = rng.standard_t(dof, size=(k, n))
    return t / np.sqrt(dof / (dof - 2.0))


def _wishart(rng, n, m, d2):
    """d2 * W_n(I, m). Bartlett when m >= n, direct Gaussian block otherwise."""
    if m >= n:
        T = np.zeros((n, n))
        idx = np.tril_indices(n, -1)
        T[idx] = rng.standard_normal(len(idx[0]))
        T[np.diag_indices(n)] = np.sqrt(rng.gamma((m - np.arange(n)) / 2.0, 2.0))
        return d2 * (T @ T.T)
    G = rng.standard_normal((m, n))
    return d2 * (G.T @ G)


def _top_k(M, k, n):
    """Top-k eigenpairs of symmetric M, descending.

    simulate() only ever uses the top k and the trace, so ask LAPACK for k of
    them rather than all n (~1.6x on the sweep). scipy is optional: this module
    is also served by a numpy-only stdlib app, and the two paths are asserted
    identical in the self-check."""
    if _sp_eigh is not None:
        tv, W = _sp_eigh(M, subset_by_index=[n - k, n - 1], driver="evr")
        return tv[::-1], W[:, ::-1]
    vals, vecs = np.linalg.eigh(M)
    top = np.argsort(vals)[::-1][:k]
    return vals[top], vecs[:, top]


def groups(k):
    """Contiguous factor runs of length >= 2, as 0-based index tuples.

    Contiguous only: near-degeneracy happens between adjacent eigenvalues, so a
    tie between f1 and f3 that skips f2 is not a thing the ranking can produce."""
    return [tuple(range(i, j + 1)) for i in range(k) for j in range(i + 1, k)]


def group_label(S):
    """(1, 2) -> 'f2+f3'. The key the app looks a subspace result up by."""
    return "+".join(f"f{j + 1}" for j in S)


def simulate(p, n, k, a, d2, dist="t", dof=6, reps=400, seed=SEED):
    """Monte Carlo the finite-p error. a = per-factor signal strengths (k,)."""
    a = np.asarray(a, dtype=float)
    rng = np.random.default_rng(seed)
    sin2 = np.empty((reps, k))
    obs = np.empty((reps, k))
    swaps = np.zeros(k)
    conf = np.zeros((k, k))            # conf[i, j] = times h_j's best match was b_i
    gs = groups(k)
    subang = np.empty((reps, len(gs)))  # largest principal angle per group, radians
    idx = [np.ix_(S, S) for S in gs]
    scale = np.sqrt(p * a)[:, None]
    sd = np.sqrt(d2)
    for r in range(reps):
        SE = scale * _phi(rng, k, n, dist, dof) + sd * rng.standard_normal((k, n))
        M = SE.T @ SE + _wishart(rng, n, p - k, d2)
        tv, W = _top_k(M, k, n)
        # G[i, j] = <b_i, h_j>, signed. Keep the sign: |.| is right for a single
        # direction (eigenvector sign is arbitrary) but destroys the subspace
        # geometry, and svd(G) below needs the real inner products.
        G = (SE @ W) / np.sqrt(tv)[None, :]
        cosm = np.abs(G)                                  # cos(h_j, b_i) matrix (i,j)
        cjj = cosm[np.arange(k), np.arange(k)]
        sin2[r] = np.clip(1.0 - cjj**2, 0.0, 1.0)
        best = np.argmax(cosm, axis=0)
        swaps += (best != np.arange(k))
        conf[best, np.arange(k)] += 1
        # Principal angles between the true and estimated spans of each run:
        # arccos of the singular values of B_S^T H_S. Invariant to eigenvector
        # sign AND to label swaps (both are orthogonal factors that leave the
        # singular values alone) — which is exactly why this survives a near-tie
        # when the per-factor numbers above do not. Cost is an SVD of a <=4x4,
        # nothing next to the n x n eigendecomposition.
        for g, ix in enumerate(idx):
            sv = np.linalg.svd(G[ix], compute_uv=False)
            subang[r, g] = np.arccos(np.clip(sv, 0.0, 1.0)).max()
        theta = tv / (n * p)
        ell = (np.trace(M) / (n * p) - theta.sum()) / (n - k)
        obs[r] = np.clip(ell / theta, 0.0, 1.0)
    deg = lambda s2: np.degrees(np.arcsin(np.sqrt(np.clip(s2, 0, 1))))
    ang = deg(sin2)
    sub_deg = np.degrees(subang)
    return {
        "quantiles": {str(q): np.quantile(ang, q, axis=0).round(2).tolist() for q in QS},
        "mean": ang.mean(axis=0).round(2).tolist(),
        "floor_plugin_median": deg(np.median(obs, axis=0)).round(2).tolist(),
        "floor_asymptotic": deg(d2 / (n * a + d2)).round(2).tolist(),
        "snr": (n * a / d2).round(2).tolist(),
        "swap_rate": (swaps / reps).round(4).tolist(),
        "confusion": (conf / reps).round(4).tolist(),
        # largest principal angle between the true and estimated span of each
        # contiguous factor run — the honest object when labels are unstable
        "subspace": {group_label(S): {
            "quantiles": {str(q): round(float(np.quantile(sub_deg[:, g], q)), 2) for q in QS},
            "mean": round(float(sub_deg[:, g].mean()), 2),
        } for g, S in enumerate(gs)},
        "reps": reps, "p": p, "n": n, "k": k, "dist": dist, "dof": dof, "seed": seed,
    }


def sweep_n(p, n_grid, k, a, d2, dist="t", dof=6, reps=250, seed=SEED, on_point=None):
    """q50/q90 total-error angle per factor across observation counts.

    on_point(done, total, n) fires after each grid point. Cost is O(n^3) per
    path, so the grid's largest n dominates the whole sweep — callers driving a
    progress bar should expect wildly uneven step times.
    """
    out = {"n": list(n_grid), "q50": [], "q90": [], "floor": []}
    for i, n in enumerate(out["n"]):
        r = simulate(p, int(n), k, a, d2, dist, dof, reps, seed)
        out["q50"].append(r["quantiles"]["0.5"])
        out["q90"].append(r["quantiles"]["0.9"])
        out["floor"].append(r["floor_asymptotic"])
        if on_point:
            on_point(i + 1, len(out["n"]), int(n))
    return out


def from_spectrum(eigs, n, k):
    """Spectrum-matched plug-in calibration (NOT an exact inversion: theta and
    ell carry sampling noise; different models can share a spectrum).
    Returns implied per-factor strengths with d2 normalized to 1, plus the
    directly-measured plug-in floors."""
    e = np.sort(np.asarray([x for x in eigs if x > 0], dtype=float))[::-1]
    if len(e) < k + 2:
        raise ValueError(f"need at least k+2={k+2} positive eigenvalues, got {len(e)}")
    theta, ell = e[:k], e[k:].mean()
    if theta[-1] <= ell:
        raise ValueError(
            f"top-{k} eigenvalue ({theta[-1]:.4g}) is not above the bulk average "
            f"({ell:.4g}) - factor {k} not detectable; reduce k")
    snr = theta / ell - 1.0
    deg = lambda s2: float(np.degrees(np.arcsin(np.sqrt(np.clip(s2, 0, 1)))))
    return {
        "a": (snr / n).tolist(), "d2": 1.0,
        "snr": snr.round(2).tolist(),
        "floor_measured": [round(deg(ell / t), 2) for t in theta],
        "theta": theta.tolist(), "ell": float(ell),
    }


if __name__ == "__main__":
    # self-check vs Python reference (validate_lowdim.py, 2000 reps):
    # f1 q50/q90 = 16.7/19.8, f2 = 34.9/46.4, f3 = 44.1/51.6
    a = [0.16**2 * 1.25, 0.08**2, 0.06**2]
    r = simulate(3000, 63, 3, a, 0.16, "t", 6, reps=800)
    ref = {"q50": [16.7, 34.9, 44.1], "q90": [19.8, 46.4, 51.6]}
    for qk, tol in (("0.5", 1.5), ("0.9", 3.0)):
        got = r["quantiles"][qk]
        want = ref["q50" if qk == "0.5" else "q90"]
        for g, w in zip(got, want):
            assert abs(g - w) < tol, f"q{qk}: {got} vs {want}"
    # small-p regime must not crash (p-k < n path)
    simulate(40, 63, 3, a, 0.16, "normal", reps=20)

    # the scipy and numpy-only eigen paths must agree, or the vault's numpy-only
    # server quietly computes something different from the deployed app
    _M = np.array([[4.0, 1.0, 0.2], [1.0, 3.0, 0.1], [0.2, 0.1, 1.0]])
    _sp = _sp_eigh
    tv_a, W_a = _top_k(_M, 2, 3)
    globals()["_sp_eigh"] = None
    tv_b, W_b = _top_k(_M, 2, 3)
    globals()["_sp_eigh"] = _sp
    assert np.allclose(tv_a, tv_b), (tv_a, tv_b)
    assert np.allclose(np.abs((W_a * W_b).sum(axis=0)), 1.0), "eigenvectors disagree"
    assert _sp_eigh is not None, "scipy path should be live here"

    # --- subspace geometry -------------------------------------------------
    assert groups(3) == [(0, 1), (0, 1, 2), (1, 2)], groups(3)
    assert group_label((1, 2)) == "f2+f3"
    # A span is known at least as well as its worst member: the largest principal
    # angle of a run cannot exceed the worst per-factor angle in it, and for the
    # near-tied f2+f3 pair it should be strictly better (that is the whole point).
    q90 = r["quantiles"]["0.9"]
    sub = r["subspace"]
    assert sub["f2+f3"]["quantiles"]["0.9"] <= max(q90[1], q90[2]) + 1e-9, sub
    assert sub["f1+f2+f3"]["quantiles"]["0.9"] <= max(q90) + 1e-9, sub
    # each column of confusion is a distribution over "which true factor did h_j
    # hit" (atol covers the 4dp rounding on the way out, not real slack)
    conf = np.array(r["confusion"])
    assert np.allclose(conf.sum(axis=0), 1.0, atol=2e-4), conf
    # its off-diagonal mass is the swap rate, by construction
    assert np.allclose(1.0 - np.diag(conf), r["swap_rate"], atol=2e-4)
    # principal angles must be recovered exactly for a rotation of known size
    rng_t = np.random.default_rng(11)
    Q, _ = np.linalg.qr(rng_t.standard_normal((400, 6)))
    B, C = Q[:, :3], Q[:, 3:]
    known = np.radians([4.0, 25.0, 61.0])
    G_t = B.T @ (B * np.cos(known) + C * np.sin(known))
    got_ang = np.degrees(np.arccos(np.clip(np.linalg.svd(G_t, compute_uv=False), 0, 1)))
    assert np.allclose(np.sort(got_ang), np.degrees(np.sort(known))), got_ang
    # ...and be blind to eigenvector sign and to label swaps, which is what makes
    # them survive a near-tie when the named directions do not
    for perturbed in (G_t * np.array([1, -1, 1]), G_t[:, [0, 2, 1]]):
        assert np.allclose(np.sort(np.linalg.svd(perturbed, compute_uv=False)),
                           np.sort(np.linalg.svd(G_t, compute_uv=False))), "not invariant"
    # sweep reports every grid point, in order, exactly once (drives the app's progress bar)
    seen = []
    sw = sweep_n(200, [10, 12], 2, a[:2], 0.16, "normal", reps=5,
                 on_point=lambda done, total, nn: seen.append((done, total, nn)))
    assert seen == [(1, 2, 10), (2, 2, 12)], seen
    assert sw["n"] == [10, 12] and len(sw["q90"]) == 2, sw["n"]
    print("engine self-check OK:", r["quantiles"]["0.5"], r["quantiles"]["0.9"],
          "swap:", r["swap_rate"])
