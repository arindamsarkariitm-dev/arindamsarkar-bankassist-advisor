"""
Feedback storage for BankAssist Advisor: 👍/👎 + a reason code, persisted
redacted, keyed by intent + topic. This is the data layer three adaptation
mechanisms in src/adaptation.py read from -- this module only stores and
retrieves, it doesn't decide how behaviour changes.

`topic` is derived consistently from whatever grounded the turn's answer:
the first policy doc_id cited, or the first tool called, or (for turns with
neither) the intent itself. The SAME derivation is used both when storing
feedback and when a later turn checks "has this topic had trouble before,"
so the two sides actually connect.
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402

from redaction import redact_text  # noqa: E402

load_dotenv(ROOT / ".env")
FEEDBACK_STORE_PATH = ROOT / "data" / "feedback_store.jsonl"
HASH_SALT = "bankassist-advisor-demo-salt"
_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

ReasonCode = Literal["too_long", "not_grounded", "wrong_intent", "unhelpful", "too_cautious"]


def derive_topic(intent: str, doc_ids_cited: list[str] | None, tools_called: list[str] | None) -> str:
    if doc_ids_cited:
        return doc_ids_cited[0]
    if tools_called:
        return tools_called[0]
    return intent


def _hash_customer_id(customer_id: str) -> str:
    return hashlib.sha256(f"{HASH_SALT}:{customer_id}".encode("utf-8")).hexdigest()[:16]


def submit_feedback(
    session_id: str,
    customer_id: str,
    turn_input: str,
    final_response: str,
    intent: str,
    doc_ids_cited: list[str] | None,
    tools_called: list[str] | None,
    signal: Literal["up", "down"],
    reason_code: ReasonCode | None = None,
    corrected_answer: str | None = None,
) -> dict:
    topic = derive_topic(intent, doc_ids_cited, tools_called)
    redacted_question = redact_text(turn_input)
    # Embedding only computed for the case few-shot retrieval actually needs
    # (a not_grounded correction) -- no point spending an API call on every
    # thumbs-up.
    question_embedding = (
        _embeddings.embed_query(redacted_question)
        if reason_code == "not_grounded" and corrected_answer else None
    )
    record = {
        "feedback_id": hashlib.sha256(f"{session_id}:{time.time()}".encode()).hexdigest()[:12],
        "session_id": session_id,
        "customer_id_hash": _hash_customer_id(customer_id),
        "intent": intent,
        "topic": topic,
        "signal": signal,
        "reason_code": reason_code,
        "redacted_question": redacted_question,
        "redacted_response": redact_text(final_response),
        "redacted_correction": redact_text(corrected_answer) if corrected_answer else None,
        "question_embedding": question_embedding,
        "timestamp": time.time(),
    }
    FEEDBACK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_STORE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _load_all() -> list[dict]:
    if not FEEDBACK_STORE_PATH.exists():
        return []
    with open(FEEDBACK_STORE_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def count_reason_for_customer(customer_id: str, reason_code: str) -> int:
    ch = _hash_customer_id(customer_id)
    return sum(1 for r in _load_all() if r["customer_id_hash"] == ch and r["reason_code"] == reason_code)


def count_negative_for_topic(topic: str) -> int:
    return sum(1 for r in _load_all() if r["topic"] == topic and r["signal"] == "down")


def get_corrections_for_topic(topic: str) -> list[dict]:
    """not_grounded corrections carrying a corrected_answer, for a given topic."""
    return [r for r in _load_all() if r["topic"] == topic and r["reason_code"] == "not_grounded" and r["redacted_correction"]]


def get_all_corrections() -> list[dict]:
    return [r for r in _load_all() if r["reason_code"] == "not_grounded" and r["redacted_correction"]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def find_similar_correction(question_text: str, threshold: float = 0.85) -> dict | None:
    """Dynamic few-shot injection: is a past not_grounded correction close
    enough to this new question to reuse as an exemplar? Returns the best
    match above `threshold`, or None."""
    candidates = get_all_corrections()
    if not candidates:
        return None
    query_embedding = _embeddings.embed_query(redact_text(question_text))
    best, best_score = None, threshold
    for c in candidates:
        score = _cosine(query_embedding, c["question_embedding"])
        if score >= best_score:
            best, best_score = c, score
    return best
