"""Count-based cascade metrics. Standard library only (no NumPy)."""
from __future__ import annotations


def ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def fmt(value, digits=4):
    return "n/a (empty denominator)" if value is None else f"{value:.{digits}f}"


def event_scores(gold_invalidated: frozenset, gold_activated: frozenset,
                 pred_invalidated: frozenset, pred_activated: frozenset) -> dict:
    """Exact-event accounting for one retraction event.

    An event is exact when the counter engine reports precisely the oracle's
    label transitions. False invalidations are reported transitions the
    oracle did not make; missed invalidations are oracle transitions the
    engine did not report. Either kind fails the reproduction (exit 1).
    """
    exact = (pred_invalidated == gold_invalidated and pred_activated == gold_activated)
    return {
        "exact": exact,
        "false_invalidations": len(pred_invalidated - gold_invalidated),
        "missed_invalidations": len(gold_invalidated - pred_invalidated),
        "false_activations": len(pred_activated - gold_activated),
        "missed_activations": len(gold_activated - pred_activated),
        "gold_changed": bool(gold_invalidated or gold_activated),
        "pred_changed": bool(pred_invalidated or pred_activated),
    }
