# ASX guidance direction: model label vs arithmetic

A small, reproducible test of one question: when a language model reads an ASX earnings-guidance announcement, how often does it get the **direction** right (upgrade, downgrade, reaffirmed, initiated)? And is it better to trust the model's own label, or to have code compute the direction from the numbers the model extracted?

## What's here

| File | What it is |
|---|---|
| `golden/guidance_golden.json` | 40 ASX announcements (document ids), each with a hand-written answer key: metric, period, prior low/high and its source, new low/high, direction. Every key cites the page and a short quote from the PDF. `alternates` are other metrics in the same release that count as an equally valid primary metric. |
| `prompt.py` | A generic extraction prompt. |
| `direction.py` | The direction arithmetic: midpoint of new vs prior guidance, ±1% = unchanged, same-period check, floor handling. |
| `eval.py` | Downloads the PDFs from the ASX, runs models through OpenRouter, scores them, and bootstraps 95% CIs over announcements. |
| `results/scores_production_prompt.csv` | Per-attempt scores from the published run (5 models × 40 × 2 repeats). |

## Run it

```bash
pip install -r requirements.txt
export OPENROUTER_API_KEY=...
python eval.py run --models z-ai/glm-5.3-flash,anthropic/claude-haiku-5.5 --repeats 2
```

`python eval.py score` re-scores `results/raw.jsonl` offline. A full 5-model run cost about US$0.50.

## How answers are scored

- **Label direction:** the model's own direction field, compared with the key.
- **Code direction:** `direction.py` applied to the model's numbers. `UNCOMPARABLE` counts as an abstention, not an error.
- **Prior figure:** correct when `previous_source` matches and previous_low/high are within 0.5% of the key.
- **Multi-metric releases:** the answer is scored against whichever metric (key or alternate) the model reported.

## Important: these scores are not from this prompt

The published scores in `results/` come from a production prompt that isn't released here. `prompt.py` is a simpler generic prompt, so if you rerun with it, expect different numbers. The golden set, the arithmetic and the scorer are the same code that produced the published results.

## Known limitation, kept on purpose

`direction.py` cannot return UPGRADE when the prior guidance was a floor ("at least $35m" raised to "at least $40m" computes as REAFFIRMED). That's the arithmetic that was measured, so it's left as is. See row 12 (RPL).

## Data

The announcements are public ASX company announcements, fetched by document id from the ASX's own file endpoint. The PDFs aren't redistributed here; the golden file holds only document ids, figures and short quotes.
