from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventCreate(BaseModel):
    location:        str
    time:            datetime
    is_private:      bool = False
    invited_users:   list[str] = []  # list of user IDs
    message: str | None = None


class EventUpdate(BaseModel):
    location:        str | None = None
    time:            datetime | None = None
    is_private:      bool | None = None
    invited_users:   list[str] | None = None  # replaces entire list
    message: str | None = None


class EventResponse(BaseModel):
    event_id:        str
    location:        str
    time:            datetime
    is_private:      bool
    invited_users:   list[str]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
    created_by:      str
    created_at:      datetime
    updated_at:      datetime
    message: str | None = None


class EventList(BaseModel):
    events: list[EventResponse]
    count:  int

#Firebase
class FCMTokenUpdate(BaseModel):
    user_id: str
    device_token: str