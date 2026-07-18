# Factor Trust

Factor Trust is a research prototype for examining how much confidence a practitioner should place in PCA-estimated factor directions when the number of assets is large relative to the number of observations.

Live prototype: https://pca-factor-trust.streamlit.app/

## What it does

Given a factor-model calibration or sample spectrum, Factor Trust reports:

- an observable asymptotic floor derived from the sample eigenvalues;
- a conditional Monte Carlo distribution of total direction error;
- the implied residual directional variance after an idealized hedge;
- warnings when adjacent factor identities are unstable;
- a calibration-sensitivity panel: the envelope on q90 and floor when each input group is scaled ±10/15/20%, and whether the tie verdict itself flips;
- required-history results for stable named factors, framed as a model-implied scenario;
- Monte Carlo uncertainty on reported q90 values and swap rates (bootstrap and Wilson intervals).

It is a challenge and decision-boundary instrument—not a production risk model or an estimator of latent realized error.

## Claim boundary

Three kinds of output must remain separate.

### Observable under the model

The ratio ℓ/θⱼ estimates an asymptotic lower bound on factor-direction error, where θⱼ is a leading sample eigenvalue and ℓ is the average bulk eigenvalue.

At finite `(n, p)`, this plug-in value has sampling noise. It is not a pathwise guarantee.

### Conditional simulation

The error fan and its quantiles are Monte Carlo outputs under the selected factor-return distribution and the model assumptions below.

The q90 bootstrap interval and the swap-rate Wilson interval measure only numerical uncertainty from using finitely many simulation paths. Neither is a confidence interval for real-market error.

Every output is also conditional on the calibration itself — which, in practice, is estimated from the same returns one would PCA. The tool cannot break that circularity; the sensitivity panel measures its first-order size.

### Not identifiable

Total direction error and the realized in-subspace rotation component cannot be recovered from returns data alone.

For exact eigenvalue ties, individual directions are not uniquely identified; only their joint span is invariant. The current span output is a conditional largest-principal-angle simulation. No theorem-backed span floor or required-history target is claimed.

## Inputs

### Model calibration

- observations `n`
- assets `p`
- factors `k`
- factor volatility
- factor prevalence
- idiosyncratic volatility
- factor-return distribution
- simulation paths

Factor strengths must be ordered from strongest to weakest using `vol² × prevalence`. Equal values are allowed and represent an exact tie.

### Sample spectrum

Use either:

1. exactly `n` positive eigenvalues from the PCA spectrum; or
2. exactly `k` leading eigenvalues plus the bulk mean ℓ, computed from all `n−k` remaining eigenvalues.

The app will not infer the bulk from a selected or truncated tail.

Spectrum mode is a plug-in scenario, not an inversion of the latent factor model.

## Near-tied factors

A one-to-one overlap-maximizing assignment measures how often estimated factors exchange their population-strength rank labels.

When adjacent factors exceed the tie cutoff (default 5%, adjustable in the sidebar):

- their named rows are marked unreliable;
- the headline emphasizes their joint span;
- named required-history decisions are withheld;
- no span-level history decision is substituted.

The cutoff is a display rule, not a theorem-derived threshold, and the swap rate is reported with its Monte Carlo interval so a verdict decided by less than the noise reads as noise. In simulation, estimated and true factors are matched by an overlap-maximizing assignment that uses the true directions — information unavailable on real data — so simulated named-factor accuracy is optimistic.

## Methodology

The full methodology and assumption register lives in [METHODOLOGY.md](METHODOLOGY.md) and in the app's `[5] methodology & assumptions` panel. Notably: PCA is on the sample covariance (not correlation) matrix, and the asymptotic tick is a p → ∞, fixed-n formula derived under Gaussian idiosyncratic noise — the Student-t option changes the simulated fan only.

## Tests

```bash
python -m unittest discover -s tests -v
python -B engine.py   # engine self-check
```

CI runs both on every push (`.github/workflows/test.yml`). Dependencies are pinned in `requirements.txt`; `runtime.txt` pins the Python version for Streamlit Cloud.

## License and citation

MIT ([LICENSE](LICENSE)). If you use this tool, cite it via [CITATION.cff](CITATION.cff).

## Running locally

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```
