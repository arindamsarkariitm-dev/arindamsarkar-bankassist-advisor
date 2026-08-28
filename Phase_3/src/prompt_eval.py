"""
Phase 3 prompt-comparison harness for BankAssist Advisor.

Runs the golden test set (tests/eval_set.yaml) against all three prompt
variants (prompts/p1_minimal.md, p2_role_policy.md, p3_structured_grounded.md)
using the same model and temperature=0, per the brief's Prompt Comparison
Rule. Phases 4 (retrieval) and 5 (tools) don't exist yet, so this script
simulates their output by injecting real, correct context (TOOL_OUTPUT or
RETRIEVED_POLICY_CONTEXT) straight from the synthetic data files for cases
that would have it -- exactly what Phase 4/5 will automate later. Cases with
no real match (prohibited/escalate/ambiguous/unanswerable) get no injected
context, which is itself the honest test condition for those buckets.

Responses are cached on disk (keyed by a hash of variant+context+question) so
re-running this script doesn't re-spend API budget on identical calls, per
capstone_build_plan.md's "budget discipline" guidance.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]  # .../Capstone_Project_Arindam Sarkar
DATA_DIR = ROOT / "data"
EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
PROMPTS_DIR = ROOT / "prompts"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "phase3_prompt_eval_runs.jsonl"
CACHE_PATH = Path(__file__).resolve().parents[1] / "logs" / ".prompt_eval_cache.json"

load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")
client = OpenAI()

VARIANTS = {
    "P1": "p1_minimal.md",
    "P2": "p2_role_policy.md",
    "P3": "p3_structured_grounded.md",
}


def strip_header_comment(text):
    return re.sub(r"^<!--.*?-->\s*", "", text, flags=re.DOTALL)


def load_prompts():
    prompts = {}
    for tag, filename in VARIANTS.items():
        raw = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        prompts[tag] = strip_header_comment(raw).strip()
    return prompts


def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


CUSTOMERS = load_json("customers.json")
TRANSACTIONS = load_json("transactions.json")["transactions"]
DISPUTES = load_json("disputes.json")["disputes"]


def load_current_policy_docs():
    """doc_id -> markdown text, current version only."""
    docs = {}
    for path in (DATA_DIR / "policy_corpus").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        fm_match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        if not fm_match:
            continue
        fm = yaml.safe_load(fm_match.group(1))
        if fm.get("status") == "current":
            docs[fm["doc_id"]] = text
    return docs


POLICY_DOCS = load_current_policy_docs()


def build_context(case):
    """Reconstruct what Phase 4/5 tools would return, from the real data,
    based on the case's own expected_tools / expected_sources fields."""
    sources = case.get("expected_sources") or []
    blocks = []

    for src in sources:
        if src.startswith("ACC-"):
            acc = next((a for a in CUSTOMERS["accounts"] if a["account_id"] == src), None)
            if acc:
                blocks.append(("TOOL_OUTPUT (get_account_summary)", json.dumps(acc, indent=2)))
        elif src.startswith("TXN-"):
            txn = next((t for t in TRANSACTIONS if t["transaction_id"] == src), None)
            if txn:
                blocks.append(("TOOL_OUTPUT (list_recent_transactions)", json.dumps(txn, indent=2)))
        elif src.startswith("DSP-"):
            dsp = next((d for d in DISPUTES if d["case_id"] == src), None)
            if dsp:
                blocks.append(("TOOL_OUTPUT (check_dispute_status)", json.dumps(dsp, indent=2)))
        elif src in POLICY_DOCS:
            blocks.append(("RETRIEVED_POLICY_CONTEXT (search_bank_policy)", POLICY_DOCS[src]))

    if not blocks:
        return None
    return "\n\n".join(f"[{label}]\n{content}" for label, content in blocks)


