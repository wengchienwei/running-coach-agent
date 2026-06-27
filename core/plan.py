"""Training plan utilities retained after the agentic migration.

generate_plan and all associated prompt builders have been removed.
The LangGraph agent in core/agent.py now owns plan generation.

Kept here because build_week_calendar is a pure date utility with no
dependency on the agent or the LLM, and imported by agent.py.
"""

from datetime import date, timedelta

DEFAULT_PLAN_WEEKS = 10
MAX_PLAN_WEEKS = 53


def _next_monday_on_or_after(d: date) -> date:
    """Return d if it is already Monday, otherwise the following Monday.

    Anchors the calendar so week 1 always starts on Monday, matching the
    Mon-Sun format the model uses in session descriptions.
    """
    days_until_monday = (7 - d.weekday()) % 7
    return d + timedelta(days=days_until_monday)


def build_week_calendar(start: date, num_weeks: int) -> str:
    """Precompute exact dates and weekdays for each week of the plan.

    LLMs are unreliable at multi-week date arithmetic in free text.
    Computing the calendar here removes that step from the model entirely.
    The model is instructed to copy these labels verbatim.
    """
    plan_start = _next_monday_on_or_after(start)
    lines = []
    for week_num in range(1, num_weeks + 1):
        week_start = plan_start + timedelta(weeks=week_num - 1)
        week_end = week_start + timedelta(days=6)
        days = ", ".join(
            (week_start + timedelta(days=i)).strftime("%a %d %b")
            for i in range(7)
        )
        lines.append(
            f"Week {week_num} ({week_start.strftime('%d %b')} to "
            f"{week_end.strftime('%d %b')}): {days}"
        )
    return "\n".join(lines)
