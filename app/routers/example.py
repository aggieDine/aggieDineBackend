from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_dynamodb_table
from app.middleware.auth import get_current_user
from app.schemas.example import ItemCreate, ItemList, ItemResponse, ItemUpdate
from app.services import example as item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemCreate,
    table=Depends(get_dynamodb_table),
    _user: dict = Depends(get_current_user),
):
    return item_service.create_item(table, data)


@router.get("/", response_model=ItemList)
def list_items(
    limit: int = 20,
    table=Depends(get_dynamodb_table),
):
    items = item_service.list_items(table, limit=limit)
    return ItemList(items=items, count=len(items))


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: str,
    table=Depends(get_dynamodb_table),
):
    item = item_service.get_item(table, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: str,
    data: ItemUpdate,
    table=Depends(get_dynamodb_table),
    _user: dict = Depends(get_current_user),
):
    item = item_service.update_item(table, item_id, data)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    table=Depends(get_dynamodb_table),
    _user: dict = Depends(get_current_user),
):
    deleted = item_service.delete_item(table, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")
