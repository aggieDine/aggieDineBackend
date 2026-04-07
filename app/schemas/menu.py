from typing import Any
from pydantic import BaseModel


class Nutrient(BaseModel):
    name: str | None = None
    value: Any = None
    unit: str | None = None
    value_numeric: Any = None


# class Coordinates(BaseModel):
#     latitude: float | None = None
#     longitude: float | None = None


class MenuItem(BaseModel):
    id: str = ""
    name: str
    station: str
    description: str | None = None
    portion: str | None = None
    ingredients: str | None = None
    calories: int | None = None
    filters: list[str] = []
    nutrients: list[Nutrient] = []


class MenuEntry(BaseModel):
    location_id: str
    location_name: str
    # building_name: str = ""
    # address: str = ""
    # coordinates: Coordinates = Coordinates()
    # status_label: str = ""
    # status_message: str = ""
    date: str
    period_id: str
    period_name: str
    item_count: int
    items: list[MenuItem]


class MenuResponse(BaseModel):
    date: str
    scraped_at: str
    location_count: int
    total_items: int
    menus: list[MenuEntry]