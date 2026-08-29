# BankAssist Advisor

An AI banking support & advisory co-pilot for contact-centre associates (Scenario 2, non-transactional). Built with **LangChain + LangGraph** (Track A). See `capstone_build_plan.md` and `scenario_analysis.md` (in the parent project folder) for the full design rationale, and `docs/09_engineering_justification.md` for the case for every major decision.

**Synthetic data only. No real customers, accounts, or transactions anywhere in this repository.**

## Live demo

**https://arindamsarkar-bankassist-advisor-x7yak6ejhgdnfoy4bpaapy.streamlit.app/** — Streamlit UI only, deployed on Streamlit Community Cloud. The FastAPI layer (`src/api.py`) is not cloud-hosted; run it locally per the instructions below if you need `/chat`/`/feedback`/`/health` directly.

## Quickstart (3 commands)

```bash
pip install -r requirements.txt
copy .env.example .env   # then edit .env and add your real OpenAI key (never commit this file)
streamlit run app.py
```

The policy vector store (`vectorstore/`) is committed, so no ingestion step is needed to try the demo. If you ever need to rebuild it from `data/policy_corpus/*.md`, run `python src/ingest.py`.

### Running the API instead of / alongside the Streamlit UI

```bash
uvicorn src.api:app --reload
```
Then `POST http://localhost:8000/chat` with `{"turn_input": "...", "customer_id": "CUST-0001"}`, `POST /feedback`, `GET /health`.

### Docker

```bash
docker-compose up --build
```
Starts the API on `:8000` and the Streamlit UI on `:8501`. `.env` is read at container start via `env_file` — it is never baked into the image.

## Architecture

A single LangGraph `StateGraph` (`src/graph.py`) — see `docs/08_deployment.md` for the full node diagram and `Phase_5/evidence/05_graph_diagram.md` for the Phase-5-era version. In short: `ingest → redact_in → classify_intent → policy_gate`, branching to deterministic refuse/escalate/clarify paths or an agentic `plan → agent ⇄ tools` loop, followed by `verify_grounding → confidence_gate → respond`, with every path converging on a PII-safe structured log.

## Repository layout

```
src/            the permanent system: graph, nodes, tools, memory, feedback,
                adaptation, redaction, observability, resilience, API
data/           synthetic customers/transactions/disputes, policy corpus,
                the escalation/feedback/memory stores the system writes to
prompts/        the three Phase 3 prompt variants (P3 is what src/ uses)
vectorstore/    committed Chroma index over the policy corpus
tests/          the golden test set (eval_set.yaml)
logs/           redacted JSONL trace log the running system writes to
Phase_1..9/     phase-by-phase docs and evidence, per capstone_build_plan.md
app.py          Streamlit demo UI
```

## Environment variables

See `.env.example`. `OPENAI_API_KEY` is required; `OPENAI_MODEL_AGENT` (default `gpt-4o-mini`) and `OPENAI_MODEL_JUDGE` (default `gpt-4o`, used by the Phase 9 eval harness) are overridable.

**LangSmith tracing**: attempted, then hard-disabled after live testing found it doesn't reliably redact AI-generated/tool-derived content (only the associate's own question redacted correctly) — see `Phase_8/docs/08_deployment.md` for the full investigation. `ENABLE_SAFE_LANGSMITH_TRACING` in `.env.example` has no effect regardless of its value; the project's own JSONL structured logger is the real, verified-safe observability mechanism.

## Known limitations

See `docs/08_deployment.md` for the full assumptions/limitations writeup, and `docs/09_evaluation_report.md` for the measured evaluation results and root-cause analysis.
