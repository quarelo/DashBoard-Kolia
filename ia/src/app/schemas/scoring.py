from datetime import datetime

from pydantic import BaseModel, Field


class MotiveWeightOut(BaseModel):
    code: str
    side: str
    name: str
    description: str
    points: int
    meetings: int
    frequency: float
    updated_at: datetime | None = None
    updated_by: str | None = None


class ScoringRulerResponse(BaseModel):
    ruler_version: int
    analysed_meetings: int
    saturated_sides: list[str] = []
    motives: list[MotiveWeightOut]


class MotiveWeightUpdate(BaseModel):
    code: str
    # The weight is a share of the 0-100 score, so a value outside it is a bug in
    # the caller, not a preference.
    points: int = Field(ge=0, le=100)
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, min_length=1, max_length=240)


class ScoringRulerUpdate(BaseModel):
    motives: list[MotiveWeightUpdate] = Field(min_length=1, max_length=50)
    # Who saved it. Set by the backend from the logged-in user, never by the
    # browser: the IA only ever sees the backend's service token.
    updated_by: str | None = Field(default=None, max_length=200)


class ScoreDistribution(BaseModel):
    count: int
    median: float | None = None
    mean: float | None = None
    at_100: int | None = None
    at_least_90: int | None = None
    zeros: int | None = None


class ScoringSimulationResponse(BaseModel):
    churn: ScoreDistribution
    opportunity: ScoreDistribution
