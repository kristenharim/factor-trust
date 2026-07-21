"""
Factor Trust engine: exact low-dimensional Monte Carlo for PCA direction error.

Model: Y = U diag(sqrt(p*a)) Phi + Z, U orthonormal p x k, Z iid N(0, d2).
Simulates the n x n dual Gram directly (no p-dimensional arrays):
  M = (S+E)^T (S+E) + C,   S = diag(sqrt(p*a)) Phi,  E = U^T Z ~ iid N(0,d2),
  C = Z_perp^T Z_perp ~ d2 * Wishart_n(I, p-k)   (independent of E; equality
  with Y^T Y holds in distribution).

Audit fixes (LLM council 2026-07-16, runtime/council/...4caebb31.md):
  - Wishart: Bartlett only when p-k >= n; otherwise sample the (p-k) x n
    Gaussian block directly (singular Wishart), so any p is handled correctly.
  - cos uses |.| explicitly.
  - swap-rate tracked with a one-to-one overlap-maximizing assignment: fraction
    of paths where h_j's assigned population label differs from rank j.
  - "a" = calibration signal strengths (inputs), distinct from the theorem's
    realized eigenvalues.

Validated against the historical full p-dimensional engine and the paper's
Figure 1 calibration; the repository's tests and CI protect the current contract.
"""
import itertools

import numpy as np

try:
    from scipy.linalg import eigh as _sp_eigh
except ImportError:      # numpy-only deployments (the vault's stdlib server)
    _sp_eigh = None

SEED = 20260716
QS = (0.025, 0.10, 0.25, 0.50, 0.75, 0.80, 0.90, 0.95, 0.975)
MC_BOOTSTRAP_REPS = 400


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


def validate_calibration(p, n, k, a, d2, reps=1):
    """Validate the ordered population-strength contract used by the engine.

    Factor j is a rank label, so strengths must be supplied from strongest to
    weakest. Equal adjacent strengths are allowed: they are the exact-tie case
    where individual population directions cease to be uniquely identified.
    """
    a = np.asarray(a, dtype=float)
    if not (isinstance(p, (int, np.integer)) and p >= k >= 1):
        raise ValueError("require integer dimensions p >= k >= 1")
    if not (isinstance(n, (int, np.integer)) and n > k):
        raise ValueError("require integer observation count n > k")
    if len(a) != k or not np.all(np.isfinite(a)) or np.any(a <= 0):
        raise ValueError(f"need {k} finite, positive factor strengths")
    if np.any(a[:-1] < a[1:]):
        raise ValueError(
            "factor strengths must be ordered strongest to weakest "
            "(vol² × prevalence must be non-increasing); equal values are allowed ties")
    if not np.isfinite(d2) or d2 <= 0:
        raise ValueError("idiosyncratic variance must be finite and positive")
    if not (isinstance(reps, (int, np.integer)) and reps >= 1):
        raise ValueError("simulation paths must be a positive integer")
    return a


def _best_permutation(cosm):
    """One-to-one true-factor assignment maximizing total absolute overlap."""
    k = cosm.shape[0]
    return np.asarray(max(
        itertools.permutations(range(k)),
        key=lambda perm: sum(cosm[perm[j], j] for j in range(k))), dtype=int)


def _q90_mc_interval(angles, seed, bootstrap_reps=MC_BOOTSTRAP_REPS):
    """Deterministic percentile-bootstrap interval for Monte Carlo q90 noise."""
    reps = angles.shape[0]
    rng = np.random.default_rng(seed ^ 0x5A17C0DE)
    take = rng.integers(0, reps, size=(bootstrap_reps, reps))
    boot = np.quantile(angles[take], 0.90, axis=1)
    lo, hi = np.quantile(boot, [0.025, 0.975], axis=0)
    return {
        "lower": lo.round(2).tolist(),
        "upper": hi.round(2).tolist(),
        "confidence": 0.95,
        "method": "percentile bootstrap over Monte Carlo paths",
        "bootstrap_reps": bootstrap_reps,
    }


