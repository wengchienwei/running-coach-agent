"""Tool declarations and executor for the coach agent.

Public API:
    COACH_TOOLS   - types.Tool passed to GenerateContentConfig
    execute_tool  - dispatcher called by the tools node in the graph

Only one tool is exposed to the model: get_runner_history.
update_plan was removed because draft_plan in agent.py calls save_plan
directly, so exposing update_plan as a model tool caused double-saves.
"""

from google.genai import types


COACH_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_runner_history",
        description=(
            "Return the runner's training sessions since a given date. "
            "Call this before building any plan to read recent load and pace. "
            "Example: get_runner_history(since='2026-04-01')"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "since": types.Schema(
                    type=types.Type.STRING,
                    description="ISO date YYYY-MM-DD. Sessions on or after this date are returned.",
                ),
            },
            required=["since"],
        ),
    ),
])


def _get_runner_history(runner_id: int, since: str) -> dict:
    from core.data_io import load_training_history
    history = load_training_history(user_id=runner_id)
    return {"sessions": [s for s in history["sessions"] if s["date"] >= since]}


def execute_tool(name: str, args: dict, runner_id: int) -> dict:
    """Execute a named tool and return its result dict."""
    if name == "get_runner_history":
        return _get_runner_history(runner_id, args.get("since", "2000-01-01"))
    return {"error": f"Unknown tool: {name}"}
