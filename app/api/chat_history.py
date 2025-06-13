from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid

from ..auth.firebase_auth import get_current_user
from ..db.dynamodb import save_or_update_chat, get_chat_titles, get_chat_by_id

# Initialize router
chat_history_router = APIRouter(
    prefix="/chat-history",
    tags=["Chat History"]
)

# Request schema for saving chat
class SaveChatRequest(BaseModel):
    chat_id: Optional[str] = None
    question: str
    answer: str

# Response schemas
class ChatSummary(BaseModel):
    chat_id: str
    title: str
    updated_at: str
    created_at: Optional[str] = None
    chat_type: Optional[str] = None

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str

class ChatDetail(BaseModel):
    chat_id: str
    user_id: str
    title: str
    conversation: List[ChatMessage]
    created_at: str
    updated_at: str

@chat_history_router.post("/save", response_model=ChatSummary)
async def save_chat(
    request: SaveChatRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Save or update a chat conversation
    """
    user_id = current_user.get("uid")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # Get previous conversation if chat_id is provided(if chat_id is not provided, this will stay empty)
    previous_convo = []
    if request.chat_id:
        try:
            chat_data = await get_chat_by_id(user_id, request.chat_id)
            # Only take the last 10 messages(to keep context window small)
            conversation = chat_data.get('conversation', [])[-10:]
            for msg in conversation:
                if msg.get('role') == 'user':
                    previous_convo.append(f"User: {msg.get('content', '')}")
        except HTTPException as e:
            if e.status_code != 404:
                raise e
    
    result = await save_or_update_chat(
        user_id=user_id,
        chat_id=request.chat_id,
        question=request.question,
        previous_convo=previous_convo,
        answer=request.answer
    )
    
    return result

@chat_history_router.get("/titles", response_model=List[ChatSummary])
async def list_chat_titles(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all chat titles for the current user
    """
    user_id = current_user.get("uid")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    chat_titles = await get_chat_titles(user_id)
    # Always return chat_type, defaulting to 'basic'
    result = []
    for chat in chat_titles:
        chat_copy = dict(chat)
        # default fallback to basic
        if 'chat_type' not in chat_copy or chat_copy['chat_type'] is None:
            chat_copy['chat_type'] = 'basic'
        result.append(chat_copy)
    return result

@chat_history_router.get("/{chat_id}", response_model=ChatDetail)
async def get_chat_detail(
    chat_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get full chat by chat_id
    """
    user_id = current_user.get("uid")
    if not user_id:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    chat_detail = await get_chat_by_id(user_id, chat_id)
    return chat_detail 