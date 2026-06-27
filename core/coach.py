"""Chat conversation logic and Gemini calls.

Public API:
    send_message(chat_history, existing_goal, profile) -> str
    extract_goal(chat_history, existing_goal) -> dict
    check_reschedule(message) -> bool

Shared helpers used by agent.py:
    build_system_instruction(task_instructions) -> str
    format_chat_history(chat_history) -> str
    format_profile(profile) -> str

COACH_PERSONA_V1 is the versioned shared system persona imported by agent.py.
"""

import json
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemini-3.1-flash-lite"

COACH_PERSONA_V1 = (
    "You are an expert running coach. You give personalized, realistic advice. "
    "You never jump volume or intensity far beyond what the runner's recent history shows, "
    "and you strictly respect any injury or scheduling constraint. "
    "Two runners with the same goal should not get the same plan."
)

GOAL_KEYS = ["distance", "target_time", "timeframe_weeks", "race_date", "missing_fields"]


# --- Shared builders used by agent.py ---

def build_system_instruction(task_instructions: str) -> str:
    """Combine the versioned coach persona with task-specific instructions."""
    if task_instructions:
        return f"{COACH_PERSONA_V1}\n\n{task_instructions}"
    return COACH_PERSONA_V1


def format_chat_history(chat_history: list) -> str:
    """Format the message list as plain labelled lines for use in prompts."""
    lines = []
    for m in chat_history:
        label = "Runner" if m.get("role") == "user" else "Coach"
        lines.append(f"{label}: {m.get('content', '')}")
    return "\n".join(lines)


def format_profile(profile: dict) -> str:
    """Format the profile dict as lean plain text for use in prompts.

    Selects only the fields relevant for coaching decisions.
    Constraints are included here so they do not appear separately in the goal.
    """
    if not profile:
        return "No profile available."
    fields = ["first_name", "city", "gender", "goals", "constraints"]
    lines = [
        f"{k.replace('_', ' ').title()}: {profile[k]}"
        for k in fields
        if profile.get(k)
    ]
    return "\n".join(lines) if lines else "No profile fields filled in."


# --- check_reschedule ---


def check_reschedule(message: str) -> bool:
    """Return True if the message signals an injury or schedule change needing a plan update."""

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False

    try:
        from pydantic import BaseModel

        class _Check(BaseModel):
            reschedule_needed: bool

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=(
                f'Runner message: "{message}"\n\n'
                "Does this message describe a new injury, a race date change, or a training "
                "schedule change that would require updating an existing training plan? "
                "Reply true or false."
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_Check,
                temperature=0.0,
            ),
        )
        return bool(json.loads(response.text).get("reschedule_needed", False))
    except Exception as e:
        print(f"ERROR in check_reschedule: {e}")
        return False


# --- send_message ---

