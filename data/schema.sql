-- Head of Data 102: Running Coach
-- Canonical database schema.
-- Run this file once against your Postgres instance to create all tables.
-- Supabase: paste into the SQL Editor and click Run.

-- users: one row per person using the app.
-- first_name, city, gender are NOT NULL for data completeness.
-- goals and constraints are nullable since a user can exist without them.
create table users (
    id           serial primary key,
    first_name   text        not null,
    city         text        not null,
    gender       text        not null,
    goals        text,
    constraints  text,
    created_at   timestamptz default now()
);

-- training_history: one row per past session, linked to a user.
-- session_date is a proper date type (not text) to support date range queries.
-- km is numeric(4,1) to match the seed data format (e.g. 5.5, 13.0).
-- pace stays as text ("5:37") since the app never does arithmetic on it.
-- session_type stores values like "easy", "intervals", "long", "recovery".
create table training_history (
    id            serial primary key,
    user_id       integer      references users(id) on delete cascade,
    session_date  date         not null,
    km            numeric(4,1) not null,
    pace          text         not null,
    session_type  text         not null,
    created_at    timestamptz  default now()
);

-- plans: one row per generated plan, linked to a user.
-- plan_text stores the full plain-text output from generate_plan().
-- goal_json is nullable because the app has a profile fallback path where
-- generate_plan can be called without a complete structured goal from chat.
create table plans (
    id          serial primary key,
    user_id     integer references users(id) on delete cascade,
    plan_text   text    not null,
    goal_json   jsonb,
    created_at  timestamptz default now()
);

-- messages: one row per chat turn, linked to a user.
-- role matches the values used in coach.py: "user" or "model".
-- The app currently writes each turn here but does not load history back
-- into context on session start (requires a windowing strategy first).
create table messages (
    id          serial primary key,
    user_id     integer references users(id) on delete cascade,
    role        text    not null check (role in ('user', 'model')),
    content     text    not null,
    created_at  timestamptz default now()
);
