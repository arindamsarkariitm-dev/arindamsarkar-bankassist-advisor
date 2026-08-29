"""
LLM-call resilience: retry-with-backoff on timeout/rate-limit, and a
one-shot repair attempt on malformed structured output.
capstone_build_plan.md §8's degradation matrix:
  "LLM timeout / 429 -> 1 retry w/ backoff -> apologise + offer escalation.
   Never a partial answer."
  "Malformed LLM JSON -> 1 repair attempt -> safe fallback message."

Applied at every LLM call site in src/nodes/ so no single flaky API call
can crash a turn or return a half-formed answer.
"""
import time

from openai import APITimeoutError, RateLimitError

from langsmith_tracing import tracing_callbacks

RETRYABLE_EXCEPTIONS = (APITimeoutError, RateLimitError, TimeoutError)


class LLMUnavailable(Exception):
    """Raised after the one allowed retry still fails -- callers must show
    an apology + escalation offer, never a partial answer."""


def invoke_with_retry(llm, messages, max_retries: int = 1, backoff_seconds: float = 1.5):
    """Plain (non-structured-output) LLM call with one retry on
    timeout/429. Returns the AIMessage."""
    attempt = 0
    while True:
        try:
            return llm.invoke(messages, config={"callbacks": tracing_callbacks()})
        except RETRYABLE_EXCEPTIONS as e:
            if attempt >= max_retries:
                raise LLMUnavailable(f"{type(e).__name__} after {attempt + 1} attempt(s): {e}") from e
            time.sleep(backoff_seconds * (attempt + 1))
            attempt += 1


def invoke_structured_with_resilience(llm, messages, max_retries: int = 1, backoff_seconds: float = 1.5):
    """Structured-output LLM call (built with include_raw=True) with BOTH
    retry-on-timeout/429 AND a one-shot repair attempt if parsing fails
    (raw_result["parsed"] is None / raw_result["parsing_error"] is set).
    Returns (parsed, raw_ai_message). Raises LLMUnavailable if every
    attempt -- including the repair attempt -- fails."""
    attempt = 0
    last_raw_result = None
    while attempt <= max_retries:
        try:
            raw_result = llm.invoke(messages, config={"callbacks": tracing_callbacks()})
        except RETRYABLE_EXCEPTIONS as e:
            if attempt >= max_retries:
                raise LLMUnavailable(f"{type(e).__name__} after {attempt + 1} attempt(s): {e}") from e
            time.sleep(backoff_seconds * (attempt + 1))
            attempt += 1
            continue

        if raw_result.get("parsed") is not None:
            return raw_result["parsed"], raw_result["raw"]

        # Malformed / unparseable structured output -- one repair attempt,
        # explicitly asking the model to fix its own output, before giving up.
        last_raw_result = raw_result
        if attempt >= max_retries:
            break
        messages = messages + [{
            "role": "user",
            "content": "Your previous response did not parse as valid structured output. "
                       "Please respond again, following the required schema exactly.",
        }]
        attempt += 1

    raise LLMUnavailable(
        f"Structured output did not parse after {attempt + 1} attempt(s): "
        f"{(last_raw_result or {}).get('parsing_error')}"
    )
