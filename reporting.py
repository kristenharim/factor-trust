"""Pure presentation helpers shared by the Streamlit app and unit tests."""
import math


def wilson95(rate, trials):
    """95% Wilson score interval for a Bernoulli rate estimated from `trials`
    Monte Carlo paths. Closed form, so the swap-rate uncertainty costs nothing.
    Returns (lo, hi) as rates in [0, 1]."""
    z = 1.959963984540054
    denom = 1.0 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denom
    half = (z / denom) * math.sqrt(rate * (1.0 - rate) / trials
                                   + z * z / (4.0 * trials * trials))
    return max(0.0, center - half), min(1.0, center + half)


def tied_runs(confusion, k, tolerance=0.05):
    """Adjacent mutually confused factors, merged into contiguous runs."""
    mutual = [max(confusion[j][j + 1], confusion[j + 1][j]) for j in range(k - 1)]
    runs = []
    for j, rate in enumerate(mutual):
        if rate <= tolerance:
            continue
        if runs and runs[-1][-1] == j:
            runs[-1] = runs[-1] + (j + 1,)
        else:
            runs.append((j, j + 1))
    return runs, mutual


def stable_factor_indices(k, tied_groups):
    tied = {j for group in tied_groups for j in group}
    return [j for j in range(k) if j not in tied]


def build_export_payload(*, engine_fingerprint, inputs, factors, subspaces,
                         tie_groups, assumptions, spectrum=None):
    """Canonical, claim-aware export used for both JSON and flattened CSV."""
    return {
        "schema_version": 1,
        "provenance": {
            "engine_fingerprint": engine_fingerprint,
            "prototype_status": "not group-reviewed",
        },
        "inputs": inputs,
        "spectrum": spectrum,
        "claim_boundary": {
            "named_factor_reliable": len(tie_groups) == 0,
            "tie_groups": tie_groups,
            "subspace_output": "conditional simulation only",
            "subspace_floor": None,
            "subspace_required_history": None,
        },
        "factors": factors,
        "subspaces": subspaces,
        "assumptions": assumptions,
    }


def export_rows(payload):
    """Flatten canonical output without dropping reliability or provenance."""
    common = {
        "engine_fingerprint": payload["provenance"]["engine_fingerprint"],
        "n": payload["inputs"]["n"],
        "p": payload["inputs"]["p"],
        "k": payload["inputs"]["k"],
        "source": payload["inputs"]["source"],
        "conditional_simulation": True,
    }
    rows = []
    for factor in payload["factors"]:
        rows.append({**common, "object_type": "named_factor", **factor})
    for subspace in payload["subspaces"]:
        rows.append({**common, "object_type": "subspace", **subspace})
    return rows
