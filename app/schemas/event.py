from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventCreate(BaseModel):
    location:        str
    time:            datetime
    is_private:      bool = False
    invited_users:   list[str] = []  # list of user IDs


class EventUpdate(BaseModel):
    location:        str | None = None
    time:            datetime | None = None
    is_private:      bool | None = None
    invited_users:   list[str] | None = None  # replaces entire list


class EventResponse(BaseModel):
    event_id:        str
    location:        str
    time:            datetime
    is_private:      bool
    invited_users:   list[str]                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            
    created_by:      str
    created_at:      datetime
    updated_at:      datetime


class EventList(BaseModel):
    events: list[EventResponse]
    count:  int

#Firebase
class FCMTokenUpdate(BaseModel):
    user_id: str
    device_token: str