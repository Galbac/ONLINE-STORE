from pydantic import BaseModel, Field


class SearchQueryTrackRequest(BaseModel):
    query: str = Field(min_length=1, max_length=100)


class SearchQueryTrackResponse(BaseModel):
    tracked: bool
