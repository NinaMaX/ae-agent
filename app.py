import os

import anthropic
import streamlit as st

import agent  # loads .env as a side effect (imports snowflake_tools -> connection.py, which does)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


EXAMPLE_PROMPTS = [
    "Prep me for my renewal call with Tide Logistics AG",
    "I've got a discovery call with Fjord Logistics AS, what do I need to know?",
    "What does the playbook say about handling a stalled renewal?",
    "Tell me about Brightline Retail GmbH",
]

st.set_page_config(page_title="Personio Call Prep Co-Pilot", page_icon="📞")

with st.sidebar:
    if st.button("＋ New chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.rated_turns = set()
        st.rerun()
    st.divider()
    st.subheader("Try asking")
    st.caption("A new AE won't know what this can do on day one - a few real starting points:")
    for prompt in EXAMPLE_PROMPTS:
        if st.button(prompt, use_container_width=True):
            st.session_state.pending_prompt = prompt
    st.divider()
    st.caption("Pulls live from Snowflake (CRM/product/support) and Personio's sales enablement docs. Multi-turn - ask a follow-up.")

st.title("📞 Personio Call Prep Co-Pilot")
st.caption("Internal AI Team · AE call-prep assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

if "rated_turns" not in st.session_state:
    st.session_state.rated_turns = set()

for turn_index, turn in enumerate(agent.group_into_turns(st.session_state.messages)):
    with st.chat_message("user"):
        st.markdown(turn["user"])
    if turn["reply"] or turn["tool_calls"]:
        with st.chat_message("assistant"):
            if turn["reply"]:
                st.markdown(turn["reply"])
            if turn["tool_calls"]:
                label = f"Sources ({len(turn['tool_calls'])} tool call{'s' if len(turn['tool_calls']) != 1 else ''})"
                with st.expander(label):
                    for call in turn["tool_calls"]:
                        st.caption(f"`{call['name']}`  {call['input']}")
            if turn["reply"]:
                if turn_index in st.session_state.rated_turns:
                    st.caption("Thanks for the feedback.")
                else:
                    up_col, down_col, _ = st.columns([1, 1, 10])
                    if up_col.button("👍", key=f"up_{turn_index}"):
                        agent.log_feedback(turn["user"], turn["reply"], "up")
                        st.session_state.rated_turns.add(turn_index)
                        st.rerun()
                    if down_col.button("👎", key=f"down_{turn_index}"):
                        agent.log_feedback(turn["user"], turn["reply"], "down")
                        st.session_state.rated_turns.add(turn_index)
                        st.rerun()

if error_message := st.session_state.pop("error_message", None):
    st.error(error_message)

user_input = st.chat_input("Ask about an account, e.g. 'prep me for my call with...'")
if "pending_prompt" in st.session_state:
    user_input = st.session_state.pop("pending_prompt")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Pulling account context..."):
        try:
            client = get_client()
            st.session_state.messages = agent.run_turn(client, st.session_state.messages)
        except Exception:
            # A raw stack trace here would be worse than an honest "something
            # broke" - the interview research is explicit that a single bad
            # moment costs an AE's trust for months, and a naked traceback
            # reads as exactly that kind of bad moment.
            st.session_state.messages.pop()  # drop the unanswered turn rather than leave it stuck, unanswered, in history
            st.session_state.error_message = "Something went wrong pulling that together - mind trying again or rephrasing?"
    st.rerun()
