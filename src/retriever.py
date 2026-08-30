"""
Phase 4 retriever for BankAssist Advisor, built on LangChain's Chroma
vectorstore integration.

k=4, MMR for diversity (via langchain_core's maximal_marginal_relevance
utility, applied over the similarity-floor-filtered candidate pool),
similarity floor 0.35 (per capstone_build_plan.md §4: "start 0.35 and tune").

FIXED IN PHASE 9 (was planted deliberately in Phase 4, see
docs/01_failure_register.md F2 and Phase_9/docs/09_evaluation_report.md's
root-cause section for the full symptom -> trace -> root cause -> fix
writeup): this retriever did NOT filter by effective_date / status, so both
the 2024 (superseded) and 2026 (current) fee schedule versions were indexed
and could both surface for the same query -- e.g. "late payment fee on
credit card" retrieved both, leaving the current answer correct only
because the LLM happened to read the status metadata correctly, not because
retrieval structurally prevented the stale one from ever being handed to it.
_filter_superseded() below removes that fragility at the source: a
superseded document is now excluded whenever a current one is also in the
candidate pool for the same query, so the LLM's prompt-level "cite the
current fee" instruction is defense-in-depth, not the only thing standing
between an associate and a wrong number.
"""
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.vectorstores.utils import maximal_marginal_relevance
from langchain_openai import OpenAIEmbeddings

ROOT = Path(__file__).resolve().parents[1]
VECTORSTORE_DIR = ROOT / "vectorstore"
COLLECTION_NAME = "policy_corpus"
EMBED_MODEL = "text-embedding-3-small"

K = 4
FETCH_K = 10
SIMILARITY_FLOOR = 0.35
LAMBDA_MULT = 0.5

load_dotenv(ROOT / ".env")

_embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
_store = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=_embeddings,
    persist_directory=str(VECTORSTORE_DIR),
)


def _filter_superseded(candidates: list[tuple]) -> list[tuple]:
    """Drop status='superseded' candidates whenever a status='current'
    candidate for the same doc_id is also present -- a superseded version
    should never compete for a retrieval slot (and never reach the LLM)
    when its own replacement is right there in the same result set. Not
    applied blindly: a superseded doc with no current counterpart in this
    candidate pool is left alone, since that's not the failure mode this
    guards against, and filtering it out could turn a real (if historical)
    answer into a false abstain."""
    current_doc_ids = {
        doc.metadata.get("doc_id")
        for doc, _ in candidates
        if doc.metadata.get("status") == "current"
    }
    return [
        (doc, score) for doc, score in candidates
        if not (doc.metadata.get("status") == "superseded" and doc.metadata.get("doc_id") in current_doc_ids)
    ]


def retrieve(query: str, k: int = K, fetch_k: int = FETCH_K, similarity_floor: float = SIMILARITY_FLOOR):
    """Returns a list of {document, metadata, score} dicts, highest-ranked
    first. An empty list means nothing cleared the similarity floor -- the
    caller must abstain and offer escalation, never fall back to the
    model's own knowledge (capstone_build_plan.md §4)."""
    candidates = _store.similarity_search_with_relevance_scores(query, k=fetch_k)
    candidates = [(doc, score) for doc, score in candidates if score >= similarity_floor]
    candidates = _filter_superseded(candidates)
    if not candidates:
        return []

    if len(candidates) <= k:
        selected = candidates
    else:
        texts = [doc.page_content for doc, _ in candidates]
        candidate_embeddings = _embeddings.embed_documents(texts)
        query_embedding = np.array(_embeddings.embed_query(query))
        idxs = maximal_marginal_relevance(
            query_embedding, candidate_embeddings, lambda_mult=LAMBDA_MULT, k=k
        )
        selected = [candidates[i] for i in idxs]

    return [
        {"document": doc.page_content, "metadata": doc.metadata, "score": round(score, 4)}
        for doc, score in selected
    ]


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "What's the foreign transaction fee on my debit card?"
    results = retrieve(query)
    print(f"Query: {query!r}\n{len(results)} result(s) cleared the floor:\n")
    for r in results:
        m = r["metadata"]
        print(f"  score={r['score']:.3f}  doc_id={m['doc_id']}  version={m['version']}  "
              f"effective_date={m['effective_date']}  status={m['status']}")
