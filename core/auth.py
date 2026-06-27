"""Shared authentication check for every page except Home.

Home.py owns the login form itself and sets st.session_state.authed on
success. Every other page calls require_auth() at the top, before any
other content, since each page is directly reachable by URL.
"""

import streamlit as st


def require_auth() -> None:
    """Stop rendering this page unless the runner is authenticated.

    Shows a short message instead of leaving the page blank, since a bare
    st.stop() gives no explanation if someone reaches this page directly
    without logging in first.
    """
    if not st.session_state.get("authed", False):
        st.info("Please log in on the Home page first.")
        st.stop()
