"""Evaluation harness (docs/AGENT_DESIGN.md §11). Uses the configured LLM (or rule-based mode).

    uv run python -m evals.run jd_extraction            # synthetic + private datasets
Writes evals/results/<suite>-<timestamp>.json with model id, prompt version and per-field accuracy.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIELDS = ("job_title", "company", "experience_min", "experience_max", "work_mode", "salary_source_type")


def _load_cases(suite: str) -> list[dict]:
    cases = []
    for folder in (ROOT / "evals" / "datasets" / suite, ROOT / "evals" / "datasets" / "private" / suite):
        for f in sorted(folder.glob("*.yaml")) if folder.exists() else []:
            data = yaml.safe_load(f.read_text())
            for c in data.get("cases", []):
                c["text"] = c.get("text") or (f.parent / c["text_file"]).resolve().read_text()
                c["synthetic"] = data.get("synthetic", False)
                cases.append(c)
    return cases


def _prf(pred: set[str], gold: set[str]) -> tuple[float, float]:
    tp = len(pred & gold)
    return (tp / len(pred) if pred else 1.0), (tp / len(gold) if gold else 1.0)


async def run_jd(cases: list[dict]) -> dict:
    from app import agents
    from app.domain.job_verify import verify_extraction

    rows, field_hits, prec, rec, salary_halluc = [], dict.fromkeys(FIELDS, 0), [], [], 0
    model, prompt = None, None
    for c in cases:
        x, meta = await agents.extract_job(c["text"], company_hint=None, source_url=None, user_id=None, run_id=None)  # type: ignore[arg-type]
        model, prompt = meta.model_id, meta.prompt_ref
        v = verify_extraction(x, c["text"])
        got = {"job_title": v.title, "company": v.company_name, "experience_min": v.experience_min, "experience_max": v.experience_max,
               "work_mode": v.work_mode, "salary_source_type": v.salary_source_type}
        exp = c["expect"]
        for f in FIELDS:
            if f in exp:
                field_hits[f] += int((got[f] if not isinstance(got[f], float) else float(got[f])) == exp[f])
        mand = {s["name"] for s in v.skills if s["importance"] == "mandatory"}
        if "mandatory_skills" in exp:
            p, r = _prf(mand, set(exp["mandatory_skills"]))
            prec.append(p)
            rec.append(r)
        if exp.get("salary_source_type") == "not_disclosed" and v.salary_source_type != "not_disclosed":
            salary_halluc += 1
        rows.append({"id": c["id"], "synthetic": c["synthetic"], "got": got, "mandatory": sorted(mand)})
    n = max(1, len(cases))
    return {"model_id": model, "prompt": prompt, "cases": len(cases),
            "field_accuracy": {f: round(field_hits[f] / max(1, sum(f in c["expect"] for c in cases)), 3) for f in FIELDS},
            "mandatory_precision": round(sum(prec) / max(1, len(prec)), 3), "mandatory_recall": round(sum(rec) / max(1, len(rec)), 3),
            "salary_hallucinations": salary_halluc, "synthetic_share": round(sum(c["synthetic"] for c in cases) / n, 2), "rows": rows}


async def main(suite: str) -> int:
    import os

    os.environ.setdefault("APP_ENV", "local")
    from app.integrations.llm import service as llm

    if llm.llm_enabled():
        from app.core.db import system_session
        from app.models import User

        async with system_session() as s:  # LLM calls are logged against an eval user
            uid = uuid.uuid5(uuid.NAMESPACE_URL, "careerpilot-eval")
            if await s.get(User, uid) is None:
                s.add(User(id=uid, email="eval@careerpilot.local"))
    if suite != "jd_extraction":
        print("Available suites: jd_extraction")
        return 2
    result = await run_jd(_load_cases(suite))
    out = ROOT / "evals" / "results" / f"{suite}-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str))
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, indent=2))
    if result["synthetic_share"] == 1.0:
        print("NOTE: only synthetic cases — add manually reviewed JDs under evals/datasets/private/ before claiming quality.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "jd_extraction")))