def simulate(p, n, k, a, d2, dist="t", dof=6, reps=400, seed=SEED, return_paths=False):
    """Monte Carlo the finite-p error. a = per-factor signal strengths (k,).

    return_paths keeps the per-path angle and plug-in arrays instead of only
    their quantiles, for callers that need the raw distribution (histograms,
    paired violins, any bootstrap the engine does not already do).
    """
    a = validate_calibration(p, n, k, a, d2, reps)
    rng = np.random.default_rng(seed)
    sin2 = np.empty((reps, k))
    obs = np.empty((reps, k))
    rot = np.empty((reps, k))          # sin2 angle(w_hat_j, e_j), the rotation term
    rho = np.empty((reps, k))          # realized eigenvalues of D_hat, the theorem's rho_j
    swaps = np.zeros(k)
    conf = np.zeros((k, k))            # conf[i, j] = times h_j's best match was b_i
    gs = groups(k)
    subang = np.empty((reps, len(gs)))  # largest principal angle per group, radians
    idx = [np.ix_(S, S) for S in gs]
    scale = np.sqrt(p * a)[:, None]
    sd = np.sqrt(d2)
    for r in range(reps):
        # S is kept separate from S+E because D_hat is built from the factor part
        # alone. Same two draws in the same order as before, so the master stream
        # is unchanged and every previously published number still reproduces.
        S_only = scale * _phi(rng, k, n, dist, dof)
        SE = S_only + sd * rng.standard_normal((k, n))
        M = SE.T @ SE + _wishart(rng, n, p - k, d2)
        # D_hat = C^(1/2) (F'F/n) C^(1/2) is exactly S S' / (n p) here, so its
        # eigenvalues ARE rho_j and its eigenvectors are w_hat_j. The p divides
        # out of the eigenvectors (it scales every eigenvalue equally), which is
        # why the rotation term does not depend on p at all.
        rvals, W_d = np.linalg.eigh(S_only @ S_only.T / (n * p))
        rho[r] = rvals[::-1]
        rot[r] = np.clip(1.0 - np.diag(W_d[:, ::-1]) ** 2, 0.0, 1.0)
        tv, W = _top_k(M, k, n)
        # G[i, j] = <b_i, h_j>, signed. Keep the sign: |.| is right for a single
        # direction (eigenvector sign is arbitrary) but destroys the subspace
        # geometry, and svd(G) below needs the real inner products.
        G = (SE @ W) / np.sqrt(tv)[None, :]
        cosm = np.abs(G)                                  # cos(h_j, b_i) matrix (i,j)
        cjj = cosm[np.arange(k), np.arange(k)]
        sin2[r] = np.clip(1.0 - cjj**2, 0.0, 1.0)
        best = _best_permutation(cosm)
        swaps += (best != np.arange(k))
        conf[best, np.arange(k)] += 1
        # Principal angles between the true and estimated spans of each run:
        # arccos of the singular values of B_S^T H_S. Invariant to eigenvector
        # sign AND to label swaps (both are orthogonal factors that leave the
        # singular values alone), which is exactly why this survives a near-tie
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
    # Theorem (5) assembled pathwise: the floor is evaluated at each path's own
    # realized rho_j, not at the population strength a. Those differ at finite n
    # because D_hat's eigenvalues spread, and substituting a is a second (n -> inf)
    # limit on top of the p -> inf one. Assembling per path and taking one median
    # at the end is the element-wise comparison; medians of the two terms taken
    # separately do not add.
    floor_path = d2 / (n * rho + d2)
    pred_path = floor_path + (1.0 - floor_path) * rot
    out = {
        "quantiles": {str(q): np.quantile(ang, q, axis=0).round(2).tolist() for q in QS},
        "mean": ang.mean(axis=0).round(2).tolist(),
        "floor_plugin_median": deg(np.median(obs, axis=0)).round(2).tolist(),
        "floor_asymptotic": deg(d2 / (n * a + d2)).round(2).tolist(),
        # the same floor evaluated at realized rho instead of population a
        "floor_pathwise_median": deg(np.median(floor_path, axis=0)).round(2).tolist(),
        "rotation_median": np.median(rot, axis=0).round(4).tolist(),
        # median of the assembled theorem prediction; compare against quantiles 0.5
        "total_predicted_median": deg(np.median(pred_path, axis=0)).round(2).tolist(),
        "snr": (n * a / d2).round(2).tolist(),
        "q90_mc95": _q90_mc_interval(ang, seed),
        "swap_rate": (swaps / reps).round(4).tolist(),
        "confusion": (conf / reps).round(4).tolist(),
        # largest principal angle between the true and estimated span of each
        # contiguous factor run, the honest object when labels are unstable
        "subspace": {group_label(S): {
            "quantiles": {str(q): round(float(np.quantile(sub_deg[:, g], q)), 2) for q in QS},
            "mean": round(float(sub_deg[:, g].mean()), 2),
        } for g, S in enumerate(gs)},
        "reps": reps, "p": p, "n": n, "k": k, "dist": dist, "dof": dof, "seed": seed,
    }
    if return_paths:
        out["paths"] = {"angle": ang.tolist(), "plugin_floor": deg(obs).tolist()}
    return out


