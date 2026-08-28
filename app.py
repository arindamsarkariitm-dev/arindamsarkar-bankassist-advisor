"""
Streamlit demo UI for BankAssist Advisor -- single file, for screenshots
(capstone_build_plan.md §8). Calls src/graph.py directly (not the FastAPI
layer) so it works standalone with `streamlit run app.py`, no server to
start separately.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

import streamlit as st  # noqa: E402

# On Streamlit Community Cloud there is no .env file -- secrets are entered
# via the app's own Secrets panel and read through st.secrets instead. Bridge
# them into os.environ (only when not already set, e.g. by a local .env)
# before importing graph.py, since every node module reads OPENAI_API_KEY /
# OPENAI_MODEL_AGENT / OPENAI_MODEL_JUDGE from os.environ, some at import time.
import os  # noqa: E402

try:
    for _key in ("OPENAI_API_KEY", "OPENAI_MODEL_AGENT", "OPENAI_MODEL_JUDGE"):
        if _key not in os.environ and _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
except st.errors.StreamlitSecretNotFoundError:
    pass  # local run, no .streamlit/secrets.toml -- .env covers it instead

from graph import give_feedback, run_turn  # noqa: E402
from tools._data import CUSTOMERS  # noqa: E402

st.set_page_config(page_title="BankAssist Advisor", page_icon="🏦", layout="centered")
st.title("🏦 BankAssist Advisor")
st.caption("Contact-centre associate co-pilot — demo UI. Synthetic data only, no real customers.")

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: role, content, trace_id, result

with st.sidebar:
    st.subheader("Session")
    customer_id = st.selectbox(
        "Authenticated customer (verified upstream)",
        options=list(CUSTOMERS.keys()),
        format_func=lambda cid: f"{cid} — {CUSTOMERS[cid]['name']}",
    )
    if st.button("Start new session / Reset"):
        st.session_state.session_id = None
        st.session_state.history = []
        st.rerun()
    if st.session_state.session_id:
        st.caption(f"session_id: `{st.session_state.session_id[:8]}...`")
    if st.button("Send /forget"):
        if st.session_state.session_id:
            run_turn("/forget", customer_id, session_id=st.session_state.session_id)
        st.session_state.history = []
        st.rerun()

for turn in st.session_state.history:
    with st.chat_message(turn["role"]):
        st.write(turn["content"])
        if turn["role"] == "assistant" and turn.get("result"):
            result = turn["result"]
            with st.expander("Trace details"):
                st.json({
                    "intent": result.get("intent"),
                    "risk_level": result.get("risk_level"),
                    "route": result.get("route"),
                    "tools_called": result.get("tools_called"),
                    "doc_ids_cited": result.get("doc_ids_cited"),
                    "refusal_code": result.get("refusal_code"),
                    "escalation_code": result.get("escalation_code"),
                    "confidence": (result.get("answer_json") or {}).get("confidence"),
                })
            col1, col2 = st.columns(2)
            trace_id = result.get("trace", {}).get("trace_id")
            if col1.button("👍", key=f"up_{trace_id}"):
                give_feedback(result, customer_id, "up")
                st.toast("Feedback recorded")
            if col2.button("👎", key=f"down_{trace_id}"):
                st.session_state[f"show_reason_{trace_id}"] = True
            if st.session_state.get(f"show_reason_{trace_id}"):
                reason = st.selectbox(
                    "Reason", ["too_long", "not_grounded", "wrong_intent", "unhelpful", "too_cautious"],
                    key=f"reason_{trace_id}",
                )
                if st.button("Submit", key=f"submit_{trace_id}"):
                    give_feedback(result, customer_id, "down", reason)
                    st.toast("Feedback recorded")
                    st.session_state[f"show_reason_{trace_id}"] = False

user_input = st.chat_input("Type the associate's question...")
if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})
    with st.spinner("Thinking..."):
        result = run_turn(user_input, customer_id, session_id=st.session_state.session_id)
    st.session_state.session_id = result["session_id"]
    st.session_state.history.append({"role": "assistant", "content": result.get("final_response", ""), "result": result})
    st.rerun()
