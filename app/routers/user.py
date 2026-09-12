from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_dynamodb_table
from app.middleware.auth import get_current_user
from app.schemas.user import (
    AllergenUpdate,
    DietUpdate,
    FollowListResponse,
    SearchResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services import user as user_service

from app.schemas.event import InviteListResponse
from app.services import event as event_service

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# IMPORTANT: /me and /search must be defined BEFORE /{user_id}
# otherwise FastAPI will try to match "me"/"search" as a user_id
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
def get_me(
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    """Get your own profile using auth token — no user_id needed."""
    result = user_service.get_user(table, user["sub"])
    if result is None:
        raise HTTPException(status_code=404, detail="User not found. Register first via POST /users.")
    return result


@router.get("/search", response_model=SearchResponse)
def search_users(
    q:     str = Query(..., min_length=1, description="Search query for display_name"),
    limit: int = Query(default=20, le=50),
    table=Depends(get_dynamodb_table),
    _user: dict = Depends(get_current_user),
):
    """Search users by display name (partial, case-insensitive)."""
    results = user_service.search_users(table, q, limit)
    return SearchResponse(users=results, count=len(results))


# ---------------------------------------------------------------------------
# Profile CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    data:  UserCreate,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    """Register a new user profile. user_id taken from auth token."""
    result = user_service.create_user(table, user["sub"], data)
    if result is None:
        raise HTTPException(status_code=409, detail="User already exists.")
    return result


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    table=Depends(get_dynamodb_table),
    _user:   dict = Depends(get_current_user),
):
    """Fetch any user's profile by user_id."""
    result = user_service.get_user(table, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return result


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    data:    UserUpdate,
    table=Depends(get_dynamodb_table),
    user:    dict = Depends(get_current_user),
):
    """Update display_name and/or email. Owner only."""
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="You can only update your own profile.")

    result = user_service.update_user(table, user_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    table=Depends(get_dynamodb_table),
    user:    dict = Depends(get_current_user),
):
    """Delete account and all follow relationships. Owner only."""
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own account.")

    deleted = user_service.delete_user(table, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found.")


# ---------------------------------------------------------------------------
# Follow / Unfollow
# ---------------------------------------------------------------------------

@router.post("/follow/{followed_id}", status_code=status.HTTP_204_NO_CONTENT)
def follow_user(
    followed_id: str,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    if user["sub"] == followed_id:
        raise HTTPException(status_code=400, detail="You cannot follow yourself.")

    result = user_service.follow_user(table, user["sub"], followed_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="User to follow not found.")
    if result == "already_following":
        raise HTTPException(status_code=409, detail="Already following this user.")


@router.delete("/follow/{followed_id}", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_user(
    followed_id: str,
    table=Depends(get_dynamodb_table),
    user:  dict = Depends(get_current_user),
):
    result = user_service.unfollow_user(table, user["sub"], followed_id)
    if result == "not_following":
        raise HTTPException(status_code=404, detail="You are not following this user.")


# ---------------------------------------------------------------------------
# Followers / Following lists
# ---------------------------------------------------------------------------

@router.get("/{user_id}/followers", response_model=FollowListResponse)
def get_followers(
    user_id: str,
    table=Depends(get_dynamodb_table),
    _user:   dict = Depends(get_current_user),
):
    if user_service.get_user(table, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    users = user_service.get_followers(table, user_id)
    return FollowListResponse(users=users, count=len(users))


@router.get("/{user_id}/following", response_model=FollowListResponse)
def get_following(
    user_id: str,
    table=Depends(get_dynamodb_table),
    _user:   dict = Depends(get_current_user),
):
    if user_service.get_user(table, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    users = user_service.get_following(table, user_id)
    return FollowListResponse(users=users, count=len(users))


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

@router.put("/diet_options/{user_id}/update", response_model=UserResponse)
def update_diet(
    user_id: str,
    data:    DietUpdate,
    table=Depends(get_dynamodb_table),
    user:    dict = Depends(get_current_user),
):
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="You can only update your own preferences.")
    result = user_service.update_diet(table, user_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return result


@router.put("/allergens/{user_id}/update", response_model=UserResponse)
def update_allergens(
    user_id: str,
    data:    AllergenUpdate,
    table=Depends(get_dynamodb_table),
    user:    dict = Depends(get_current_user),
):
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="You can only update your own allergens.")
    result = user_service.update_allergens(table, user_id, data)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return result

@router.get("/me/invites", response_model=InviteListResponse)
def get_my_invites(
    status: str | None = Query(default=None, description="Filter by status: pending, accepted, declined"),
    table=Depends(get_dynamodb_table),
    user:   dict = Depends(get_current_user),
):
    """Get all event invites for the current user."""
    if status and status not in ("pending", "accepted", "declined"):
        raise HTTPException(status_code=400, detail="Status must be pending, accepted, or declined.")

    invites = event_service.get_user_invites(table, user["sub"], status_filter=status)
    return InviteListResponse(invites=invites, count=len(invites))