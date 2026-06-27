"""Agent integration tests.

Verifies that the LangGraph agent, tools, and reschedule router work
end to end against the real Gemini API and the remote database.

Run from the repo root after adding all three secrets to your .env file:

    python tests/test_agent.py

GEMINI_API_KEY, APP_PASSWORD, and DATABASE_URL must all be set.
Each test that calls the API costs a small number of tokens.
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()


def separator(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print("=" * 50)


# --- Pure function tests (no API, no DB) ---

def test_build_week_calendar() -> None:
    separator("TEST: build_week_calendar")
    from core.plan import build_week_calendar
    from datetime import date

    # Use a known Friday so we can verify the Monday anchor
    friday = date(2026, 6, 19)
    calendar = build_week_calendar(friday, 3)
    lines = calendar.strip().split("\n")

    assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"
    # First week should start on the upcoming Monday (Jun 22)
    assert "22 Jun" in lines[0], f"Expected Monday Jun 22 as week start, got: {lines[0]}"
    # Verify Mon appears as the first day label
    assert "Mon 22 Jun" in lines[0], f"Expected Mon 22 Jun as first day, got: {lines[0]}"
    # Week 3 should start on Jul 06
    assert "06 Jul" in lines[2], f"Expected week 3 to start Jul 06, got: {lines[2]}"
    print(f"  Week 1: {lines[0]}")
    print(f"  Week 3: {lines[2]}")
    print("  PASSED")


def test_router_tool_call_limit() -> None:
    separator("TEST: router tool call limit guard")
    from core.agent import router, CoachState
    from google.genai import types

    # Build a minimal state that has hit the tool call limit
    dummy_part = types.Part(text="some summary")
    dummy_content = types.Content(role="model", parts=[dummy_part])

    state = CoachState(
        contents=[dummy_content],
        plan=None,
        reply=None,
        runner_id=1,
        tool_call_count=10,   # at MAX_TOOL_CALLS
        goal_complete=False,
    )
    result = router(state)
    assert result == "draft_plan", f"Expected 'draft_plan' at limit, got '{result}'"
    print(f"  router at MAX_TOOL_CALLS -> '{result}'")
    print("  PASSED")


def test_router_goal_complete() -> None:
    separator("TEST: router goal_complete path")
    from core.agent import router, CoachState
    from google.genai import types

    dummy_part = types.Part(text="I have enough info now.")
    dummy_content = types.Content(role="model", parts=[dummy_part])

    state = CoachState(
        contents=[dummy_content],
        plan=None,
        reply=None,
        runner_id=1,
        tool_call_count=1,
        goal_complete=True,
    )
    result = router(state)
    assert result == "draft_plan", f"Expected 'draft_plan' with goal_complete, got '{result}'"
    print(f"  router with goal_complete=True -> '{result}'")
    print("  PASSED")


def test_router_ask_for_info() -> None:
    separator("TEST: router ask_for_info path")
    from core.agent import router, CoachState
    from google.genai import types

    dummy_part = types.Part(text="What distance are you training for?")
    dummy_content = types.Content(role="model", parts=[dummy_part])

    state = CoachState(
        contents=[dummy_content],
        plan=None,
        reply=None,
        runner_id=1,
        tool_call_count=1,
        goal_complete=False,
    )
    result = router(state)
    assert result == "ask_for_info", f"Expected 'ask_for_info', got '{result}'"
    print(f"  router with goal_complete=False, no tool calls -> '{result}'")
    print("  PASSED")


# --- API tests ---

def test_check_reschedule_true() -> None:
    separator("TEST: check_reschedule (injury message)")
    from core.coach import check_reschedule

    result = check_reschedule(
        "I tweaked my ankle on yesterday's long run, and my race just moved to November."
    )
    assert result is True, f"Expected True for injury message, got {result}"
    print(f"  result: {result}")
    print("  PASSED")


def test_check_reschedule_false() -> None:
    separator("TEST: check_reschedule (routine message)")
    from core.coach import check_reschedule

    result = check_reschedule("What should my easy run pace be this week?")
    assert result is False, f"Expected False for routine message, got {result}"
    print(f"  result: {result}")
    print("  PASSED")


# --- Agent integration test (API + DB) ---

def test_run_agent_ask_for_info() -> None:
    separator("TEST: run_agent with incomplete goal -> ask_for_info")
    from core.agent import run_agent, DEFAULT_USER_ID

    # No goal passed, force_plan=False -> agent should ask for missing info
    result = run_agent(
        message="I want to run faster.",
        runner_id=DEFAULT_USER_ID,
        profile={"first_name": "Marie", "goals": None, "constraints": None},
        chat_history=[
            {"role": "model", "content": "Hi! What are you training for?"},
            {"role": "user", "content": "I want to run faster."},
        ],
        goal={"distance": None, "target_time": None, "timeframe_weeks": None,
              "race_date": None, "missing_fields": ["distance", "target_time", "timeframe_weeks"]},
        force_plan=False,
    )
    assert result.get("plan") is None, "Expected no plan for incomplete goal"
    assert result.get("reply"), "Expected a reply asking for missing info"
    print(f"  reply preview: {result['reply'][:100]}...")
    print("  PASSED")


def test_run_agent_draft_plan() -> None:
    separator("TEST: run_agent with complete goal -> draft_plan")
    from core.agent import run_agent, DEFAULT_USER_ID
    from core.data_io import load_profile

    profile = load_profile()

    result = run_agent(
        message="I want to run a 10K under 50 minutes in 10 weeks.",
        runner_id=DEFAULT_USER_ID,
        profile=profile,
        chat_history=[
            {"role": "model", "content": "Hi! What are you training for?"},
            {"role": "user", "content": "I want to run a 10K under 50 minutes in 10 weeks."},
        ],
        goal={"distance": "10K", "target_time": "50:00", "timeframe_weeks": 10,
              "race_date": None, "missing_fields": []},
        force_plan=False,
    )
    assert result.get("reply") is None or result.get("plan"), (
        "Expected a plan for complete goal"
    )
    plan = result.get("plan")
    assert plan, "plan must be present"
    assert "goal" in plan, "plan must have a goal field"
    assert "weeks" in plan and len(plan["weeks"]) > 0, "plan must have at least one week"
    print(f"  goal: {plan['goal']}")
    print(f"  weeks: {len(plan['weeks'])}")
    print(f"  week 1 sessions: {plan['weeks'][0].get('sessions', [])[:2]}")
    print("  Check Supabase plans table to confirm the row was saved.")
    print("  PASSED")


# --- Runner ---

def main() -> None:
    print("\nRunning agent tests.")
    api_set = bool(os.environ.get("GEMINI_API_KEY"))
    db_set = bool(os.environ.get("DATABASE_URL"))
    print(f"GEMINI_API_KEY: {'SET' if api_set else 'NOT SET'}")
    print(f"DATABASE_URL:   {'SET' if db_set else 'NOT SET'}")

    if not api_set:
        print("\nERROR: GEMINI_API_KEY not set. Add it to your .env file and retry.")
        sys.exit(1)

    passed = 0
    failed = 0

    # Pure function tests run first (no API cost)
    pure_tests = [
        test_build_week_calendar,
        test_router_tool_call_limit,
        test_router_goal_complete,
        test_router_ask_for_info,
    ]

    # API + DB tests run after
    api_tests = [
        test_check_reschedule_true,
        test_check_reschedule_false,
    ]

    integration_tests = []
    if db_set:
        integration_tests = [
            test_run_agent_ask_for_info,
            test_run_agent_draft_plan,
        ]
    else:
        print("\nDATABASE_URL not set. Skipping agent integration tests.")

    for test in pure_tests + api_tests + integration_tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAILED: {e}")
            failed += 1

    separator("RESULTS")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    if integration_tests:
        print("  Check Supabase plans and messages tables for test rows and delete them.")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
