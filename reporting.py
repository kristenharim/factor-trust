"""Pure presentation helpers shared by the Streamlit app and unit tests."""
import math

# Two directions drawn at random in R^p are almost exactly orthogonal once p is
# large (the angle concentrates at 90 with sd ~ 1/sqrt(p) radians, about a degree
# at p=3000). So 90 is not "the worst case" on some arbitrary scale, it is the
# score a coin flip gets, and every angle the tool prints should be read against
# it. Without the anchor a reader sees 44 < 90 and assumes that is fine.
RANDOM_BASELINE_DEG = 90.0


def resid_var_pct(angle_deg):
    """Fraction of the factor's directional variance a book neutralized on the
    ESTIMATED direction still carries: sin² of the angle to the true one.

    The same number reads two ways and the app uses both: the share of the
    estimated direction pointing somewhere other than the factor, and the share of
    the exposure an idealized hedge on that direction fails to remove.
    """
    return math.sin(math.radians(angle_deg)) ** 2 * 100


def verdict(angle_deg, swap_rate, green_deg, amber_deg, tie_tol):
    """(state, sentence) for one factor row. The bands are the user's, not ours.

    "Usable" is use-dependent - 17 degrees is fine for neutralizing broad market
    exposure and not fine for attributing PnL to factor 3 - so the thresholds are
    inputs and the sentence names the consequence instead of passing judgement.
    An unstable label overrides the angle bands: a precise number attached to the
    wrong factor is worse than a loose one attached to the right factor.
    """
    elsewhere = resid_var_pct(angle_deg)
    if swap_rate > tie_tol:
        return "unstable", (f"swaps places with a neighbour on {swap_rate * 100:.0f}% of runs, "
                            "so the name is not reliable. Read the span instead.")
    if angle_deg < green_deg:
        return "usable", (f"about {elsewhere:.0f}% of it points somewhere other than the factor, "
                          f"so a hedge on it clears roughly {100 - elsewhere:.0f}% of the exposure.")
    if angle_deg < amber_deg:
        return "caution", (f"about {elsewhere:.0f}% of it points elsewhere. Usable for "
                           "neutralizing broad exposure, not for attributing PnL to this factor.")
    return "unusable", (f"about {elsewhere:.0f}% of it points elsewhere, against 100% for a "
                        "direction picked at random. Treat it as a plane, not a factor.")


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