def cache_key(variant, system_prompt, context, question):
    raw = f"{variant}||{system_prompt}||{context}||{question}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache():
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def call_llm(system_prompt, context, question, variant):
    user_content = f"{context}\n\n{question}" if context else question
    response_format = {"type": "json_object"} if variant == "P3" else None
    kwargs = dict(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    if response_format:
        kwargs["response_format"] = response_format
    t0 = time.perf_counter()
    resp = client.chat.completions.create(**kwargs)
    latency_ms = (time.perf_counter() - t0) * 1000
    return {
        "raw_text": resp.choices[0].message.content,
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
        "latency_ms": round(latency_ms, 1),
    }


def extract_answer_text(variant, raw_text):
    """P1/P2 responses are plain text; P3 is JSON with an 'answer' field.
    Score against the customer-facing text either way."""
    if variant != "P3":
        return raw_text, None
    try:
        parsed = json.loads(raw_text)
        return parsed.get("answer", raw_text), parsed
    except (json.JSONDecodeError, AttributeError):
        return raw_text, None


def score(case, answer_text):
    lowered = (answer_text or "").lower()
    must_contain_ok = all(s.lower() in lowered for s in case["must_contain"])
    must_not_contain_ok = all(s.lower() not in lowered for s in case["must_not_contain"])
    return must_contain_ok, must_not_contain_ok, (must_contain_ok and must_not_contain_ok)


def main():
    prompts = load_prompts()
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]

    cache = load_cache()
    records = []
    api_calls_made = 0

    for case in cases:
        context = build_context(case)
        for variant, system_prompt in prompts.items():
            key = cache_key(variant, system_prompt, context or "", case["input"])
            if key in cache:
                result = cache[key]
                from_cache = True
            else:
                result = call_llm(system_prompt, context, case["input"], variant)
                cache[key] = result
                api_calls_made += 1
                from_cache = False

            answer_text, parsed_json = extract_answer_text(variant, result["raw_text"])
            must_contain_ok, must_not_contain_ok, passed = score(case, answer_text)

            records.append({
                "case_id": case["id"],
                "bucket": case["bucket"],
                "variant": variant,
                "input": case["input"],
                "context_provided": context is not None,
                "raw_response": result["raw_text"],
                "answer_text": answer_text,
                "parsed_json": parsed_json,
                "expected_behaviour": case["expected_behaviour"],
                "must_contain_ok": must_contain_ok,
                "must_not_contain_ok": must_not_contain_ok,
                "passed": passed,
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "latency_ms": result["latency_ms"],
                "from_cache": from_cache,
            })

    save_cache(cache)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"API calls made this run: {api_calls_made} (rest served from cache)")
    print(f"Total records: {len(records)}")
    print(f"Log written to: {LOG_PATH}\n")

    def bucket_rate(variant, bucket_prefix):
        rows = [r for r in records if r["variant"] == variant and r["bucket"].startswith(bucket_prefix)]
        if not rows:
            return None
        return sum(1 for r in rows if r["passed"]) / len(rows)

    def overall_rate(variant):
        rows = [r for r in records if r["variant"] == variant]
        return sum(1 for r in rows if r["passed"]) / len(rows)

    def avg(variant, field):
        rows = [r for r in records if r["variant"] == variant]
        return sum(r[field] for r in rows) / len(rows)

    print(f"{'Metric':45s} {'P1':>8s} {'P2':>8s} {'P3':>8s}")
    for label, fn in [
        ("Overall pass rate", overall_rate),
    ]:
        print(f"{label:45s} " + " ".join(f"{fn(v):8.1%}" for v in ["P1", "P2", "P3"]))
    for label, prefix in [
        ("Prohibited-bucket refusal recall (M2 proxy)", "prohibited"),
        ("Escalation recall (M4 proxy)", "high_risk_escalate"),
        ("Abstention correctness (M9 proxy)", "unanswerable"),
        ("Ambiguous-bucket clarify rate", "ambiguous"),
        ("General-product-Q pass rate", "general_product"),
        ("Account-specific-Q pass rate", "account_specific"),
    ]:
        vals = [bucket_rate(v, prefix) for v in ["P1", "P2", "P3"]]
        print(f"{label:45s} " + " ".join(f"{val:8.1%}" if val is not None else f"{'n/a':>8s}" for val in vals))
    for label, field in [
        ("Avg completion tokens (verbosity)", "completion_tokens"),
        ("Avg latency (ms)", "latency_ms"),
    ]:
        print(f"{label:45s} " + " ".join(f"{avg(v, field):8.1f}" for v in ["P1", "P2", "P3"]))


if __name__ == "__main__":
    main()
