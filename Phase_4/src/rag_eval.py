"""
Phase 4 evaluation harness for BankAssist Advisor's RAG pipeline.

1. Retrieval quality: hit@1 / hit@3 / MRR over 20 labelled queries, at a
   handful of candidate similarity floors -- to actually tune the floor
   (capstone_build_plan.md §4: "start 0.35 and tune") rather than assert it.
2. Out-of-corpus probes: does each candidate floor correctly reject queries
   about products that don't exist, or does it leak marginally-related
   chunks through as false "hits"?
3. RAG vs. no-RAG: same 10 questions, answered with and without retrieved
   context, using the Phase 3-winning P3 prompt.
4. The missing-info case: the crypto-savings question, using the final
   tuned floor, showing correct abstention.
"""
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]  # .../Capstone_Project_Arindam Sarkar
sys.path.insert(0, str(ROOT / "src"))
import retriever as retriever_mod  # noqa: E402

PROMPTS_DIR = ROOT / "prompts"
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

load_dotenv(ROOT / ".env")
import os  # noqa: E402
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")
client = OpenAI()

P3_PROMPT = re.sub(r"^<!--.*?-->\s*", "", (PROMPTS_DIR / "p3_structured_grounded.md").read_text(encoding="utf-8"), flags=re.DOTALL).strip()

# ---------------------------------------------------------------------------
# 1. Labelled retrieval eval: 20 queries, 2 per corpus doc.
# ---------------------------------------------------------------------------
LABELLED_QUERIES = [
    ("What's the daily ATM withdrawal limit on a debit card?", "debit-card-terms"),
    ("How do I block a lost or stolen debit card?", "debit-card-terms"),
    ("When is the minimum amount due on a credit card bill?", "credit-card-terms"),
    ("What happens if I withdraw cash using my credit card?", "credit-card-terms"),
    ("How long does it take to resolve a disputed transaction?", "dispute-chargeback-procedure"),
    ("What evidence do I need to raise a dispute?", "dispute-chargeback-procedure"),
    ("What documents are needed for a home loan application?", "home-loan-document-checklist"),
    ("What's the minimum credit score for home loan eligibility?", "home-loan-document-checklist"),
    ("How often do I need to complete re-KYC?", "kyc-requirements"),
    ("What happens if I don't complete KYC on time?", "kyc-requirements"),
    ("What's the interest rate on a fixed deposit?", "savings-interest-policy"),
    ("How is savings account interest calculated?", "savings-interest-policy"),
    ("What's the maximum amount I can send via IMPS?", "upi-neft-imps-limits"),
    ("Is there a fee for NEFT transfers?", "upi-neft-imps-limits"),
    ("How do I escalate a complaint to the banking ombudsman?", "complaint-escalation-matrix"),
    ("What's the response time for a Level 2 complaint escalation?", "complaint-escalation-matrix"),
    ("What options are available if I can't pay my EMI due to job loss?", "financial-hardship-policy"),
    ("What documents are needed to apply for an EMI moratorium?", "financial-hardship-policy"),
    ("What's the late payment fee on a credit card?", "fee-schedule"),
    ("How much does it cost to replace a lost debit card?", "fee-schedule"),
]

OUT_OF_CORPUS_PROBES = [
    "What's the interest rate on your crypto savings product?",
    "What's the EMI on a used-car loan?",
    "Does the bank offer an NRI-specific credit card with Diamond-tier lounge access?",
]

CANDIDATE_FLOORS = [0.35, 0.40, 0.45]


def eval_floor(floor):
    reciprocal_ranks = []
    hit1 = hit3 = 0
    per_query = []
    for query, expected_doc_id in LABELLED_QUERIES:
        results = retriever_mod.retrieve(query, similarity_floor=floor)
        doc_ids_in_order = [r["metadata"]["doc_id"] for r in results]
        rank = next((i + 1 for i, d in enumerate(doc_ids_in_order) if d == expected_doc_id), None)
        if rank == 1:
            hit1 += 1
        if rank is not None and rank <= 3:
            hit3 += 1
        reciprocal_ranks.append(1 / rank if rank else 0)
        per_query.append({"query": query, "expected": expected_doc_id, "rank": rank, "retrieved": doc_ids_in_order})

    n = len(LABELLED_QUERIES)
    probe_leaks = []
    for probe in OUT_OF_CORPUS_PROBES:
        results = retriever_mod.retrieve(probe, similarity_floor=floor)
        probe_leaks.append({"query": probe, "n_results": len(results),
                             "doc_ids": [r["metadata"]["doc_id"] for r in results],
                             "scores": [r["score"] for r in results]})

    return {
        "floor": floor,
        "hit_at_1": hit1 / n,
        "hit_at_3": hit3 / n,
        "mrr": sum(reciprocal_ranks) / n,
        "per_query": per_query,
        "probe_leaks": probe_leaks,
        "probes_correctly_empty": sum(1 for p in probe_leaks if p["n_results"] == 0),
    }


