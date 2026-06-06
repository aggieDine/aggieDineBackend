from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import example, health, recommend
from app.routers import menu
from app.routers import hours

app = FastAPI(
    title=settings.SERVICE_NAME,
    version=settings.VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(example.router)
app.include_router(recommend.router)

app.include_router(menu.router)

'''
**Example requests:**
GET /menu
GET /menu?date=2026-04-03
GET /menu?date=2026-04-03&location=Commons
GET /menu?date=2026-04-03&period=Breakfast
GET /menu?date=2026-04-03&filters=Vegetarian&filters=Avoiding+Gluten
GET /menu?date=2026-04-03&location=Sbisa&period=Dinner&filters=Vegan

--- Real URL Example ---
https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/menu?date=2026-04-06&period=Breakfast

Menu is available for current day and days before
'''

app.include_router(hours.router)

'''
** Example Requests: **
GET /hours?date=2026-04-06
GET /hours?date=2026-04-07

--- Real URL Example ---
https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/hours?date=2026-04-06

Hours are available up until including the day a week from current day
'''

from app.routers import event
app.include_router(event.router)

'''
** Example Requests: **
POST /events
GET /events
GET /events?date=2026-04-18
GET /events?hours_window=48
GET /events/evt_019?event_time=2026-04-18T20:00:00Z
PUT /events/evt_019?event_time=2026-04-18T20:00:00Z
DELETE /events/evt_019?event_time=2026-04-18T20:00:00Z

--- Real URL Example ---
https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/events?date=2026-04-18

If no date is provided, GET /events returns events for the next 24 hours. Single-event operations (GET, PUT, DELETE) strictly require the 'event_time' ISO string query parameter to locate the item in DynamoDB. All endpoints require an authenticated user.
'''

from app.routers import user_token
app.include_router(user_token.router)

'''
FCM
** Example Requests: **
POST /user/register-device
POST /user/unregister-device

--- Real URL Example ---
https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/user/register-device

Endpoints require an authenticated user. Expects a JSON body containing {"device_token": "string"} to connect or disconnect the user's mobile device from Firebase silent notifications.
'''

from app.routers import user
app.include_router(user.router)

'''
User 
'''


@app.get("/")
async def root():
    return {"service": settings.SERVICE_NAME, "version": settings.VERSION}