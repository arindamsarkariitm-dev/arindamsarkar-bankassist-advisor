"""
Phase 8 evidence: 50+ real turns through the full graph, capturing latency
and errors to a CSV (capstone_build_plan.md §8: "logs/latency_errors.csv
(50+ turns)"). Runs the golden test set twice (56 turns) -- reusing the
same 28 cases twice, rather than inventing new ones, still produces
genuinely independent timing/behaviour data each pass (LLM latency and
occasional retries are not deterministic even at temperature=0).
"""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import yaml  # noqa: E402
from graph import run_turn  # noqa: E402

EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
OUT_PATH = Path(__file__).resolve().parents[1] / "logs" / "latency_errors.csv"

FIELDS = [
    "pass_num", "case_id", "customer_id", "trace_id", "intent", "route", "outcome",
    "total_latency_ms", "prompt_tokens", "completion_tokens", "error",
]


def main():
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for pass_num in (1, 2):
        for case in cases:
            customer_id = case["context"].get("customer_id") or "CUST-0001"
            error = None
            t0 = time.perf_counter()
            try:
                result = run_turn(case["input"], customer_id)
            except Exception as e:  # noqa: BLE001 -- this CSV exists specifically to capture errors, not just successes
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
                rows.append({
                    "pass_num": pass_num, "case_id": case["id"], "customer_id": customer_id,
                    "trace_id": "", "intent": "", "route": "", "outcome": "ERROR",
                    "total_latency_ms": elapsed_ms, "prompt_tokens": "", "completion_tokens": "",
                    "error": f"{type(e).__name__}: {e}",
                })
                continue
            trace = result.get("trace", {})
            token_usage = trace.get("token_usage", {})
            rows.append({
                "pass_num": pass_num, "case_id": case["id"], "customer_id": customer_id,
                "trace_id": trace.get("trace_id", ""), "intent": result.get("intent"),
                "route": result.get("route"), "outcome": trace.get("outcome"),
                "total_latency_ms": trace.get("total_latency_ms"),
                "prompt_tokens": token_usage.get("prompt_tokens"),
                "completion_tokens": token_usage.get("completion_tokens"),
                "error": "",
            })
            print(f"pass {pass_num} {case['id']:8s} {trace.get('total_latency_ms', '?'):>8} ms  outcome={trace.get('outcome')}")

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    latencies = sorted(r["total_latency_ms"] for r in rows if isinstance(r["total_latency_ms"], (int, float)))
    errors = [r for r in rows if r["outcome"] == "ERROR"]
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(0.95 * (len(latencies) - 1))]
        print(f"\nTotal turns: {len(rows)} | Errors: {len(errors)}")
        print(f"p50 latency: {p50:.0f} ms | p95 latency: {p95:.0f} ms | max: {latencies[-1]:.0f} ms")
    print(f"Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
