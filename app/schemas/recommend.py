from pydantic import BaseModel


class Coordinates(BaseModel):
    lat: float
    lon: float


class RecommendationRequest(BaseModel):
    current_location: Coordinates
    center_of_interest: Coordinates
    radius: float
    user_id: str
    restriction: str | None = None


class RecommendationItem(BaseModel):
    name: str
    cuisine: str
    restriction: str
    distance: float


class RecommendationResponse(BaseModel):
    status: str
    results: list[RecommendationItem]
