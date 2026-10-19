"""Score LLMs on ASX guidance direction: the model's own label vs arithmetic on its numbers.

    export OPENROUTER_API_KEY=...
    python eval.py run --models qwen/qwen3.7-flash,anthropic/claude-haiku-5.5 --repeats 2
    python eval.py score

`run` downloads each announcement PDF from the ASX by document id (cached in
pdf_cache/), extracts the text with PyMuPDF, sends prompt.PROMPT + text
(first 30,000 characters) to every model with identical settings, and appends
one line per attempt to results/raw.jsonl. `score` compares each answer with
golden/guidance_golden.json and bootstraps 95% CIs over announcements.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
GOLDEN = HERE / "golden" / "guidance_golden.json"
RAW = HERE / "results" / "raw.jsonl"
CACHE = HERE / "pdf_cache"
ASX_FILE = "https://cdn-api.markitdigital.com/apiman-gateway/ASX/asx-research/1.0/file/"
CAP = 30_000
DIRS = {"UPGRADE", "DOWNGRADE", "REAFFIRMED", "INITIATED", "WITHDRAWN"}

from direction import direction, period_kind  # noqa: E402


# ------------------------------------------------------------------ run

def pdf_text(doc_id: str) -> str:
    import fitz  # PyMuPDF
    import httpx

    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{doc_id}.pdf"
    if not path.exists():
        r = httpx.get(ASX_FILE + doc_id, timeout=60, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www2.asx.com.au/"})
        r.raise_for_status()
        path.write_bytes(r.content)
    return "\n".join(page.get_text() for page in fitz.open(path))


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start = min(i for i in (text.find("{"), text.find("[")) if i >= 0)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1])


def run(models: list[str], rows: list[dict], repeats: int, workers: int) -> None:
    import httpx
    from openai import OpenAI

    from prompt import PROMPT

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=os.environ["OPENROUTER_API_KEY"])
    prices = {m["id"]: m["pricing"] for m in
              httpx.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]}
    texts = {r["id"]: pdf_text(r["doc_key"]) for r in rows}
    lock = threading.Lock()
    RAW.parent.mkdir(exist_ok=True)

    def one(model: str, row: dict, rep: int) -> None:
        rec = {"model": model, "row_id": row["id"], "repeat": rep}
        try:
            resp = client.chat.completions.create(
                model=model, temperature=0, max_tokens=8000,
                messages=[{"role": "user", "content": PROMPT + texts[row["id"]][:CAP]}])
            u = resp.usage
            rec["data"] = parse_json(resp.choices[0].message.content or "")
            rec["cost_usd"] = (u.prompt_tokens * float(prices[model]["prompt"])
                               + u.completion_tokens * float(prices[model]["completion"]))
        except Exception as exc:  # noqa: BLE001 - a failed call is a scored failure
            rec["data"], rec["error"] = None, str(exc)[:300]
        with lock, RAW.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    jobs = [(m, r, k) for m in models for r in rows for k in range(repeats)]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda j: one(*j), jobs))


# ---------------------------------------------------------------- score

def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def matches(got, want) -> bool:
    if isinstance(want, dict) and "any_of" in want:
        return any(matches(got, w) for w in want["any_of"])
    if want is None:
        return got is None
    if isinstance(want, str):
        return isinstance(got, str) and got.strip().upper() == want.upper()
    g = _num(got)
    return g is not None and abs(g - want) <= max(abs(want) * 0.005, 0.01)


def pair_ok(lo, hi, want_lo, want_hi) -> bool:
    """A point figure may be written with the top left blank."""
    return (matches(lo, want_lo) and matches(hi, want_hi)) or \
        (hi is None and matches(lo, want_lo) and matches(lo, want_hi))


def figures(d: dict) -> dict:
    unit = (d.get("unit") or "").lower()

    def scale(v):
        v = _num(v)
        if v is None:
            return None
        if unit == "thousands":
            return v / 1_000
        if unit == "millions" and abs(v) >= 100_000:
            return v / 1_000_000
        return v
    return {f: scale(d.get(f)) for f in ("previous_low", "previous_high", "new_low", "new_high")}


def pick_target(row: dict, data: dict) -> dict:
    """The key or alternate the answer is about: its new figure first (preferring
    a matching metric when two share a figure), then metric + period."""
    cands = [row["key"], *row.get("alternates", [])]
    fig = figures(data)
    same_metric = lambda t: (data.get("metric") or "").upper() == t["metric"].upper()
    hits = [t for t in cands if pair_ok(fig["new_low"], fig["new_high"], t["new_low"], t["new_high"])
            and (fig["new_low"] is not None or fig["new_high"] is not None)]
    if hits:
        return next((t for t in hits if same_metric(t)), hits[0])
    return next((t for t in cands if same_metric(t)
                 and period_kind(data.get("period")) == period_kind(t["period"])), row["key"])


def score_attempt(row: dict, data) -> dict:
    if isinstance(data, list):  # a list reply is scored on its first item
        data = data[0] if data else None
    if isinstance(data, dict) and isinstance(data.get("events"), list):
        data = data["events"][0] if data["events"] else None
    if not data:
        return {"label": "blank", "code": "blank", "prior": "blank"}
    target = pick_target(row, data)
    truth = target["direction"]
    fig = figures(data)
    label_got = (data.get("direction") or data.get("guidance_type") or "").strip().upper() or None
    code_got = direction(data)
    blank = fig["previous_low"] is None and fig["previous_high"] is None
    source = (data.get("previous_source") or "").strip().upper() or ("NONE" if blank else None)
    prior_ok = matches(source, target["previous_source"]) and \
        pair_ok(fig["previous_low"], fig["previous_high"], target["previous_low"], target["previous_high"])
    return {
        "label": "blank" if label_got not in DIRS else ("ok" if matches(label_got, truth) else "wrong"),
        "code": "abstain" if code_got == "UNCOMPARABLE" else ("ok" if matches(code_got, truth) else "wrong"),
        "prior": "ok" if prior_ok else ("blank" if blank and not matches(None, target["previous_low"]) else "wrong"),
    }


def bootstrap(xs: list[float], n: int = 10_000, seed: int = 7) -> tuple[float, float, float]:
    rng, k = random.Random(seed), len(xs)
    means = sorted(sum(rng.choice(xs) for _ in range(k)) / k for _ in range(n))
    return sum(xs) / k, means[int(0.025 * n)], means[int(0.975 * n) - 1]


def score(rows: list[dict], raw: Path = RAW) -> None:
    by_id = {r["id"]: r for r in rows}
    per = defaultdict(lambda: defaultdict(list))
    cost = defaultdict(list)
    for line in raw.read_text().splitlines():
        rec = json.loads(line)
        if rec["row_id"] in by_id:
            per[rec["model"]][rec["row_id"]].append(score_attempt(by_id[rec["row_id"]], rec.get("data")))
            cost[rec["model"]].append(rec.get("cost_usd") or 0)
    fmt = lambda t: f"{100*t[0]:.1f} [{100*t[1]:.1f}, {100*t[2]:.1f}]"
    print("| Model | Label direction | Code direction | Code right and prior right | Prior figure | $ per 1,000 |")
    print("|---|---|---|---|---|---|")
    for model, rs in per.items():
        ids = sorted(rs)
        rate = lambda f: [sum(s[f] == "ok" for s in rs[i]) / len(rs[i]) for i in ids]
        both = [sum(s["code"] == "ok" and s["prior"] == "ok" for s in rs[i]) / len(rs[i]) for i in ids]
        print(f"| {model} | {fmt(bootstrap(rate('label')))} | {fmt(bootstrap(rate('code')))} | "
              f"{fmt(bootstrap(both))} | {fmt(bootstrap(rate('prior')))} | "
              f"{1000 * sum(cost[model]) / len(cost[model]):.2f} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--models", required=True, help="comma-separated OpenRouter model ids")
    r.add_argument("--repeats", type=int, default=2)
    r.add_argument("--workers", type=int, default=16)
    s = sub.add_parser("score")
    s.add_argument("--raw", default=str(RAW))
    a = ap.parse_args()
    rows = json.loads(GOLDEN.read_text())["rows"]
    if a.cmd == "run":
        run(a.models.split(","), rows, a.repeats, a.workers)
        score(rows)
    else:
        score(rows, Path(a.raw))
