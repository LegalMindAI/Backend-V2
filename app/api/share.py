from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import boto3
import os
import json
from datetime import datetime

from ..auth.firebase_auth import get_current_user
from ..db.dynamodb import get_chat_by_id

# Create router
share_router = APIRouter(
    prefix="/share",
    tags=["Share"]
)

# S3 configuration
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
S3_AWS_REGION = os.getenv("S3_AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# Initialize S3 client
s3_client = boto3.client(
    's3',
    region_name=S3_AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

# Request schema
class ShareChatRequest(BaseModel):
    chat_id: str

# Response schema
class ShareResponse(BaseModel):
    share_id: str
    message: str

# emmpty "" means nothing after the prefix(/share route)
@share_router.post("", response_model=ShareResponse)
async def share_chat(
    request: ShareChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Share a chat conversation by uploading it to S3
    """
    user_id = current_user.get("uid")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    try:
        # Get chat data from DDB
        chat_data = await get_chat_by_id(user_id, request.chat_id)
        
        # Prepare data for S3
        shared_data = {
            "chat_id": chat_data["chat_id"],
            "title": chat_data["title"],
            "conversation": chat_data["conversation"],
            "shared_at": datetime.now().isoformat(),
            "shared_by": user_id
        }
        
        # Upload to S3
        s3_key = f"chats/{request.chat_id}.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key,
            Body=json.dumps(shared_data),
            ContentType="application/json"
        )
        
        return {
            "share_id": request.chat_id,
            "message": "Chat shared successfully"
        }
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error sharing chat: {str(e)}")

# Create public router for fetch functionality
fetch_router = APIRouter(
    prefix="/fetch",
    tags=["Fetch"]
)

# this is /fetch/{chat_id}
@fetch_router.get("/{chat_id}")
async def fetch_shared_chat(chat_id: str):
    """
    Fetch a shared chat from S3 (public bucket)
    """
    try:
        # Fetch from S3
        s3_key = f"chats/{chat_id}.json"
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=s3_key
        )
        
        # Parse JSON from S3
        chat_data = json.loads(response['Body'].read().decode('utf-8'))
        return chat_data
        
    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="Shared chat not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching shared chat: {str(e)}") 