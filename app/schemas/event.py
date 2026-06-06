from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class EventCreate(BaseModel):
    location:      str
    time:          datetime
    is_private:    bool = False
    invited_users: list[str] = []


class EventUpdate(BaseModel):
    location:      str | None = None
    time:          datetime | None = None
    is_private:    bool | None = None
    invited_users: list[str] | None = None


class InviteStatusEntry(BaseModel):
    user_id: str
    status:  str  # "pending" | "accepted" | "declined"


class EventResponse(BaseModel):
    event_id:        str
    location:        str
    time:            datetime
    is_private:      bool
    invited_users:   list[str]
    invite_statuses: list[InviteStatusEntry] = []
    created_by:      str
    created_at:      datetime
    updated_at:      datetime


class EventList(BaseModel):
    events: list[EventResponse]
    count:  int


class InviteRespond(BaseModel):
    status: str  # "accepted" | "declined"


class InviteResponse(BaseModel):
    event_id:   str
    event_time: str
    location:   str
    status:     str
    invited_by: str
    created_at: str
    updated_at: str


class InviteListResponse(BaseModel):
    invites: list[InviteResponse]
    count:   int