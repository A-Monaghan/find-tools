"""
User authentication routes.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
    get_current_user
)
from core.config import get_settings


router = APIRouter(prefix="/auth", tags=["authentication"])


# Schemas
class UserCreate(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class UserResponse(BaseModel):
    user_id: str
    username: str


# In-memory user store (replace with database in production)
# TODO: Move to database table
_users_db = {}


@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate):
    """Register a new user."""
    if user.username in _users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    user_id = f"user_{len(_users_db) + 1}"
    hashed_password = get_password_hash(user.password)
    
    _users_db[user.username] = {
        "user_id": user_id,
        "username": user.username,
        "hashed_password": hashed_password
    }
    
    return UserResponse(user_id=user_id, username=user.username)


@router.post("/login", response_model=Token)
async def login(user: UserLogin):
    """Login and get access token."""
    settings = get_settings()
    
    user_data = _users_db.get(user.username)
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not verify_password(user.password, user_data["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user_data["user_id"], "username": user.username},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    return UserResponse(
        user_id=current_user["user_id"],
        username=current_user["payload"].get("username", "unknown")
    )
