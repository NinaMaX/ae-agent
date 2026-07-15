import os
import threading

import anthropic
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

import agent  # loads .env as a side effect (imports snowflake_tools -> connection.py, which does)


@st.cache_resource
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _call_agent_in_background(active: dict) -> None:
    # Runs in its own thread so the main script never blocks on the network
    # call. Streamlit doesn't finish clearing a run's stale elements (like
    # the empty-state grid this replaces) until that run finishes - and a
    # run with a multi-second blocking call keeps them lingering the whole
    # time, no matter how many quick `st.rerun()`s precede it (confirmed by
    # directly testing several rerun-chaining approaches - none worked). A
    # real background thread is the only way the run showing this never
    # blocks at all.
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
    finally:
        st.session_state._agent_thread_running = False


def render_chat(active: dict) -> None:
    for turn_index, turn in enumerate(agent.group_into_turns(active["messages"])):
        with st.chat_message("user"):
            st.markdown(turn["user"])
        if turn["reply"]:
            # Only once there's an actual reply - not the instant tool calls
            # get made mid-turn - so Sources always lands together with the
            # answer it backs, never as a preview of it.
            with st.chat_message("assistant"):
                st.markdown(turn["reply"])
                if turn["tool_calls"]:
                    label = f"Sources ({len(turn['tool_calls'])} tool call{'s' if len(turn['tool_calls']) != 1 else ''})"
                    with st.expander(label):
                        for call in turn["tool_calls"]:
                            st.caption(f"`{call['name']}`  {call['input']}")
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

    # A trailing user message with no reply yet means input was just
    # captured (below) and this is the follow-up pass - answer it now,
    # right under the message that's already visible above.
    #
    # `_agent_thread_running` - not the trailing role - is the only thing
    # that decides whether to keep waiting. The background thread mutates
    # `active["messages"]` in place across a multi-round tool-use loop
    # (assistant-with-tool-use, then user-with-tool-results, repeating), so
    # its trailing role flips back and forth *while the thread is still
    # working*. Polling on the trailing role directly is a real race:
    # catching the list between rounds (trailing role briefly "assistant",
    # real work not actually finished) looks identical to "done," and
    # freezes the UI showing tool calls but no final reply.
    needs_reply = active["messages"] and active["messages"][-1]["role"] == "user"
    thread_running = st.session_state.get("_agent_thread_running", False)

    if needs_reply or thread_running:
        with st.chat_message("assistant"):
            if needs_reply and not thread_running:
                st.session_state._agent_thread_running = True
                thread = threading.Thread(target=_call_agent_in_background, args=(active,), daemon=True)
                add_script_run_ctx(thread)  # without this, the thread can't safely touch session_state
                thread.start()

            # A nested fragment with `run_every` ticks on its own, without
            # re-running the rest of the page - unlike a manual sleep +
            # `st.rerun()` loop, which forces a *full-page* rerun every
            # single tick. That full-page churn is what was making the
            # example grid and the chat input flicker for the whole wait,
            # and - more importantly - it never let the page settle long
            # enough for the stale grid to actually get cleared, since a
            # run that immediately re-runs itself never reaches the "done"
            # state Streamlit needs to clean up what came before it. This
            # function reaching a normal, natural end (right after this
            # call) is what lets that happen, exactly once, right away.
            @st.fragment(run_every=0.3)
            def _poll_for_reply():
                if st.session_state.get("_agent_thread_running"):
                    st.caption("⏳ Pulling account context...")
                else:
                    st.rerun()

            _poll_for_reply()


def new_conversation() -> None:
    active = st.session_state.conversations[st.session_state.active_index]
    if not active["messages"]:
        return  # already sitting on an empty chat - nothing to save, nothing to do
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

st.set_page_config(page_title="Personio AE Call-Prep Agent", page_icon="📞")

if "conversations" not in st.session_state:
    st.session_state.conversations = [{"messages": [], "rated_turns": set()}]
    st.session_state.active_index = 0

with st.sidebar:
    if st.button("＋ New chat", width="stretch"):
        new_conversation()
        st.rerun()

    # Always visible, even with just the one starter chat - establishes the
    # pattern from the first run instead of the list appearing (and shifting
    # everything below it) only once a second conversation exists.
    st.divider()
    st.caption("History")
    for i in reversed(range(len(st.session_state.conversations))):
        conv = st.session_state.conversations[i]
        title = conversation_title(conv)
        label = f"● {title}" if i == st.session_state.active_index else title
        if st.button(label, key=f"conv_{i}", width="stretch"):
            st.session_state.active_index = i
            st.rerun()

    st.divider()
    st.caption("Uses live account data plus Personio's playbook, battlecards, and pricing guide. Ask follow-ups any time.")

st.title("📞 Personio AE Call-Prep Agent")
st.caption("Internal AI Team · AE call-prep assistant")

active = st.session_state.conversations[st.session_state.active_index]

main_area = st.empty()

if not active["messages"]:
    with main_area.container():
        # Empty-state examples live here, not the sidebar, and only while this
        # chat has nothing in it yet - two problems solved at once: they can't
        # pile up and push the sidebar's history list off-screen as you use the
        # app, and clicking one can never inject into an already-running
        # conversation, since they're only ever visible before one exists. No
        # bounding box here - there's nothing to scroll yet, so a boxed 520px
        # frame around four buttons would just look like empty chrome.
        st.subheader("Try asking", anchor=False)
        st.caption("First time here? Start with one of these:")
        cols = st.columns(2)
        for i, prompt in enumerate(EXAMPLE_PROMPTS):
            if cols[i % 2].button(prompt, width="stretch", key=f"example_{i}"):
                # Append + rerun immediately, rather than waiting on the agent
                # call below, so the example grid disappears and the user's
                # message appears on the very next script pass instead of only
                # once the reply comes back.
                active["messages"].append({"role": "user", "content": prompt})
                st.rerun()
else:
    with main_area.container():
        render_chat(active)

if error_message := st.session_state.pop("error_message", None):
    st.error(error_message)

user_input = st.chat_input("Ask about an account, e.g. 'prep me for my call with...'")
if user_input:
    # Append + rerun immediately (rather than calling the agent right here)
    # so the user's message shows up on the next pass before the agent call
    # even starts, instead of appearing only once the reply comes back.
    active["messages"].append({"role": "user", "content": user_input})
    st.rerun()
