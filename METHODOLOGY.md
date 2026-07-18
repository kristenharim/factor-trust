# Methodology & assumption register

This is the repository copy of the app's `[5] methodology & assumptions` panel, kept in
sync by hand. The app text is the version users actually see; if the two disagree, the
app is what shipped and this file is the bug.

## What it is

A conditional simulator of PCA factor-direction error. Given (n, p, k), per-factor signal
strengths and a factor-return distribution, it Monte-Carlos the finite-p error
sin²∠(hⱼ, bⱼ) per factor, reports it in degrees as 50/80/95% bands, and marks the
observable floor ℓ/θⱼ separately.

PCA here means eigenvectors of the sample **covariance** matrix (not the correlation
matrix), and the "true direction" bⱼ is the corresponding population eigenvector of Σ.
If your shop runs PCA on correlations, the two problems differ by a per-asset rescaling
and these numbers do not transfer.

## What it is not

- **Not an estimator of total error from data alone.** The rotation component is provably
  not estimable (Gurdogan–Shkolnik impossibility). The fan is *simulated under assumptions*.
- **Not a confidence interval.** The bands are a conditional predictive distribution under
  an assumed data-generating process. No amount of simulation fidelity changes this.
- Not investment advice, and not a production risk tool.

## The simulator

Per path: Y = U·diag(√(pλ))·Φ + Z, with U orthonormal p×k and Z iid N(0, δ²). The n×n
dual Gram is simulated exactly without ever forming a p-dimensional array (Wishart via
Bartlett when p−k ≥ n, direct Gaussian block otherwise), so cost is O(n³) and independent
of p. See the `engine.py` module docstring for the exact construction.

Estimated and true directions are matched by the one-to-one permutation that maximizes
total absolute overlap; `swap%` is how often that assignment differs from the
population-strength rank label. **That matching uses the true directions** — information
no practitioner has on real data. Simulated named-factor accuracy is therefore optimistic
in a way the fan cannot show.

## What is exact, what is asymptotic, what is simulated

| quantity | status |
|---|---|
| sin²∠(hⱼ, bⱼ) per path | exact finite-p draw — no asymptotic shortcut |
| floor tick, spectrum mode | exact arithmetic on your eigenvalues (its own sampling noise is **not** shown) |
| floor tick, model mode | median of the simulated plug-in ℓ/θⱼ — an asymptotic floor, not a pathwise finite-p bound |
| gray asymptotic tick | closed-form limit arcsin√(δ²/(nλⱼ+δ²)) in the **p → ∞, n fixed** regime, derived under the model's own assumptions (in particular Gaussian idiosyncratic noise). Student-t factor returns change the simulated fan only; the formula is not re-derived for heavy tails |
| fan quantiles | empirical quantiles of simulated paths; q90 carries a 95% bootstrap interval for Monte Carlo estimation noise |
| swap% | Monte Carlo rate with a 95% Wilson interval; both intervals quantify simulation noise only |

## Tied factors: when a label stops being a label

PCA orders factors by sample eigenvalue. When two eigenvalues are close, that ordering is
not stable. At an *exact* tie it is an identification problem, not a precision problem:
any rotation within the shared plane is an equally valid eigenbasis, so only the span is
invariant.

When the estimator swaps two labels on more than the tie cutoff (default 5%, adjustable
in the app sidebar — **a display policy, not a theorem-derived threshold**), the app stops
leading with named directions and reports the **span**: the largest principal angle
between the true and estimated subspaces, arccos of the smallest singular value of BᵀH.
That statistic is invariant to eigenvector sign and to label swaps, which is exactly why
it survives a near-tie when the named rows do not.

**Claim boundary.** *Established:* at an exact tie only the joint span is invariant, and
the largest principal angle is what the engine simulates (checked against rotations of
known size). *Not established:* a theorem-backed floor for this statistic, a principled
switch threshold, or a span-level required-history target. Subspace mode is a conditional
diagnostic and a limitation flag, not a new theorem-backed output.

## Calibration sensitivity and circularity

Every output is conditional on the calibration, and in practice the calibration (vols,
prevalence, idiosyncratic vol) is estimated from the same returns one would PCA. The tool
cannot break that circularity; the app's `[3] calibration sensitivity` panel measures its
first-order size by scaling each input group ±10/15/20% one at a time and reporting the
envelope on q90 and floor, plus whether the tie verdict itself flips. One-at-a-time
scaling is a probe, not a joint error model.

## Required history is a model-implied scenario

The `[4]` sweep holds the calibration fixed while n varies: it answers "at what n does the
*simulated* q90 cross the target, if the calibration is right and stays right." It is not
a guarantee that collecting that much history achieves the target. The grid stops at
n = 252 by choice: the model holds loadings fixed for the whole window, so longer windows
would answer the question with the assumption least likely to survive them. Crossings are
only reported `[ok]` when the target clears the 95% Monte Carlo interval, not just the
point estimate.

## Assumptions register

| assumption | plausible violation | effect on the fan |
|---|---|---|
| random orthonormal true loadings | real sector/style structure | largest external-validity gap; direction configuration-dependent |
| loadings fixed across time | drift / regime change | live markets add error the fan omits → **fan optimistic** |
| iid observations | vol clustering, autocorrelation | effective n < nominal n → **fan optimistic** |
| Gaussian idiosyncratic noise | fat-tailed specific returns | untested hypothesis, not a proven-safe step |
| correct factor count k | ambiguous factor count in real markets | conflated factors; bias direction unclear |
| prevalence enters as diag(G_B) | correlated loadings | vol²·prev valid **only** when Σ_f and G_B share a diagonal basis |

Two of the three "fan optimistic" rows are unmitigated. The true error is more likely
above the bands than below them.

## Validation status

Cross-checked against a full p-dimensional reference engine (agreement <0.5° at p=500 and
p=3000) and against the paper's Figure 1; floors reproduce the closed form; simulated
totals sit above the floor as the theorem requires. Agreement between two engines is
implementation validation, not theorem validation, and **external validity is not
established**: the true loading direction is latent, so realized rotation cannot be
observed on real equity panels. Every number is internally consistent and externally
unproven.

Defaults are the paper's illustrative calibration (US equity, Bayraktar et al. 2014), not
fitted to any current book.
