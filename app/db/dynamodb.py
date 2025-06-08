import os
import boto3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# DynamoDB configs
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = os.getenv("DDB_AWS_REGION")
CHAT_TABLE_NAME = os.getenv("DYNAMODB_CHAT_TABLE")

# Initialize DDB client
dynamodb = boto3.resource(
    'dynamodb',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

# Get the chat table
chat_table = dynamodb.Table(CHAT_TABLE_NAME)

async def save_or_update_chat(user_id: str, chat_id: Optional[str], question: str, 
                              previous_convo: List[str], answer: str) -> Dict[str, Any]:
    """
    This is the function to save or update a chat in DDB

    Arguments:
        user_id: User's UID(this is generating from the firebase auth)
        chat_id: Optional chat ID(if chat id doesn't exist, it will create a new one)
        question: The question
        previous_convo: List of previous conversations (already retrieved from DB if chat_id exists)
        answer: The AI's answer to the question
    """
    current_time = datetime.now().isoformat()
    
    # If new chat, generate chat_id and title from first message
    if not chat_id:
        chat_id = str(uuid.uuid4())
        title = question[:50] + ("..." if len(question) > 50 else "")
        
        # Initialize conversation
        conversation = [{
            "role": "user",
            "content": question,
            "timestamp": current_time
        }, {
            "role": "assistant",
            "content": answer,
            "timestamp": current_time
        }]
    else:
        # Get existing chat to update(this will trigger is user passes a chat_id)
        try:
            response = chat_table.get_item(
                Key={
                    'user_id': user_id,
                    'chat_id': chat_id
                }
            )
            
            if 'Item' not in response:
                # If chat_id provided but not found, raise an error
                raise HTTPException(status_code=404, detail="Chat not found")
            else:
                chat_data = response['Item']
                title = chat_data.get('title', question[:50])
                conversation = chat_data.get('conversation', [])
                current_time_created = chat_data.get('created_at', current_time)
                
                # Add new record to conversation
                conversation.append({
                    "role": "user",
                    "content": question,
                    "timestamp": current_time
                })
                conversation.append({
                    "role": "assistant",
                    "content": answer,
                    "timestamp": current_time
                })
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error retrieving chat: {str(e)}")
    
    # Prepare item for DynamoDB
    chat_item = {
        'user_id': user_id,
        'chat_id': chat_id,
        'title': title,
        'conversation': conversation,
        'updated_at': current_time,
        'created_at': current_time_created if 'current_time_created' in locals() else current_time
    }
    
    # Save to DynamoDB
    try:
        chat_table.put_item(Item=chat_item)
        
        return {
            'chat_id': chat_id,
            'title': title,
            'updated_at': current_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving chat: {str(e)}")

async def get_chat_titles(user_id: str) -> List[Dict[str, Any]]:
    """
    This function will get all chat titles for a user(this will be used to display the chat titles in the sidebar)

    Arguments:
        user_id: User's UID
    """
    try:
        response = chat_table.query(
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={
                ":uid": user_id
            },
            ProjectionExpression="chat_id, title, updated_at, created_at"
        )
        
        # Sort by updated_at in descending order
        chats = sorted(
            response.get('Items', []),
            key=lambda x: x.get('updated_at', ''),
            reverse=True
        )
        
        return chats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chat titles: {str(e)}")

async def get_chat_by_id(user_id: str, chat_id: str) -> Dict[str, Any]:
    """
    Get a specific chat by ID
    
    Arguments:
        user_id: User's UID
        chat_id: Chat ID
    """
    try:
        response = chat_table.get_item(
            Key={
                'user_id': user_id,
                'chat_id': chat_id
            }
        )
        
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        return response['Item']
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error fetching chat: {str(e)}") 