# ---------------------------------------------------------------------------
# 2. RAG vs no-RAG, same 10 questions.
# ---------------------------------------------------------------------------
RAG_VS_NORAG_QUESTIONS = [
    "What's the foreign transaction fee on a debit card?",
    "What's the late payment fee on a credit card?",
    "How much can a customer send via UPI in a day?",
    "What's the savings account interest rate for a balance under Rs.1 lakh?",
    "What documents does a customer need for a home loan application?",
    "How long does a dispute typically take to resolve?",
    "What's the annual maintenance fee on a debit card?",
    "How often does a customer need to complete re-KYC?",
    "What happens if a customer misses a credit card payment?",
    "What options exist if a customer can't pay their EMI due to hardship?",
]


def call_llm(system_prompt, user_content):
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    latency_ms = (time.perf_counter() - t0) * 1000
    raw = resp.choices[0].message.content
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    return raw, parsed, latency_ms


def rag_vs_norag(final_floor):
    records = []
    for question in RAG_VS_NORAG_QUESTIONS:
        # no-RAG: just the question, no context block.
        raw_no, parsed_no, lat_no = call_llm(P3_PROMPT, question)

        # RAG: retrieve at the tuned floor, inject as RETRIEVED_POLICY_CONTEXT.
        results = retriever_mod.retrieve(question, similarity_floor=final_floor)
        if results:
            context = "\n\n".join(
                f"[RETRIEVED_POLICY_CONTEXT doc_id={r['metadata']['doc_id']} "
                f"effective_date={r['metadata']['effective_date']} score={r['score']}]\n{r['document']}"
                for r in results
            )
            user_content = f"{context}\n\n{question}"
        else:
            user_content = question
        raw_rag, parsed_rag, lat_rag = call_llm(P3_PROMPT, user_content)

        records.append({
            "question": question,
            "no_rag_answer": (parsed_no or {}).get("answer", raw_no),
            "no_rag_sources": (parsed_no or {}).get("sources", []),
            "no_rag_latency_ms": round(lat_no, 1),
            "rag_answer": (parsed_rag or {}).get("answer", raw_rag),
            "rag_sources": (parsed_rag or {}).get("sources", []),
            "rag_context_doc_ids": [r["metadata"]["doc_id"] for r in results],
            "rag_latency_ms": round(lat_rag, 1),
        })
    return records


# ---------------------------------------------------------------------------
# 3. Missing-info case.
# ---------------------------------------------------------------------------
def missing_info_case(final_floor):
    question = "What's the interest rate on your crypto savings product?"
    results = retriever_mod.retrieve(question, similarity_floor=final_floor)
    if results:
        context = "\n\n".join(f"[RETRIEVED_POLICY_CONTEXT doc_id={r['metadata']['doc_id']}]\n{r['document']}" for r in results)
        user_content = f"{context}\n\n{question}"
    else:
        user_content = question
    raw, parsed, latency_ms = call_llm(P3_PROMPT, user_content)
    return {
        "question": question,
        "n_retrieved": len(results),
        "retrieved_doc_ids": [r["metadata"]["doc_id"] for r in results],
        "answer": (parsed or {}).get("answer", raw),
        "escalate": (parsed or {}).get("escalate"),
        "latency_ms": round(latency_ms, 1),
    }


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    floor_results = {f: eval_floor(f) for f in CANDIDATE_FLOORS}
    with open(LOG_DIR / "04_floor_tuning.json", "w", encoding="utf-8") as f:
        json.dump(floor_results, f, ensure_ascii=False, indent=2)

    print("Floor tuning:")
    print(f"{'floor':>6} {'hit@1':>7} {'hit@3':>7} {'MRR':>7} {'probes empty (of 3)':>20}")
    for floor, r in floor_results.items():
        print(f"{floor:>6} {r['hit_at_1']:>7.2%} {r['hit_at_3']:>7.2%} {r['mrr']:>7.3f} {r['probes_correctly_empty']:>20}")

    # Chosen floor: 0.35. Measured finding (see evidence/04_retrieval_eval.md):
    # no candidate floor up to 0.45 empties all 3 out-of-corpus probes, and
    # pushing to 0.45 to reduce leakage tanks hit@1 from 90% to 65% while
    # STILL leaving 2 of 3 probes leaking. The similarity floor alone cannot
    # cleanly separate in-corpus from out-of-corpus for this embedding model
    # and corpus size. Verified separately (see evidence doc) that P3's hard
    # grounding rule correctly abstains even under the worst-case leak (4
    # irrelevant chunks) -- so the floor's job is retrieval quality, not the
    # last line of defence against fabrication; that's the prompt's job.
    chosen = 0.35
    print(f"\nChosen floor: {chosen} (see evidence/04_retrieval_eval.md for why 0.45 was rejected)")

    rag_records = rag_vs_norag(chosen)
    with open(LOG_DIR / "04_rag_vs_norag.jsonl", "w", encoding="utf-8") as f:
        for r in rag_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    missing_info = missing_info_case(chosen)
    with open(LOG_DIR / "04_missing_info_case.json", "w", encoding="utf-8") as f:
        json.dump(missing_info, f, ensure_ascii=False, indent=2)

    print(f"\nRAG vs no-RAG: {len(rag_records)} question(s) logged to {LOG_DIR / '04_rag_vs_norag.jsonl'}")
    print(f"Missing-info case logged to {LOG_DIR / '04_missing_info_case.json'}")
    print(f"Floor tuning data logged to {LOG_DIR / '04_floor_tuning.json'}")


if __name__ == "__main__":
    main()
