"""
Phase 5 evaluation: run the golden test set (tests/eval_set.yaml) through the
REAL LangGraph pipeline (src/graph.py) -- not a simulated/manual context
injection like Phases 3-4 used, since the graph now does its own retrieval
and tool-calling end to end. Logs every full run and scores against the
same must_contain/must_not_contain rubric used throughout.
"""
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from graph import run_turn  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "phase5_tool_traces.jsonl"


def _extract_tool_calls(messages):
    calls = []
    for m in messages or []:
        if isinstance(m, AIMessage) and m.tool_calls:
            for tc in m.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls


def score(case, response_text):
    lowered = (response_text or "").lower()
    must_contain_ok = all(s.lower() in lowered for s in case["must_contain"])
    must_not_contain_ok = all(s.lower() not in lowered for s in case["must_not_contain"])
    return must_contain_ok, must_not_contain_ok, (must_contain_ok and must_not_contain_ok)


def main():
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]

    records = []
    for case in cases:
        customer_id = case["context"].get("customer_id") or "CUST-0001"  # policy/unanswerable cases still need a session
        t0 = time.perf_counter()
        try:
            result = run_turn(case["input"], customer_id)
            error = None
        except Exception as e:  # noqa: BLE001
            result = {}
            error = f"{type(e).__name__}: {e}"
        latency_ms = (time.perf_counter() - t0) * 1000

        response_text = result.get("final_response", "")
        must_contain_ok, must_not_contain_ok, passed = score(case, response_text)
        tool_calls = _extract_tool_calls(result.get("messages"))

        record = {
            "case_id": case["id"],
            "bucket": case["bucket"],
            "input": case["input"],
            "customer_id": customer_id,
            "expected_behaviour": case["expected_behaviour"],
            "intent": result.get("intent"),
            "risk_level": result.get("risk_level"),
            "route": result.get("route"),
            "tool_calls": tool_calls,
            "tools_called": result.get("tools_called", []),
            "doc_ids_cited": result.get("doc_ids_cited", []),
            "tool_call_count": result.get("tool_call_count", 0),
            "grounding_ok": result.get("grounding_ok"),
            "regenerate_count": result.get("regenerate_count", 0),
            "final_response": response_text,
            "refusal_code": result.get("refusal_code"),
            "escalation_code": result.get("escalation_code"),
            "escalation_ticket": result.get("escalation_ticket"),
            "must_contain_ok": must_contain_ok,
            "must_not_contain_ok": must_not_contain_ok,
            "passed": passed,
            "latency_ms": round(latency_ms, 1),
            "error": error,
        }
        records.append(record)
        print(f"{case['id']:8s} intent={result.get('intent', 'ERROR'):22s} route={result.get('route', ''):10s} "
              f"tools={[c['name'] for c in tool_calls]!s:45s} passed={passed}")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    total = len(records)
    passed = sum(1 for r in records if r["passed"])
    print(f"\nOverall pass rate: {passed}/{total} = {passed/total:.1%}")

    def bucket_rate(prefix):
        rows = [r for r in records if r["bucket"].startswith(prefix)]
        return sum(1 for r in rows if r["passed"]) / len(rows) if rows else None

    for label, prefix in [
        ("General product", "general_product"), ("Account specific", "account_specific"),
        ("Prohibited (all)", "prohibited"), ("High-risk escalate", "high_risk_escalate"),
        ("Ambiguous", "ambiguous"), ("Unanswerable", "unanswerable"),
    ]:
        rate = bucket_rate(prefix)
        print(f"  {label:20s} {rate:.1%}" if rate is not None else f"  {label:20s} n/a")

    print(f"\nLog written to: {LOG_PATH}")


if __name__ == "__main__":
    main()
