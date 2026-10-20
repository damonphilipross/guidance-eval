# ASX guidance direction: model label vs arithmetic

A small, reproducible test of one question: when a language model reads an ASX earnings-guidance announcement, how often does it get the **direction** right (upgrade, downgrade, reaffirmed, initiated)? And is it better to trust the model's own label, or to have code compute the direction from the numbers the model extracted?

## Results

5 models × 40 announcements × 2 repeats = 400 calls. Total cost **US$0.49**. Intervals are 95% bootstrap CIs over announcements.

| Model | Direction: model's label | Direction: code (`direction.py`) | Prior figure | US$ per 1,000 |
|---|---|---|---|---|
| qwen/qwen3.7-flash | 92.5 [85.0, 98.8] | 91.2 [81.2, 98.8] | 95.0 [87.5, 100] | 0.20 |
| xiaomi/mimo-v2.5 | **100** [100, 100] | 92.5 [82.5, 100] | 100 | 0.86 |
| deepseek/deepseek-v4-pro | **100** [100, 100] | 96.2 [90.0, 100] | 98.8 [96.2, 100] | 3.42 |
| z-ai/glm-5.3-flash | **100** [100, 100] | 91.2 [82.5, 98.8] | 100 | 0.23 |
| anthropic/claude-haiku-5.5 | 97.5 [92.5, 100] | 91.2 [82.5, 98.8] | 100 | 1.40 |

What it says:

1. **The model's own label beat the arithmetic for every model.** The code tops out at 92.5% even with perfect extraction (it can't call a raised floor an upgrade, and it abstains when no prior is printed).
2. **The code rescued one model on one case.** qwen read Mayfield's numbers correctly ($4.7–5.3m cut to $2.4–2.7m) and still labelled it an upgrade. The code caught it.
3. **Agreement is the signal.** When the label and the code agreed, they were right every time: 0 wrong in 400 attempts. Every error sat in a disagreement. So the useful design is "flag disagreements for review", not "trust the code over the model".
4. **Prior figures are close to solved** (95–100%). The one bad miss: qwen invented a prior for MGH that appears nowhere in the release.
5. **Cost:** GLM-5.3-flash got 100% on labels for US$0.23 per 1,000 announcements. DeepSeek V4 Pro matched it at about 15× the price.

Small set, so read the intervals, not just the averages. Four models are statistically tied on labels; qwen is the one clear laggard.

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

`python eval.py score --raw results/raw.jsonl` re-scores a run offline. The published run's raw answers are not released; `results/scores_production_prompt.csv` holds the per-attempt outcomes. A full 5-model run cost about US$0.50.

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

## License

MIT. See `LICENSE`.
