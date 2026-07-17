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


def simulate(p, n, k, a, d2, dist="t", dof=6, reps=400, seed=SEED):
    """Monte Carlo the finite-p error. a = per-factor signal strengths (k,)."""
    a = np.asarray(a, dtype=float)
    rng = np.random.default_rng(seed)
    sin2 = np.empty((reps, k))
    obs = np.empty((reps, k))
    swaps = np.zeros(k)
    scale = np.sqrt(p * a)[:, None]
    sd = np.sqrt(d2)
    for r in range(reps):
        SE = scale * _phi(rng, k, n, dist, dof) + sd * rng.standard_normal((k, n))
        M = SE.T @ SE + _wishart(rng, n, p - k, d2)
        vals, vecs = np.linalg.eigh(M)
        top = np.argsort(vals)[::-1][:k]
        tv, W = vals[top], vecs[:, top]
        cosm = np.abs(SE @ W) / np.sqrt(tv)[None, :]      # cos(h_j, b_i) matrix (i,j)
        cjj = cosm[np.arange(k), np.arange(k)]
        sin2[r] = np.clip(1.0 - cjj**2, 0.0, 1.0)
        swaps += (np.argmax(cosm, axis=0) != np.arange(k))
        theta = tv / (n * p)
        ell = (np.trace(M) / (n * p) - theta.sum()) / (n - k)
        obs[r] = np.clip(ell / theta, 0.0, 1.0)
    deg = lambda s2: np.degrees(np.arcsin(np.sqrt(np.clip(s2, 0, 1))))
    ang = deg(sin2)
    return {
        "quantiles": {str(q): np.quantile(ang, q, axis=0).round(2).tolist() for q in QS},
        "mean": ang.mean(axis=0).round(2).tolist(),
        "floor_plugin_median": deg(np.median(obs, axis=0)).round(2).tolist(),
        "floor_asymptotic": deg(d2 / (n * a + d2)).round(2).tolist(),
        "snr": (n * a / d2).round(2).tolist(),
        "swap_rate": (swaps / reps).round(4).tolist(),
        "reps": reps, "p": p, "n": n, "k": k, "dist": dist, "dof": dof, "seed": seed,
    }


def sweep_n(p, n_grid, k, a, d2, dist="t", dof=6, reps=250, seed=SEED):
    """q50/q90 total-error angle per factor across observation counts."""
    out = {"n": list(n_grid), "q50": [], "q90": [], "floor": []}
    for n in n_grid:
        r = simulate(p, int(n), k, a, d2, dist, dof, reps, seed)
        out["q50"].append(r["quantiles"]["0.5"])
        out["q90"].append(r["quantiles"]["0.9"])
        out["floor"].append(r["floor_asymptotic"])
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
    print("engine self-check OK:", r["quantiles"]["0.5"], r["quantiles"]["0.9"],
          "swap:", r["swap_rate"])
