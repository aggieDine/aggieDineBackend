from pydantic import BaseModel
from typing import Optional


class UserCreate(BaseModel):
    display_name: str
    email:        str


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    email:        Optional[str] = None


class UserSummary(BaseModel):
    user_id:      str
    display_name: str


class UserResponse(BaseModel):
    user_id:               str
    display_name:          str
    email:                 str
    dietary_preferences:   list[str] = []
    allergens:             list[str] = []
    fcm_token:             Optional[str] = None
    follower_count:        int = 0
    following_count:       int = 0
    created_at:            str


class FollowListResponse(BaseModel):
    users: list[UserSummary]
    count: int


class SearchResponse(BaseModel):
    users: list[UserSummary]
    count: int


class DietUpdate(BaseModel):
    dietary_preferences: list[str]


class AllergenUpdate(BaseModel):
    allergens: list[str]