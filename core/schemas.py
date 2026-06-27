"""Shared Pydantic schemas for the training plan."""

from pydantic import BaseModel


class Week(BaseModel):
    week: int
    phase: str
    km: float
    sessions: list[str]


class TrainingPlan(BaseModel):
    goal: str
    weeks: list[Week]
