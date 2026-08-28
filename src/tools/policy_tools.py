"""Policy-lane tool: search_bank_policy. Wraps the Phase 4 retriever
(src/retriever.py) -- no customer binding needed, since policy documents
aren't customer-specific data."""
import sys
from pathlib import Path

from langchain_core.tools import tool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # .../src
import retriever as _retriever  # noqa: E402

from .schemas import PolicyChunk


@tool
def search_bank_policy(query: str, product: str | None = None) -> list[dict]:
    """Search the bank's policy documents (fee schedules, card terms, KYC,
    dispute procedure, hardship policy, etc.) for the passage most relevant
    to `query`. `query` MUST be the full natural-language question, not
    keywords -- e.g. "What's the foreign transaction fee on a debit card?",
    NOT "foreign transaction fee". This retriever is a dense embedding
    search over prose documents; short keyword fragments score measurably
    worse against it than a complete question does, even for the exact same
    underlying request. Optionally hint the product area with `product`.
    Returns an empty list if nothing clears the relevance floor -- that
    means the answer is not in the corpus and the response must abstain,
    never guess."""
    results = _retriever.retrieve(query)
    chunks = []
    for r in results:
        m = r["metadata"]
        chunks.append(PolicyChunk(
            doc_id=m["doc_id"], version=m["version"], effective_date=m["effective_date"],
            status=m["status"], text=r["document"], score=r["score"],
        ).model_dump())
    return chunks
