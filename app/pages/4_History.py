"""Screen 4: Training history (read only).

Reads the data from the database via core/data_io.load_training_history() and
does not touch st.session_state, so it runs standalone even before Home.py
has run in this session.

JSON shape: a dict with a sessions list, each session has date, km, pace, type.
Table columns shown: date, km, pace, type, in that order.
"""

import os
import sys

# Make `core` importable regardless of where streamlit is launched from.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
 
from core.auth import require_auth
 
require_auth()

from core.agent import DEFAULT_USER_ID
from core.data_io import load_training_history

st.title("Training History")

try:
    history_data = load_training_history()
    sessions = history_data.get("sessions", [])
except Exception as e:
    sessions = []
    print(f"ERROR loading training history for user {DEFAULT_USER_ID}: {e}")
    st.error("Could not load training history. Please try refreshing the page.")

if sessions:
    # Keep a stable, expected column order; tolerate missing fields gracefully.
    expected_cols = ["date", "km", "pace", "type"]
    rows = [{col: row.get(col, "") for col in expected_cols} for row in sessions]
    st.dataframe(rows, width="stretch")
else:
    st.info("No training sessions found yet.")
