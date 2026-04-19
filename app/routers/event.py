from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_dynamodb_table
from app.middleware.auth import get_current_user
from app.schemas.event import EventCreate, EventList, EventResponse, EventUpdate
from app.services import event as event_service
from app.fcm import (
    notify_event_created,
    notify_event_updated,
    notify_event_deleted,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    data:  EventCreate,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    event = event_service.create_event(table, data, user["sub"])
    
    # Send silent FCM data message to all involved users
    notify_event_created(table, event)
    
    return event


@router.get("", response_model=EventList)
def list_events(
    date:         str | None = Query(default=None, description="YYYY-MM-DD — if omitted returns next 24h"),
    hours_window: int        = Query(default=24,   description="How many hours ahead to look (ignored if date is set)"),
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    events = event_service.list_events(table, user["sub"], date=date, hours_window=hours_window)
    return EventList(events=events, count=len(events))


@router.get("/{event_id}", response_model=EventResponse)
def get_event(
    event_id:   str,
    event_time: datetime = Query(..., description="ISO datetime of the event — needed to locate it"),
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    event = event_service.get_event(table, event_id, event_time)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    if event["is_private"] and user["sub"] not in event["invited_users"] and event["created_by"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return event


@router.put("/{event_id}", response_model=EventResponse)
def update_event(
    event_id:   str,
    data:       EventUpdate,
    event_time: datetime = Query(..., description="Current ISO datetime of the event"),
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    previous_event = event_service.get_event(table, event_id, event_time)
    if previous_event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if previous_event["created_by"] != user["sub"]:
        raise HTTPException(status_code=403, detail="Only the creator can update this event")

    updated = event_service.update_event(table, event_id, event_time, data, user["sub"])
    if updated is None:
        raise HTTPException(status_code=404, detail="Event not found")
    
    # Send silent FCM data message with updated event
    notify_event_updated(table, updated, previous_event)
    
    return updated


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id:   str,
    event_time: datetime = Query(..., description="ISO datetime of the event"),
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    event = event_service.get_event(table, event_id, event_time)
    if event is None or event["created_by"] != user["sub"]:
        raise HTTPException(status_code=404, detail="Event not found or you are not the creator")
    
    deleted = event_service.delete_event(table, event_id, event_time, user["sub"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found or you are not the creator")
    
    # Send silent FCM data message about deletion
    notify_event_deleted(table, event)