def sweep_n(p, n_grid, k, a, d2, dist="t", dof=6, reps=250, seed=SEED, on_point=None):
    """q50/q90 total-error angle per factor across observation counts.

    on_point(done, total, n) fires after each grid point. Cost is O(n^3) per
    path, so the grid's largest n dominates the whole sweep, and callers driving a
    progress bar should expect wildly uneven step times.
    """
    out = {"n": list(n_grid), "q50": [], "q90": [], "q90_mc95": [], "floor": []}
    for i, n in enumerate(out["n"]):
        r = simulate(p, int(n), k, a, d2, dist, dof, reps, seed)
        out["q50"].append(r["quantiles"]["0.5"])
        out["q90"].append(r["quantiles"]["0.9"])
        out["q90_mc95"].append(r["q90_mc95"])
        out["floor"].append(r["floor_asymptotic"])
        if on_point:
            on_point(i + 1, len(out["n"]), int(n))
    return out


def sweep_p(p_grid, n, k, a, d2, dist="t", dof=6, reps=250, seed=SEED, on_point=None,
            keep_paths=0):
    """q10/q50/q90 total-error angle per factor across asset counts, n held fixed.

    The point of the sweep is that the curves flatten: the floor is a p -> inf,
    fixed-n statement, so growing p buys nothing once the curve has settled. Cheap
    to run because the dual-Gram construction is O(n^3) and independent of p, so
    p = 100,000 costs exactly what p = 100 costs — unlike sweep_n, every grid point
    here takes the same time.

    keep_paths keeps that many individual path angles per grid point, for drawing
    the spread behind the quantiles. They are NOT a path followed across p: each
    grid point is its own simulate() call and the Wishart block consumes a
    different number of variates at each p, so the streams diverge immediately.
    Draw them as points, never joined up, or the picture claims a continuity the
    simulation does not have.
    """
    out = {"p": list(p_grid), "q10": [], "q50": [], "q90": [], "paths": [],
           "floor": deg_of(d2 / (n * np.asarray(a, dtype=float) + d2))}
    for i, pp in enumerate(out["p"]):
        r = simulate(int(pp), n, k, a, d2, dist, dof, reps, seed,
                     return_paths=bool(keep_paths))
        out["q10"].append(r["quantiles"]["0.1"])
        out["q50"].append(r["quantiles"]["0.5"])
        out["q90"].append(r["quantiles"]["0.9"])
        if keep_paths:
            out["paths"].append(r["paths"]["angle"][:keep_paths])
        if on_point:
            on_point(i + 1, len(out["p"]), int(pp))
    return out


def deg_of(sin2_values):
    """sin2 -> degrees, as a plain list. The engine speaks degrees on the way out."""
    s = np.clip(np.asarray(sin2_values, dtype=float), 0.0, 1.0)
    return np.degrees(np.arcsin(np.sqrt(s))).round(2).tolist()


