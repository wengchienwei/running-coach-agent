"""Load user profile and training history from the remote Postgres database."""

import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# Fill in your .env file with the following line:
# DATABASE_URL=postgresql://postgres:your_password@your_host:5432/postgres
DATABASE_URL = os.environ["DATABASE_URL"]
DEFAULT_USER_ID = 1


def _get_connection():
    return psycopg2.connect(DATABASE_URL)


def load_profile(user_id: int = DEFAULT_USER_ID) -> dict:
    """Return the user profile dict for the given user_id.

    Expected fields: first_name, city, gender, goals, constraints.
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT first_name, city, gender, goals, constraints "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise ValueError(f"No user found with id={user_id}.")
    return dict(row)


def load_training_history(user_id: int = DEFAULT_USER_ID) -> dict:
    """Return training history dict with a 'sessions' list for the given user_id.

    Each session has: date, km, pace, type.
    """
    with _get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT session_date AS date, km, pace, session_type AS type "
                "FROM training_history WHERE user_id = %s ORDER BY session_date",
                (user_id,),
            )
            rows = cur.fetchall()
    sessions = []
    for row in rows:
        sessions.append({
            "date": str(row["date"]),
            "km": float(row["km"]),
            "pace": row["pace"],
            "type": row["type"],
        })
    return {"sessions": sessions}


def save_training_history(sessions: list, user_id: int = DEFAULT_USER_ID) -> None:
    """Insert new training sessions for the given user into the database."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            for session in sessions:
                cur.execute(
                    "INSERT INTO training_history (user_id, session_date, km, pace, session_type) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (user_id, session["date"], session["km"], session["pace"], session["type"]),
                )


def save_plan(plan_text: str, goal_json: dict = None, user_id: int = DEFAULT_USER_ID) -> None:
    """Insert a generated plan for the given user into the database."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO plans (user_id, plan_text, goal_json) "
                "VALUES (%s, %s, %s)",
                (user_id, plan_text, psycopg2.extras.Json(goal_json) if goal_json else None),
            )


def save_message(role: str, content: str, user_id: int = DEFAULT_USER_ID) -> None:
    """Insert a single chat message for the given user into the database.

    role must be 'user' or 'model', matching the check constraint on the messages table.
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (user_id, role, content) "
                "VALUES (%s, %s, %s)",
                (user_id, role, content),
            )
