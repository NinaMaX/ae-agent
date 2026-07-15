import os

import anthropic
import streamlit as st

import agent  # loads .env as a side effect (imports snowflake_tools -> connection.py, which does)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def new_conversation() -> None:
    st.session_state.conversations.append({"messages": [], "rated_turns": set()})
    st.session_state.active_index = len(st.session_state.conversations) - 1


def conversation_title(conv: dict) -> str:
    for msg in conv["messages"]:
        if msg["role"] == "user" and isinstance(msg["content"], str):
            text = msg["content"]
            return text[:40] + ("…" if len(text) > 40 else "")
    return "New chat"


EXAMPLE_PROMPTS = [
    "Prep me for my renewal call with Tide Logistics AG",
    "I've got a discovery call with Verdant Financial Services SAS, what do I need to know?",
    "What does the playbook say about handling a stalled renewal?",
    "Tell me about Brightline Retail GmbH",
]

st.set_page_config(page_title="Personio Call Prep Co-Pilot", page_icon="📞")

if "conversations" not in st.session_state:
    st.session_state.conversations = [{"messages": [], "rated_turns": set()}]
    st.session_state.active_index = 0

with st.sidebar:
    if st.button("＋ New chat", use_container_width=True):
        new_conversation()
        st.rerun()

    # Only worth showing a history list once there's more than the one
    # empty conversation everyone starts with - an AE prepping for a
    # back-to-back day of calls needs to get back to Account A's chat while
    # already deep into Account B's, not just start fresh forever.
    if len(st.session_state.conversations) > 1:
        st.divider()
        st.caption("History")
        for i in reversed(range(len(st.session_state.conversations))):
            conv = st.session_state.conversations[i]
            title = conversation_title(conv)
            label = f"● {title}" if i == st.session_state.active_index else title
            if st.button(label, key=f"conv_{i}", use_container_width=True):
                st.session_state.active_index = i
                st.rerun()

    st.divider()
    st.subheader("Try asking")
    st.caption("First time here? Start with one of these:")
    for prompt in EXAMPLE_PROMPTS:
        if st.button(prompt, use_container_width=True):
            st.session_state.pending_prompt = prompt
    st.divider()
    st.caption("Uses live account data plus Personio's playbook, battlecards, and pricing guide. Ask follow-ups any time.")

st.title("📞 Personio Call Prep Co-Pilot")
st.caption("Internal AI Team · AE call-prep assistant")

active = st.session_state.conversations[st.session_state.active_index]

for turn_index, turn in enumerate(agent.group_into_turns(active["messages"])):
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
                if turn_index in active["rated_turns"]:
                    st.caption("Thanks for the feedback.")
                else:
                    up_col, down_col, _ = st.columns([1, 1, 10])
                    if up_col.button("👍", key=f"up_{st.session_state.active_index}_{turn_index}"):
                        agent.log_feedback(turn["user"], turn["reply"], "up")
                        active["rated_turns"].add(turn_index)
                        st.rerun()
                    if down_col.button("👎", key=f"down_{st.session_state.active_index}_{turn_index}"):
                        agent.log_feedback(turn["user"], turn["reply"], "down")
                        active["rated_turns"].add(turn_index)
                        st.rerun()

if error_message := st.session_state.pop("error_message", None):
    st.error(error_message)

user_input = st.chat_input("Ask about an account, e.g. 'prep me for my call with...'")
if "pending_prompt" in st.session_state:
    user_input = st.session_state.pop("pending_prompt")

if user_input:
    active["messages"].append({"role": "user", "content": user_input})
    with st.spinner("Pulling account context..."):
        try:
            client = get_client()
            active["messages"] = agent.run_turn(client, active["messages"])
        except Exception:
            # A raw stack trace here would be worse than an honest "something
            # broke" - the interview research is explicit that a single bad
            # moment costs an AE's trust for months, and a naked traceback
            # reads as exactly that kind of bad moment.
            active["messages"].pop()  # drop the unanswered turn rather than leave it stuck, unanswered, in history
            st.session_state.error_message = "Something went wrong pulling that together - mind trying again or rephrasing?"
    st.rerun()
