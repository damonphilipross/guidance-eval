"""A generic guidance-extraction prompt.

Deliberately plain: it asks for the fields the scorer needs and states the
two definitions that matter (what counts as a prior, same-period rule). It is
not the prompt used in production.
"""

PROMPT = """You are reading an ASX company announcement about earnings guidance.

Identify the company's main guidance figure in this announcement and return one JSON object:

{
  "direction": "UPGRADE" | "DOWNGRADE" | "REAFFIRMED" | "INITIATED" | "WITHDRAWN",
  "metric": "NPAT" | "EBITDA" | "EBIT" | "PBT" | "Revenue" | "EPS" | "Other",
  "metric_detail": string or null,
  "period": the period the new guidance is for, e.g. "FY26", "H1FY27", "H2FY26",
  "new_low": number or null,
  "new_high": number or null,
  "previous_low": number or null,
  "previous_high": number or null,
  "previous_source": "PRIOR_GUIDANCE" | "PCP_ACTUAL" | "NONE",
  "previous_period": string or null,
  "prior_is_floor": true | false,
  "last_year_actual": number or null,
  "unit": "millions" | "thousands" | "cents" | "percent",
  "currency": "AUD" | "NZD" | "USD" | "GBP" | ...
}

Definitions:
- previous_low/high are the company's EARLIER GUIDANCE for the same period. Last year's actual
  result is not guidance: put it in last_year_actual and use previous_source "PCP_ACTUAL" or "NONE".
- The previous and new figures must be for the same period (do not compare H2 with full year).
- A single number: set low and high to the same value. "At least $X": low = X, high = null.
  If the earlier guidance was a floor ("at least", "breakeven or better"), set prior_is_floor true.
- UPGRADE / DOWNGRADE = new guidance above / below the earlier guidance. REAFFIRMED = unchanged.
  INITIATED = first guidance for that period. WITHDRAWN = guidance removed.
- Report numbers in the unit printed ("$40m" -> 40, unit "millions").

Return only the JSON object.

ANNOUNCEMENT:
"""