def send_message(chat_history: list, existing_goal: dict, profile: dict) -> str:
    """Generate the coach's next reply.

    Uses the current goal state to decide whether to ask for a missing piece
    or to tell the runner they can generate a plan.
    Returns a plain string to display in the chat.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set, check the .env file")
        return "There is a configuration issue. Please contact the team."

    goal_summary = _format_goal_summary(existing_goal)
    profile_text = format_profile(profile)
    conversation = format_chat_history(chat_history)

    task = (
        "Reply to the runner's latest message.\n\n"
        f"Runner profile:\n{profile_text}\n\n"
        f"Current goal state:\n{goal_summary}\n\n"
        f"Conversation so far:\n{conversation}\n\n"
        "Rules:\n"
        "- Be direct. No filler, no greetings, no 'Great question!'.\n"
        "- If missing_fields is not empty, ask one focused question to get "
        "the most important missing piece.\n"
        "- If missing_fields is empty, tell the runner their goal is clear "
        "and they can click 'Generate a training plan'.\n"
        "- If the runner mentions something in the moment such as a new "
        "injury or a schedule change, acknowledge it and factor it in.\n"
        "- Keep it to 1-3 sentences.\n"
        "- Output only the reply text, nothing else."
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=task,
            config=types.GenerateContentConfig(
                system_instruction=build_system_instruction(""),
                temperature=0.7,
            ),
        )
        return response.text.strip()
    except Exception as e:
        print(f"ERROR in send_message: {e}")
        return "The coach is not available right now. Please try again later."


# --- extract_goal ---

def extract_goal(chat_history: list, existing_goal: dict = None) -> dict:
    """Extract a structured running goal from the full chat history.

    Runs on every turn. Falls back to rule-based extraction if the API is
    unavailable. Returns a goal dict with keys defined in GOAL_KEYS.
    """
    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            prompt = _build_extract_goal_prompt(chat_history, existing_goal)
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=build_system_instruction(
                        "Extract structured goal data. "
                        "Output JSON only, no commentary, no code fences."
                    ),
                    temperature=0.0,
                ),
            )
            goal = _parse_goal_json(response.text)
            if goal:
                return goal
        except Exception as e:
            print(f"ERROR in extract_goal: {e}")

    return _fallback_extract(chat_history, existing_goal)


# --- Internal prompt builders ---

def _build_extract_goal_prompt(chat_history: list, existing_goal: dict = None) -> str:
    conversation = format_chat_history(chat_history)
    existing = json.dumps(existing_goal, ensure_ascii=False) if existing_goal else "null"

    return (
        "Read the conversation and extract the runner's training goal.\n\n"
        f"Conversation:\n{conversation}\n\n"
        f"Existing goal (may be null):\n{existing}\n\n"
        "Return a JSON object with exactly these keys:\n"
        "{\n"
        '  "distance": string | null,\n'
        '  "target_time": string | null,\n'
        '  "timeframe_weeks": number | null,\n'
        '  "race_date": string | null,\n'
        '  "missing_fields": [string]\n'
        "}\n\n"
        "Rules:\n"
        "- missing_fields lists any of [distance, target_time, timeframe_weeks] "
        "that are still unknown.\n"
        "- timeframe_weeks and race_date are complementary: if either is known, "
        "do not list both as missing.\n"
        "- If the latest messages contain no goal information and an existing goal "
        "is present, return that existing goal unchanged.\n"
        "- Output JSON only."
    )


def _format_goal_summary(goal: dict) -> str:
    """Compact goal representation for use inside the send_message prompt."""
    if not goal:
        return "No goal extracted yet."
    lines = []
    for key in ["distance", "target_time", "timeframe_weeks", "race_date"]:
        val = goal.get(key)
        if val is not None:
            lines.append(f"{key}: {val}")
    missing = goal.get("missing_fields", [])
    if missing:
        lines.append(f"missing: {', '.join(missing)}")
    return "\n".join(lines) if lines else "No goal extracted yet."


# --- JSON parsing ---

def _parse_goal_json(text: str) -> dict:
    """Parse the model's JSON output into a goal dict. Returns None on failure."""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_goal(data)


def _normalize_goal(data: dict) -> dict:
    """Fill in missing keys and coerce value types."""
    goal = _empty_goal()
    for key in GOAL_KEYS:
        if key in data:
            goal[key] = data[key]
    if goal["timeframe_weeks"] is not None:
        try:
            goal["timeframe_weeks"] = int(goal["timeframe_weeks"])
        except (ValueError, TypeError):
            goal["timeframe_weeks"] = None
    if not isinstance(goal["missing_fields"], list):
        goal["missing_fields"] = []
    return goal


def _empty_goal() -> dict:
    return {
        "distance": None,
        "target_time": None,
        "timeframe_weeks": None,
        "race_date": None,
        "missing_fields": ["distance", "target_time", "timeframe_weeks"],
    }


# --- Fallback extraction (no API key or API failure) ---

def _fallback_extract(chat_history: list, existing_goal: dict = None) -> dict:
    """Rule-based extraction used when the API is unavailable."""
    text = " ".join(
        m.get("content", "") for m in chat_history if m.get("role") == "user"
    )
    if not text.strip():
        return existing_goal or _empty_goal()

    lower = text.lower()

    distance = None
    if "half marathon" in lower:
        distance = "half marathon"
    elif "marathon" in lower:
        distance = "marathon"
    elif "10k" in lower or "10 k" in lower:
        distance = "10K"
    elif "5k" in lower or "5 k" in lower:
        distance = "5K"

    target_time = None
    time_match = re.search(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b", text)
    if time_match:
        target_time = time_match.group(1)
    else:
        min_match = re.search(r"(\d{1,3})\s*(?:minutes?|mins?)", text)
        if min_match:
            target_time = f"{int(min_match.group(1))}:00"

    timeframe_weeks = None
    week_match = re.search(r"(\d+)\s*weeks?", text)
    month_match = re.search(r"(\d+)\s*months?", text)
    if week_match:
        timeframe_weeks = int(week_match.group(1))
    elif month_match:
        timeframe_weeks = int(month_match.group(1)) * 4

    missing = []
    if not distance:
        missing.append("distance")
    if not target_time:
        missing.append("target_time")
    if timeframe_weeks is None:
        missing.append("timeframe_weeks")

    return {
        "distance": distance,
        "target_time": target_time,
        "timeframe_weeks": timeframe_weeks,
        "race_date": None,
        "missing_fields": missing,
    }