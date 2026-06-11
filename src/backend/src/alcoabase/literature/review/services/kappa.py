"""Pure helper for Cohen's kappa inter-rater reliability computation.

Extracted from SLRReviewService.compute_inter_rater_reliability() to enable
property-based testing without database access.

References:
    - Requirements 4.6
    - Design: SLR_Review_Service.compute_inter_rater_reliability()
"""

from __future__ import annotations


def compute_cohens_kappa(
    verdict_pairs: list[tuple[str, str]],
) -> float:
    """Compute Cohen's kappa coefficient for binary inter-rater agreement.

    Takes a list of (ai_verdict, human_verdict) pairs where each verdict is
    one of {"include", "exclude"} and returns the kappa statistic measuring
    agreement beyond chance.

    Formula:
        P_observed = (# agreements) / total
        P_ai_include = (# AI says include) / total
        P_ai_exclude = (# AI says exclude) / total
        P_human_include = (# human says include) / total
        P_human_exclude = (# human says exclude) / total
        P_expected = (P_ai_include * P_human_include) + (P_ai_exclude * P_human_exclude)
        kappa = (P_observed - P_expected) / (1 - P_expected) when P_expected < 1.0
        kappa = 0.0 when P_expected >= 1.0

    Args:
        verdict_pairs: List of (ai_verdict, human_verdict) tuples.
            Each verdict must be "include" or "exclude".

    Returns:
        Cohen's kappa coefficient as a float.
        Returns 0.0 when the list is empty or P_expected >= 1.0.

    Raises:
        ValueError: If any verdict is not "include" or "exclude".
    """
    if not verdict_pairs:
        return 0.0

    valid_verdicts = {"include", "exclude"}
    for ai_v, human_v in verdict_pairs:
        if ai_v not in valid_verdicts:
            msg = f"Invalid AI verdict: {ai_v!r}. Must be 'include' or 'exclude'."
            raise ValueError(msg)
        if human_v not in valid_verdicts:
            msg = f"Invalid human verdict: {human_v!r}. Must be 'include' or 'exclude'."
            raise ValueError(msg)

    total = len(verdict_pairs)

    agreements = sum(1 for ai_v, human_v in verdict_pairs if ai_v == human_v)

    ai_include = sum(1 for ai_v, _ in verdict_pairs if ai_v == "include")
    ai_exclude = total - ai_include
    human_include = sum(1 for _, human_v in verdict_pairs if human_v == "include")
    human_exclude = total - human_include

    p_observed = agreements / total

    p_ai_include = ai_include / total
    p_ai_exclude = ai_exclude / total
    p_human_include = human_include / total
    p_human_exclude = human_exclude / total

    p_expected = (p_ai_include * p_human_include) + (p_ai_exclude * p_human_exclude)

    if p_expected >= 1.0:
        return 0.0

    return (p_observed - p_expected) / (1.0 - p_expected)
