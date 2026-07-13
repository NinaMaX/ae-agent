import os

import anthropic
import streamlit as st
from dotenv import load_dotenv

import agent

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=True)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def is_displayable_user_turn(content) -> bool:
    """A user turn is either what the AE typed (a string) or a tool_result
    round-trip (a list of dicts) - only the former should render in the UI."""
    return isinstance(content, str)


st.set_page_config(page_title="Personio Call Prep Co-Pilot", page_icon="📞")
st.title("📞 Personio Call Prep Co-Pilot")
st.caption("Internal AI Team · AE call-prep assistant")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if msg["role"] == "user":
        if is_displayable_user_turn(msg["content"]):
            with st.chat_message("user"):
                st.markdown(msg["content"])
    else:
        text = "".join(b.text for b in msg["content"] if getattr(b, "type", None) == "text")
        if text:
            with st.chat_message("assistant"):
                st.markdown(text)

if user_input := st.chat_input("Ask about an account, e.g. 'prep me for my call with...'"):
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("assistant"):
        with st.spinner("Pulling account context..."):
            client = get_client()
            st.session_state.messages = agent.run_turn(client, st.session_state.messages)
            reply = agent.latest_reply_text(st.session_state.messages)
        st.markdown(reply)
