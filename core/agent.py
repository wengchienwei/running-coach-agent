"""LangGraph coach agent: understand -> tools loop -> draft_plan or ask_for_info.

Public API:
    run_agent(message, runner_id, profile, chat_history, goal, force_plan) -> dict
    build_coach_graph() -> compiled StateGraph
    DEFAULT_USER_ID -> int

Returns a dict with at least one of:
    plan: dict  - a validated TrainingPlan as a dict, if plan was generated
    reply: str  - a text reply asking for missing info, if goal was incomplete

Graph topology:
    START -> understand -> router -> tools -> understand (loop)
                                  -> draft_plan -> END
                                  -> ask_for_info -> END
"""

import json
import os
from datetime import date, timedelta
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langgraph.graph import END, START, StateGraph

from core.coach import COACH_PERSONA_V1, format_chat_history, format_profile
from core.plan import DEFAULT_PLAN_WEEKS, MAX_PLAN_WEEKS, build_week_calendar
from core.schemas import TrainingPlan
from core.tools import COACH_TOOLS, execute_tool

load_dotenv()

MODEL = "gemini-3.1-flash-lite"
DEFAULT_USER_ID = 1
MAX_TOOL_CALLS = 10


# --- State ---

def _append(existing: list, incoming) -> list:
    """LangGraph reducer: append a Content or extend with a list of Contents."""
    if isinstance(incoming, list):
        return existing + incoming
    return existing + [incoming]


class CoachState(TypedDict):
    contents: Annotated[list, _append]
    plan: dict | None
    reply: str | None
    runner_id: int
    tool_call_count: int
    goal_complete: bool


# --- System instructions ---

_UNDERSTAND_SYSTEM = (
    COACH_PERSONA_V1 + "\n\n"
    "Before producing any plan, call get_runner_history at least once to read "
    "the runner's recent sessions. Once you have the history and enough goal "
    "information, respond with a plain-text summary only (no tool calls).\n\n"
    "If the runner has not yet provided all necessary goal information "
    "(distance, target time, and timeframe), ask one focused question to get "
    "the most important missing piece. Do not produce a plan until you have "
    "at least distance and timeframe."
)

_DRAFT_PLAN_SYSTEM = (
    COACH_PERSONA_V1 + "\n\n"
    "Produce the plan as structured JSON matching the TrainingPlan schema exactly.\n"
    "Format each session as a single descriptive string. Examples:\n"
    "  'Tue: Easy run 7 km at 5:30/km'\n"
    "  'Wed: Intervals 2.4 km main set (6x400m) plus 2 km warmup and cooldown'\n"
    "  'Sat: Long run 12 km'\n"
    "  'Mon: Rest'\n"
    "Use the exact dates and weekdays from the week calendar provided in the "
    "conversation. Do not compute or guess dates yourself."
)


# --- Nodes ---

def understand(state: CoachState) -> dict:
    """Call the LLM; it may emit function calls or produce a plain-text reply."""
    print("[understand]")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=MODEL,
        contents=state["contents"],
        config=types.GenerateContentConfig(
            system_instruction=_UNDERSTAND_SYSTEM,
            tools=[COACH_TOOLS],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    model_content = response.candidates[0].content
    calls = [p.function_call.name for p in model_content.parts if p.function_call]
    print(f"  tool_calls={calls or 'none'}")
    return {"contents": model_content}


def tools_node(state: CoachState) -> dict:
    """Execute all function calls in the last model Content and return results."""
    print("[tools]")
    last = state["contents"][-1]
    runner_id = state["runner_id"]
    result_parts = []

    for part in last.parts:
        if not part.function_call:
            continue
        name = part.function_call.name
        args = dict(part.function_call.args)
        print(f"  -> {name}({args})")
        result = execute_tool(name, args, runner_id)
        result_parts.append(
            types.Part.from_function_response(name=name, response=result)
        )

    return {
        "contents": types.Content(role="user", parts=result_parts),
        "tool_call_count": state.get("tool_call_count", 0) + 1,
    }


def draft_plan(state: CoachState) -> dict:
    """Produce a validated TrainingPlan via constrained JSON output and save it."""
    print("[draft_plan]")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    contents = list(state["contents"]) + [
        types.Content(
            role="user",
            parts=[types.Part(text=(
                "Now produce the complete training plan as structured JSON. "
                "Include every week from the start of training until race week. "
                "Use the exact dates and weekdays from the week calendar provided earlier."
            ))],
        )
    ]
    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=_DRAFT_PLAN_SYSTEM,
            response_mime_type="application/json",
            response_schema=TrainingPlan,
            temperature=0.3,
        ),
    )
    plan_dict = json.loads(response.text)
    validated = TrainingPlan(**plan_dict)

    clean_dict = validated.model_dump()

    from core.data_io import save_plan
    save_plan(json.dumps(clean_dict, indent=2), clean_dict.goal, user_id=state["runner_id"])
    print(f"  goal='{validated.goal}', weeks={len(validated.weeks)}")
    return {"plan": clean_dict}


