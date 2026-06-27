# Running Coach Agent

A conversational running coach built with Streamlit, LangGraph, and Gemini. The runner describes their goal in plain language, and the agent reads their training history from a database before generating a personalised week-by-week plan as structured output.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.58+-FF4B4B.svg)](https://streamlit.io/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2.6-green.svg)](https://www.langchain.com/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What it does

The app has four screens: chat, current plan, user profile, and training history. 

The chat pipeline extracts a structured goal from the conversation on every turn. When the runner clicks Generate, a LangGraph agent reads their training history from Postgres via a tool call, then produces a validated TrainingPlan (Pydantic model) via constrained JSON output. If the runner mentions an injury or a race date change mid-conversation, a reschedule router detects it and triggers the agent automatically without requiring the button.

The whole app sits behind a shared password gate checked on every page, not just the entry point.

---

## Architecture

```
Runner (browser)
    |
Streamlit Community Cloud  (4 pages, hmac password gate)
    |
Gemini API  (gemini-3.1-flash-lite)
    |
LangGraph agent
    understand -> get_runner_history (Supabase tool) -> draft_plan -> END
                                                     -> ask_for_info -> END
    |
Supabase (Postgres)  (users, training_history, plans, messages)
```

**Chat turn flow:**
```
user message -> check_reschedule (LLM router)
    if reschedule and plan exists: run_agent(force_plan=True)
    else: extract_goal -> send_message
```

---

## Project structure

```
running-coach-agent/
├── app/
│   ├── Home.py                  # entry point: gate, chat, plan button
│   └── pages/
│       ├── 2_Plan.py             # renders structured TrainingPlan with expandable weeks
│       ├── 3_Profile.py          # user profile (read only)
│       └── 4_History.py          # training history table
├── core/
│   ├── agent.py                  # LangGraph graph and run_agent entry point
│   ├── auth.py                   # require_auth() used by every gated page
│   ├── coach.py                  # send_message, extract_goal, check_reschedule
│   ├── data_io.py                # psycopg2 reads and writes via transaction pooler
│   ├── plan.py                   # build_week_calendar (deterministic date utility)
│   ├── schemas.py                # TrainingPlan and Week Pydantic models
│   └── tools.py                  # get_runner_history tool declaration and executor
├── data/
│   └── schema.sql                # CREATE TABLE statements for all four tables
├── tests/
│   ├── test_db.py                # database connection and read/write tests
│   └── test_agent.py             # router logic, reschedule detection, agent integration
├── requirements.txt
└── .gitignore                    # excludes .env and seed data JSON files
```

---

## Quick start

<details>
<summary><b>Setup and run, click to expand</b></summary>

### Prerequisites
- Python 3.10+
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- A Postgres database (Supabase free tier works)

### Setup

1. **Clone**
```bash
git clone https://github.com/wengchienwei/running-coach-agent.git
cd running-coach-agent
```

2. **Virtual environment**
```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
venv\Scripts\activate      # Windows
```

3. **Install**
```bash
pip install -r requirements.txt
```

4. **Create the database tables**

Run `data/schema.sql` against your Postgres instance. In Supabase: paste into the SQL Editor and click Run.

5. **Create `.env`** in the project root:
```
GEMINI_API_KEY=your_key_here
APP_PASSWORD=pick_any_password
DATABASE_URL=postgresql://postgres:your_password@your_pooler_host:6543/postgres
```
Use the Supabase transaction pooler connection string (port 6543), not the direct hostname.

6. **Run**
```bash
streamlit run app/Home.py
```

7. **Test**
```bash
python tests/test_db.py
python tests/test_agent.py
```

</details>

---

## Key technical decisions

**Transaction pooler over direct connection.** The Supabase direct hostname resolves only over IPv6. The transaction pooler uses a different hostname that resolves over IPv4, which is required for Streamlit Community Cloud and most local development environments.

**Deterministic week calendar.** The agent receives a precomputed Monday-anchored week calendar in the prompt rather than asking the LLM to calculate dates. LLMs produce incorrect weekday labels when computing multi-week date arithmetic in free text, confirmed during testing where a race date several weeks out was assigned the wrong weekday.

**Two END paths in the agent graph.** `draft_plan` fires when the goal is complete. `ask_for_info` fires when it is not, extracting the model's plain-text question from the understand node's output without an additional LLM call.

**Reschedule router before extract_goal.** When an injury or schedule change is detected, extract_goal is skipped entirely since the agent runs with force_plan=True regardless of missing_fields. This saves one LLM call per turn on the reschedule path.

---

## Contributors

Built as a team project for Head of Data 102, MSc DSBA, ESSEC x CentraleSupelec.

- [wengchienwei](https://github.com/wengchienwei) - project skeleton, session state contract, architecture decisions, code review, agentic refactor
- [stuckingravity](https://github.com/stuckingravity) - initial repo setup, LLM conversation logic
- [hbyang01](https://github.com/hbyang01) - LangGraph agent, structured output
- [audreyli0428](https://github.com/audreyli0428) - chat UI, Supabase integration
- [Abigail0716](https://github.com/Abigail0716) - plan generation, screens

Original team repository (private): [stuckingravity/hod102-2026-group-4](https://github.com/stuckingravity/hod102-2026-group-4)

---

## License

MIT. See [LICENSE](LICENSE) for details.

Seed data files (`profile.json`, `training_history.json`) are not included as they are proprietary to the course. The schema and all application code are original work.