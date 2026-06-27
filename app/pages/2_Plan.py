"""Screen 2: Current training plan.

Renders the structured TrainingPlan dict produced by the agent.
Falls back to plain text for plans generated before the agent upgrade.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from core.auth import require_auth

require_auth()

KEY_PLAN = "current_plan"

st.title("Current Training Plan")

plan = st.session_state.get(KEY_PLAN)

if plan is None:
    st.info("No plan generated yet. Go chat with the coach first.")

elif isinstance(plan, dict) and "weeks" in plan:
    st.subheader(plan.get("goal", "Training Plan"))
    for week in plan["weeks"]:
        label = f"Week {week['week']} · {week['phase']} · {week['km']} km"
        with st.expander(label):
            for session in week.get("sessions", []):
                st.write(f"• {session}")

else:
    # Legacy plain-text plan
    st.text(plan)