def ask_for_info_node(state: CoachState) -> dict:
    """Extract the model's conversational reply when goal information is still missing.

    The understand node's last content is a plain-text reply asking the runner
    for the missing piece. This node lifts that text into the reply field so
    Home.py can display it as a coach message in the chat.
    """
    print("[ask_for_info]")
    last = state["contents"][-1]
    reply_text = ""
    for part in last.parts or []:
        if hasattr(part, "text") and part.text:
            reply_text = part.text
            break
    return {"reply": reply_text}


# --- Router ---

def router(state: CoachState) -> str:
    """Return the next node name based on the current state.

    Priority order:
    1. Loop guard: if MAX_TOOL_CALLS reached, force draft_plan regardless.
    2. Tool call pending: route to tools.
    3. Goal complete or force_plan: route to draft_plan.
    4. Default: route to ask_for_info to request missing goal information.
    """
    if state.get("tool_call_count", 0) >= MAX_TOOL_CALLS:
        print("[router] -> draft_plan (tool call limit reached)")
        return "draft_plan"
    last = state["contents"][-1]
    for part in last.parts or []:
        if part.function_call:
            print("[router] -> tools")
            return "tools"
    if state.get("goal_complete", False):
        print("[router] -> draft_plan")
        return "draft_plan"
    print("[router] -> ask_for_info")
    return "ask_for_info"


# --- Graph ---

def build_coach_graph():
    g = StateGraph(CoachState)
    g.add_node("understand", understand)
    g.add_node("tools", tools_node)
    g.add_node("draft_plan", draft_plan)
    g.add_node("ask_for_info", ask_for_info_node)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", router)
    g.add_edge("tools", "understand")
    g.add_edge("draft_plan", END)
    g.add_edge("ask_for_info", END)
    return g.compile()


# --- Entry point ---

def run_agent(
    message: str,
    runner_id: int = DEFAULT_USER_ID,
    profile: dict | None = None,
    chat_history: list | None = None,
    goal: dict | None = None,
    force_plan: bool = False,
) -> dict:
    """Run the coach graph and return a dict with 'plan' and/or 'reply'.

    force_plan=True routes to draft_plan after the tools loop completes,
    even when missing_fields is not empty. Used for mid-conversation
    reschedules where the runner has signalled a change that requires
    updating an existing plan immediately.

    Returns a dict with at least one key set:
        plan: dict  - if a TrainingPlan was produced
        reply: str  - if the agent asked for more information
    """
    today = date.today()
    today_str = f"{today.strftime('%Y-%m-%d')} ({today.strftime('%A')})"
    since = (today - timedelta(weeks=8)).isoformat()

    num_weeks = DEFAULT_PLAN_WEEKS
    if goal and goal.get("timeframe_weeks"):
        try:
            num_weeks = min(int(goal["timeframe_weeks"]), MAX_PLAN_WEEKS)
        except (ValueError, TypeError):
            num_weeks = DEFAULT_PLAN_WEEKS
    calendar_text = build_week_calendar(today, num_weeks)

    lines = [
        f"Today: {today_str}",
        "Week calendar (use these exact dates and weekdays, do not compute your own):",
        calendar_text,
        f"Suggested history lookback date: {since}",
    ]

    if profile:
        profile_text = format_profile(profile)
        lines.append(f"\nRunner profile:\n{profile_text}")

    if chat_history:
        recent = chat_history[-8:]
        lines.append("\nRecent conversation:")
        lines.append(format_chat_history(recent))

    lines.append(f"\nRunner's latest message: {message}")

    # goal_complete is True if the runner has given all required goal fields,
    # or if force_plan is set (reschedule scenario: regenerate with what we have).
    missing = goal.get("missing_fields", []) if goal else ["distance", "target_time", "timeframe_weeks"]
    goal_complete = force_plan or (not missing)

    graph = build_coach_graph()
    result = graph.invoke({
        "contents": [
            types.Content(
                role="user",
                parts=[types.Part(text="\n".join(lines))],
            )
        ],
        "plan": None,
        "reply": None,
        "runner_id": runner_id,
        "tool_call_count": 0,
        "goal_complete": goal_complete,
    })
    return result