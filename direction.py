"""Guidance direction from extracted numbers.

The model reads the announcement and reports the figures (prior guidance,
new guidance, periods, whether the prior was a floor). This module does the
arithmetic only; it never reads text.

    - Only a prior that is previous GUIDANCE is a prior (not last year's result).
    - Prior and new must be for the same kind of period (H1, H2, FY, quarter).
    - Direction = midpoint(new) vs midpoint(prior), with +/-1% counting as unchanged.
    - A floor prior ("at least $X"): DOWNGRADE if the new top is below the floor,
      otherwise REAFFIRMED. (Known gap: a floor raised to a higher floor comes
      out REAFFIRMED; kept as-is because it is what was measured.)
    - No prior: INITIATED, or UNCOMPARABLE if the model claimed an up/down move
      it has no number for. UNCOMPARABLE is scored as an abstention.
"""

from __future__ import annotations

BAND = 0.01


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rescale(v, unit):
    if v is None:
        return None
    u = (unit or "").lower()
    if u == "thousands":
        return v / 1_000
    if u == "millions" and abs(v) >= 100_000:
        return v / 1_000_000
    return v


def _mid(lo, hi):
    vals = [v for v in (lo, hi) if v is not None]
    return sum(vals) / len(vals) if vals else None


def period_kind(period):
    if not period:
        return None
    p = str(period).upper().replace(" ", "").replace("'", "").replace("’", "")
    for kind in ("H1", "H2"):
        if p.startswith((kind, kind[::-1])):
            return kind
    if p.startswith("Q"):
        return "Q"
    if p.startswith(("FY", "CY")) or (p[:4].isdigit() and len(p) == 4):
        return "FY"
    return None


def direction(data: dict) -> str:
    """UPGRADE | DOWNGRADE | REAFFIRMED | INITIATED | WITHDRAWN | UNCOMPARABLE."""
    label = (data.get("direction") or data.get("guidance_type") or "").upper() or None
    unit = data.get("unit")
    p_lo = _rescale(_num(data.get("previous_low")), unit)
    p_hi = _rescale(_num(data.get("previous_high")), unit)
    n_lo = _rescale(_num(data.get("new_low")), unit)
    n_hi = _rescale(_num(data.get("new_high")), unit)
    pcp = _rescale(_num(data.get("last_year_actual") or data.get("pcp_actual")), unit)
    floor = bool(data.get("prior_is_floor"))
    source = (data.get("previous_source") or "").upper() or None

    if p_lo is not None or p_hi is not None:
        if source in {"PCP_ACTUAL", "NONE"}:
            p_lo = p_hi = None
        elif pcp is not None and p_lo == pcp and p_hi in (pcp, None):
            p_lo = p_hi = None
        elif floor:
            p_hi = None
    has_prior = p_lo is not None or p_hi is not None

    nk, pk = period_kind(data.get("period")), period_kind(data.get("previous_period")) if has_prior else None
    comparable = has_prior and not (pk and nk and pk != nk)
    new_vals = [v for v in (n_lo, n_hi) if v is not None]

    if label == "WITHDRAWN" and not new_vals:
        return "WITHDRAWN"
    if not new_vals:
        return "REAFFIRMED" if label == "REAFFIRMED" else "UNCOMPARABLE"
    if has_prior and comparable:
        if floor:
            return "DOWNGRADE" if max(new_vals) < p_lo else "REAFFIRMED"
        n_mid, p_mid = _mid(n_lo, n_hi), _mid(p_lo, p_hi)
        if p_mid == 0:
            return "REAFFIRMED" if n_mid == 0 else ("UPGRADE" if n_mid > 0 else "DOWNGRADE")
        change = (n_mid - p_mid) / abs(p_mid)
        return "REAFFIRMED" if abs(change) <= BAND else ("UPGRADE" if change > 0 else "DOWNGRADE")
    if has_prior:
        return "UNCOMPARABLE"
    if label in {"UPGRADE", "DOWNGRADE"}:
        return "UNCOMPARABLE"
    if label == "REAFFIRMED":
        return "REAFFIRMED"
    return "INITIATED"
