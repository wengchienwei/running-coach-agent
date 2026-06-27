"""Screen 1: Chat with the coach. Entry point for the whole app.

Streamlit reruns this whole script on every interaction, so st.session_state
is the only place that persists data across reruns. This file owns
initializing every shared session_state key the other screens read from.

Session state contract:
  KEY_CHAT_HISTORY: list of dicts, each {"role": "user" or "model", "content": str}
  KEY_GOAL: dict or None, updated after every user message via extract_goal
  KEY_PLAN: dict or str or None, written by the agent on success
  KEY_PROFILE: dict, loaded once from the database via data_io
  KEY_TRAINING_HISTORY: dict, loaded once from the database via data_io

Chat turn flow:
  user message -> reschedule router -> run_agent or -> extract_goal -> send_message

Generate button flow:
  run_agent -> draft_plan (plan returned) or ask_for_info (reply returned)
"""

import hmac
import os
import sys

# Home.py sits one level under the repo root (app/Home.py), so one level up
# reaches the repo root where the core package lives.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import streamlit as st

from core.agent import DEFAULT_USER_ID, run_agent
from core.coach import check_reschedule, extract_goal, send_message
from core.data_io import load_profile, load_training_history, save_message

KEY_CHAT_HISTORY = "chat_history"
KEY_GOAL = "goal"
KEY_PLAN = "current_plan"
KEY_PROFILE = "profile"
KEY_TRAINING_HISTORY = "training_history"


# --- Password gate ---
# Runs before anything else on the page, including session state init, so no
# chat call or data load happens until the runner is authenticated.
if "authed" not in st.session_state:
    st.session_state.authed = False

if not st.session_state.authed:
    st.title("Conversational Running Coach")

    secret = os.environ.get("APP_PASSWORD")
    if secret is None:
        st.error("APP_PASSWORD is not configured. Contact the team.")
        st.stop()

    pw = st.text_input("Password", type="password")
    if pw:
        if hmac.compare_digest(pw, secret):
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


# --- Session state initialization ---
if KEY_CHAT_HISTORY not in st.session_state:
    st.session_state[KEY_CHAT_HISTORY] = [
        {"role": "model", "content": "Hi! What are you training for?"}
    ]

if KEY_GOAL not in st.session_state:
    st.session_state[KEY_GOAL] = None

if KEY_PLAN not in st.session_state:
    st.session_state[KEY_PLAN] = None

if KEY_PROFILE not in st.session_state:
    st.session_state[KEY_PROFILE] = load_profile()

if KEY_TRAINING_HISTORY not in st.session_state:
    st.session_state[KEY_TRAINING_HISTORY] = load_training_history()


# --- Page content ---
st.title("Conversational Running Coach")

for message in st.session_state[KEY_CHAT_HISTORY]:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_input = st.chat_input("Type your message...")

if user_input:
    st.session_state[KEY_CHAT_HISTORY].append({"role": "user", "content": user_input})

    # Reschedule router runs first, before extract_goal, so that when a plan
    # update is needed we skip the extract_goal LLM call entirely: the agent
    # runs with force_plan=True regardless of missing_fields.
    has_existing_plan = bool(st.session_state[KEY_PLAN])
    reschedule = has_existing_plan and check_reschedule(user_input)

    if reschedule:
        with st.spinner("Updating your plan based on this change..."):
            try:
                result = run_agent(
                    message=user_input,
                    runner_id=DEFAULT_USER_ID,
                    profile=st.session_state[KEY_PROFILE],
                    chat_history=st.session_state[KEY_CHAT_HISTORY],
                    goal=st.session_state[KEY_GOAL],
                    force_plan=True,
                )
                if result.get("plan"):
                    st.session_state[KEY_PLAN] = result["plan"]
                    reply = (
                        "I have updated your training plan to account for this change. "
                        "Check the Plan page to see the revised schedule."
                    )
                else:
                    reply = result.get(
                        "reply",
                        "Noted. I was not able to update the plan automatically. "
                        "Try clicking 'Generate a training plan'.",
                    )
            except Exception as e:
                print(f"ERROR in reschedule agent: {e}")
                reply = send_message(
                    st.session_state[KEY_CHAT_HISTORY],
                    st.session_state[KEY_GOAL],
                    st.session_state[KEY_PROFILE],
                )
    else:
        # Normal conversational flow: extract goal then reply.
        st.session_state[KEY_GOAL] = extract_goal(
            st.session_state[KEY_CHAT_HISTORY],
            st.session_state[KEY_GOAL],
        )
        reply = send_message(
            st.session_state[KEY_CHAT_HISTORY],
            st.session_state[KEY_GOAL],
            st.session_state[KEY_PROFILE],
        )

    st.session_state[KEY_CHAT_HISTORY].append({"role": "model", "content": reply})

    try:
        save_message("user", user_input)
        save_message("model", reply)
    except Exception as e:
        print(f"ERROR saving messages to database: {e}")
        st.warning("Could not save this message. Your conversation continues but may not be stored.")

    st.rerun()


# --- Generate plan button ---
st.divider()

no_conversation_yet = len(st.session_state[KEY_CHAT_HISTORY]) <= 1

if no_conversation_yet:
    st.caption("Chat with the coach first so there is a goal to build a plan from.")

if st.button("Generate a training plan", type="primary", disabled=no_conversation_yet):
    last_user_msg = next(
        (m["content"] for m in reversed(st.session_state[KEY_CHAT_HISTORY]) if m["role"] == "user"),
        "Please generate a training plan for me.",
    )
    with st.spinner("The coach is reading your history and drafting a plan..."):
        try:
            result = run_agent(
                message=last_user_msg,
                runner_id=DEFAULT_USER_ID,
                profile=st.session_state[KEY_PROFILE],
                chat_history=st.session_state[KEY_CHAT_HISTORY],
                goal=st.session_state[KEY_GOAL],
                force_plan=False,
            )
            if result.get("plan"):
                # Agent produced a complete plan.
                st.session_state[KEY_PLAN] = result["plan"]
                st.success("Plan generated. Check the Plan page.")
            elif result.get("reply"):
                # Agent needs more information before it can produce a plan.
                # Display the reply as a coach message in the chat.
                st.session_state[KEY_CHAT_HISTORY].append({
                    "role": "model",
                    "content": result["reply"],
                })
                try:
                    save_message("model", result["reply"])
                except Exception:
                    pass
                st.rerun()
        except Exception as e:
            print(f"ERROR running agent: {e}")
            st.error("Could not generate plan. Please try again.")

elif st.session_state.get(KEY_PLAN):
    st.info("You already have a plan. Check the Plan page, or keep chatting to update it.")