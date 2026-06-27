"""Local database connection test.

Verifies that the app can read and write to the remote Postgres database.
Run from the repo root after adding DATABASE_URL to your .env file:

    python tests/test_db.py

All writes use a clearly labelled test marker so rows are easy to identify
and clean up in the Supabase table editor afterward.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from core.data_io import (
    load_profile,
    load_training_history,
    save_message,
    save_plan,
)


def separator(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print('=' * 50)


def test_load_profile() -> None:
    separator("TEST: load_profile")
    profile = load_profile()
    assert isinstance(profile, dict), "Expected a dict"
    assert "first_name" in profile, "Missing first_name"
    assert profile["first_name"], "first_name is empty"
    print(f"  first_name : {profile.get('first_name')}")
    print(f"  city       : {profile.get('city')}")
    print(f"  gender     : {profile.get('gender')}")
    print(f"  goals      : {profile.get('goals')}")
    print(f"  constraints: {profile.get('constraints')}")
    print("  PASSED")


def test_load_training_history() -> None:
    separator("TEST: load_training_history")
    result = load_training_history()
    assert isinstance(result, dict), "Expected a dict"
    assert "sessions" in result, "Missing sessions key"
    sessions = result["sessions"]
    assert isinstance(sessions, list), "sessions must be a list"
    print(f"  session count: {len(sessions)}")
    if sessions:
        first = sessions[0]
        print(f"  first session: {first}")
        assert "date" in first, "Missing date field"
        assert "km" in first, "Missing km field"
        assert "pace" in first, "Missing pace field"
        assert "type" in first, "Missing type field"
        assert isinstance(first["km"], float), "km must be a float"
    print("  PASSED")


def test_save_message() -> None:
    separator("TEST: save_message")
    # Write two rows, one per role.
    save_message("user", "[test] local DB write check - user turn")
    save_message("model", "[test] local DB write check - model turn")
    print("  Inserted 2 rows into messages.")
    print("  Check the Supabase table editor to confirm, then delete them.")
    print("  PASSED")


def test_save_plan() -> None:
    separator("TEST: save_plan")
    mock_goal = {
        "distance": "10K",
        "target_time": "50:00",
        "timeframe_weeks": 10,
        "race_date": None,
        "missing_fields": [],
    }
    save_plan("[test] local DB write check - plan text", mock_goal)
    print("  Inserted 1 row into plans.")
    print("  Check the Supabase table editor to confirm, then delete it.")
    print("  PASSED")


def main() -> None:
    print("\nRunning database connection tests against the remote Postgres instance.")
    print("DATABASE_URL is", "SET" if os.environ.get("DATABASE_URL") else "NOT SET")

    if not os.environ.get("DATABASE_URL"):
        print("\nERROR: DATABASE_URL is not set. Add it to your .env file and retry.")
        sys.exit(1)

    passed = 0
    failed = 0

    tests = [
        test_load_profile,
        test_load_training_history,
        test_save_message,
        test_save_plan,
    ]

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    separator("RESULTS")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
