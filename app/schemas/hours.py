from pydantic import BaseModel


class LocationHours(BaseModel):
    location: str
    closed:   bool
    hours:    list[str] = []


class HoursResponse(BaseModel):
    date:           str
    scraped_at:     str
    source:         str
    location_count: int
    locations:      list[LocationHours]