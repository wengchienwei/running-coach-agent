"""Screen 3: User profile (read only).

Reads the seed JSON directly via core/data_io.load_profile() and does not
touch st.session_state, so it runs standalone even before Home.py has run
in this session.

Profile fields: first_name, city, gender, goals, constraints.
The Modify button is a placeholder, disabled until a save_profile()
function and an edit form exist.
"""

import os
import sys

# Make `core` importable regardless of where streamlit is launched from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st

from core.auth import require_auth

require_auth()

from core.agent import DEFAULT_USER_ID
from core.data_io import load_profile

st.title("User Profile")

try:
    profile = load_profile()
except Exception as e:
    profile = {}
    print(f"ERROR loading profile for user {DEFAULT_USER_ID}: {e}")
    st.error("Could not load profile. Please try refreshing the page.")

if profile:
    st.write("**First name:**", profile.get("first_name", "(unknown)"))
    st.write("**City:**", profile.get("city", "(unknown)"))
    st.write("**Gender:**", profile.get("gender", "(unknown)"))
    st.write("**Goals:**", profile.get("goals", "(unknown)"))
    st.write("**Constraints:**", profile.get("constraints", "(unknown)"))
else:
    st.info("No profile data found yet.")

st.divider()
st.button("Modify", disabled=True)