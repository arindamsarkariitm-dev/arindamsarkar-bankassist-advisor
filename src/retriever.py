"""
Phase 4 retriever for BankAssist Advisor, built on LangChain's Chroma
vectorstore integration.

k=4, MMR for diversity (via langchain_core's maximal_marginal_relevance
utility, applied over the similarity-floor-filtered candidate pool),
similarity floor 0.35 (per capstone_build_plan.md §4: "start 0.35 and tune").

INTENTIONAL BUG, left in on purpose (fixed in Phase 9): this retriever does
NOT filter by effective_date / status="current". Both the 2024 and 2026 fee
schedule versions are indexed, so a query about a currently-effective fee
can retrieve the superseded 2024 chunk instead of (or ranked above) the 2026
one. This is planted deliberately -- see docs/01_failure_register.md F2 and
capstone_build_plan.md §4 "Plant your Phase 9 failure case here" / §8. Do
not "fix" this without updating Phase_4's evidence and the Phase 9
root-cause writeup that depends on it still being reproducible.
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


def retrieve(query: str, k: int = K, fetch_k: int = FETCH_K, similarity_floor: float = SIMILARITY_FLOOR):
    """Returns a list of {document, metadata, score} dicts, highest-ranked
    first. An empty list means nothing cleared the similarity floor -- the
    caller must abstain and offer escalation, never fall back to the
    model's own knowledge (capstone_build_plan.md §4)."""
    candidates = _store.similarity_search_with_relevance_scores(query, k=fetch_k)
    candidates = [(doc, score) for doc, score in candidates if score >= similarity_floor]
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