def from_spectrum(eigs, n, k, bulk_mean=None, bulk_count=None):
    """Spectrum-matched plug-in calibration (NOT an exact inversion: theta and
    ell carry sampling noise; different models can share a spectrum).
    Returns implied per-factor strengths with d2 normalized to 1, plus the
    directly-measured plug-in floors."""
    raw = np.asarray(eigs, dtype=float)
    if raw.ndim != 1 or not np.all(np.isfinite(raw)) or np.any(raw <= 0):
        raise ValueError("eigenvalues must all be finite and strictly positive")
    if bulk_mean is None:
        if len(raw) != n:
            raise ValueError(
                f"complete-spectrum mode requires exactly n={n} positive eigenvalues; "
                f"got {len(raw)}. Use the explicit bulk-summary mode for θ₁…θₖ plus ℓ.")
        e = np.sort(raw)[::-1]
        theta, bulk = e[:k], e[k:]
        ell, bulk_count = float(bulk.mean()), len(bulk)
        source = "complete spectrum"
    else:
        if len(raw) != k:
            raise ValueError(f"bulk-summary mode requires exactly k={k} top eigenvalues")
        theta = np.sort(raw)[::-1]
        ell = float(bulk_mean)
        if not np.isfinite(ell) or ell <= 0:
            raise ValueError("bulk mean ℓ must be finite and strictly positive")
        if bulk_count != n - k:
            raise ValueError(
                f"bulk count must be n-k={n-k}; got {bulk_count}. "
                "Use the mean of every remaining eigenvalue, not a selected tail.")
        source = "top-k plus explicit bulk summary"
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
        "bulk_count": int(bulk_count), "spectrum_source": source,
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
    if _sp is not None:
        assert _sp_eigh is not None, "scipy path should be restored when installed"

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
    # its off-diagonal mass is the one-to-one label mismatch rate, by construction
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

    # --- theorem (5), assembled pathwise ------------------------------------
    # The decomposition is the whole result, so check it rather than assume it:
    # floor + (1-floor)*rotation, built per path from D_hat, must land on the
    # separately-simulated total. Both are medians of the same 800 paths.
    meas = np.array(r["quantiles"]["0.5"])
    pred = np.array(r["total_predicted_median"])
    assert np.all(np.abs(meas - pred) < 1.0), (meas, pred)
    # ...and it must beat the same prediction with the population strength a
    # substituted for realized rho, which is the extra n -> inf limit. If this
    # ever fails, the pathwise floor has stopped being the better tick and the
    # readout column claiming so is wrong.
    fa = 0.16 / (63 * np.array(a) + 0.16)
    pop = np.degrees(np.arcsin(np.sqrt(fa + (1 - fa) * np.array(r["rotation_median"]))))
    assert np.all(np.abs(meas - pred) <= np.abs(meas - pop)), (meas, pred, pop)

    # raw paths are opt-in and shaped (reps, k)
    rp = simulate(500, 20, 2, a[:2], 0.16, "normal", reps=7, return_paths=True)
    assert "paths" not in simulate(500, 20, 2, a[:2], 0.16, "normal", reps=7)
    assert np.array(rp["paths"]["angle"]).shape == (7, 2), rp["paths"]["angle"]
    assert np.array(rp["paths"]["plugin_floor"]).shape == (7, 2)
    # 0.005 not 0 because the quantiles ship rounded to 2dp and the paths do not
    assert abs(np.median(rp["paths"]["angle"], axis=0)[0]
               - rp["quantiles"]["0.5"][0]) < 5e-3, "paths must match the quantiles"

    # sweep_p: same callback contract as sweep_n, and the floor does not move with p
    seen_p = []
    swp = sweep_p([300, 30_000], 63, 2, a[:2], 0.16, "normal", reps=40,
                  on_point=lambda done, total, pp: seen_p.append((done, total, pp)),
                  keep_paths=6)
    assert seen_p == [(1, 2, 300), (2, 2, 30_000)], seen_p
    assert swp["p"] == [300, 30_000] and len(swp["floor"]) == 2, swp
    # a hundredfold more assets must not move the curve by much once it has settled
    assert abs(swp["q50"][0][0] - swp["q50"][1][0]) < 3.0, swp["q50"]
    # the band must actually bracket the median at every grid point
    for lo, mid, hi in zip(swp["q10"], swp["q50"], swp["q90"]):
        assert all(l <= m <= h for l, m, h in zip(lo, mid, hi)), (lo, mid, hi)
    assert np.array(swp["paths"]).shape == (2, 6, 2), np.array(swp["paths"]).shape
    assert not sweep_p([300], 63, 2, a[:2], 0.16, "normal", reps=5)["paths"]
    print("engine self-check OK:", r["quantiles"]["0.5"], r["quantiles"]["0.9"],
          "swap:", r["swap_rate"])
