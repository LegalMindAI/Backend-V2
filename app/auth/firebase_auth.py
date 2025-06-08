from fastapi import Depends, HTTPException, status, APIRouter, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import os
from dotenv import load_dotenv
import httpx
from pydantic import BaseModel
from typing import Optional, Dict, Any

# Load environment variables
load_dotenv()

# Firebase configuration
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")

# Set up OAuth2 with password flow
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Create auth router for login with tags and prefix
auth_router = APIRouter(
    tags=["Authentication"],
    prefix="/auth"
)

# Token response model
class Token(BaseModel):
    access_token: str
    token_type: str

# User info model
class UserInfo(BaseModel):
    uid: str
    email: str

@auth_router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        # Firebase Auth REST API for email/password sign-in
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        
        payload = {
            "email": form_data.username,
            "password": form_data.password,
            "returnSecureToken": True
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            data = response.json()
            
            if response.status_code != 200:
                error_message = data.get("error", {}).get("message", "Unknown error")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Authentication failed: {error_message}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            # Return the token in the format expected by OAuth2
            return {
                "access_token": data.get("idToken"),
                "token_type": "bearer"
            }
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"HTTP error occurred: {str(e)}"
        )

async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Validate and decode the JWT token to get the current user
    """
    try:
        # Firebase Auth REST API for token verification
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_WEB_API_KEY}"
        
        payload = {
            "idToken": token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload)
            data = response.json()
            
            if response.status_code != 200 or "users" not in data or not data["users"]:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            user = data["users"][0]
            return {
                "uid": user.get("localId"),
                "email": user.get("email")
            }
            
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

@auth_router.get("/users/me", response_model=UserInfo)
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Get information about the current authenticated user
    """
    return current_user

@auth_router.get("/status", include_in_schema=True)
async def auth_status():
    """
    Check if the authentication system is working
    """
    return {
        "status": "ok",
        "firebase_project_id": FIREBASE_PROJECT_ID,
        "message": "Authentication system is working"
    } 