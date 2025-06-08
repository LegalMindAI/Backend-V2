from fastapi import APIRouter, HTTPException, File, UploadFile, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
import httpx
import os
import logging
import base64
import uuid
import tempfile
import json

# Load functions
from .utils.pdf_handler import extract_text_from_pdf
from ..db.dynamodb import save_or_update_chat, get_chat_by_id
from ..auth.firebase_auth import get_current_user

# Load ENV
load_dotenv()

# Initialize Groq client
groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Base API URL(Update with AWS endpoint)[This is the Backend v1]
BASE_API = "http://localhost"

# Initialize router
app_router = APIRouter()

# Request Schema for Basic Chatting
class BasicChatRequest(BaseModel):
    extracted_text: str = ""
    question: str
    chat_id: str = None  # we will only pass chat_id if we want to continue a conversation

# Request Schema for Advanced Chatting
class AdvancedChatRequest(BaseModel):
    extracted_text: str = ""
    question: str
    chat_id: str = None  # we will only pass chat_id if we want to continue a conversation

# Request Schema for Text to Speech
class TextToSpeechRequest(BaseModel):
    text: str

# Request Schema for Hinglish Chatting
class HinglishChatRequest(BaseModel):
    extracted_text: str = ""
    question: str
    chat_id: str = None  # we will only pass chat_id if we want to continue a conversation

# Helper function to validate UUID
async def validate_chat_id(chat_id: str | None, user_id: str) -> str | None:
    # If chat_id is None, do nothing, we can create
    if chat_id is None:
        return None
        
    # First check UUID format without making any DB calls(this is to avoid unnecessary DB calls and save cost)
    try:
        uuid_obj = uuid.UUID(chat_id)
        chat_id_str = str(uuid_obj)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat_id format. Must be a valid UUID.")
    
    # Only check DynamoDB if UUID format is valid
    try:
        await get_chat_by_id(user_id, chat_id_str)
        return chat_id_str
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=400, detail="Chat ID does not exist.")
        raise e

# Helper function to fetch and format previous conversation
async def get_formatted_previous_convo(user_id: str, chat_id: str):
    previous_convo = []
    if chat_id and user_id:
        try:
            chat_data = await get_chat_by_id(user_id, chat_id)
            # Only include user messages, skip assistant messages(this is to keep the context window small)
            for msg in chat_data.get('conversation', []):
                if msg.get('role') == 'user':
                    previous_convo.append(f"User: {msg.get('content', '')}")
        except HTTPException as e:
            if e.status_code != 404:
                raise e
            # continue with empty previous_convo
    return previous_convo

# endpoint for uploading pdf
@app_router.post("/pdf-upload")
async def pdf_upload(
    file: UploadFile = File(...)
):
    MAX_FILE_SIZE = 4 * 1024 * 1024 # 4MB
    
    # Validations
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # size check
    file_data = await file.read()
    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds 4MB")
    
    await file.seek(0)

    text = extract_text_from_pdf(file_data)

    return {"extracted_text": text}


# Endpoint for Basic Chatting
@app_router.post("/chat-basic")
async def chat_basic(request: BasicChatRequest, current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user.get("uid")
        # Validate chat_id
        validated_chat_id = await validate_chat_id(request.chat_id, user_id)
        previous_convo = await get_formatted_previous_convo(user_id, validated_chat_id)
        
        completion = groq.chat.completions.create(
            model = "mistral-saba-24b",
            messages= [
                {
                    "role": "system",
                    "content": "You are a helpful Lawyer based in India. You are given a question and a context. You need to answer the question based on the context. You need to answer in the same language as the question. Always return a JSON object with an 'answer' field containing your response."
                },
                {
                    "role": "user",
                    "content": f"Context:{request.extracted_text}"
                },
                {
                    "role": "user",
                    "content": f"Question: {request.question}"
                },
                {
                    "role": "user",
                    "content": "Previous Conversation:\n" + "\n".join(previous_convo)
                }
            ],
            temperature=0.7,
            max_completion_tokens=1024,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
            stop=None
        )

        answer = completion.choices[0].message.content if completion.choices else None

        if answer:
            answer_json = json.loads(answer)
            answer_text = answer_json.get("answer", "")

            if user_id:
                await save_or_update_chat(
                    user_id=user_id,
                    chat_id=validated_chat_id,
                    question=request.question,
                    previous_convo=previous_convo,
                    answer=answer_text
                )
            
            return answer_json
        else:
            raise HTTPException(status_code=500, detail="No response, Try again")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Endpoint for Advanced Chatting
@app_router.post("/chat-advanced")
async def chat_advanced(request: AdvancedChatRequest, current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user.get("uid")
        # Validate chat_id
        validated_chat_id = await validate_chat_id(request.chat_id, user_id)
        previous_convo = await get_formatted_previous_convo(user_id, validated_chat_id)
        
        # Retrieve previous cases using the research endpoint
        research_payload = {
            "query": request.question,
            "top_k": 2
        }
        
        async with httpx.AsyncClient() as client:
            research_response = await client.post(
                f"{BASE_API}/fetch",
                json=research_payload,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json"
                }
            )
            
        if research_response.status_code == 200:
            previous_cases = research_response.json()
            # Log the response, truncated by 30 characters
            response_text = str(previous_cases)
            truncated_response = response_text[:-30] if len(response_text) > 30 else response_text
            logging.info(f"Research response (truncated): {truncated_response}")
        else:
            previous_cases = {}  # Fallback if research endpoint fails
            logging.warning(f"Research endpoint failed with status: {research_response.status_code}")
        
        completion = groq.chat.completions.create(
            model = "qwen-qwq-32b",
            messages= [
                {
                    "role": "system",
                    "content": "You're a helpful Lawyer based in India. You are given a question and a context We've also implmented RAG (Retrieval-Augmented Generation) to retrive previous cases and their verdicts. You need to answer the question based on the context and those previous cases. You need to answer in the same language as the question."
                },
                {
                    "role": "user",
                    "content": f"Previous Cases: {previous_cases}"
                },
                {
                    "role": "user",
                    "content": f"Context: {request.extracted_text}"
                },
                {
                    "role": "user",
                    "content": f"Question: {request.question}"
                },
                {
                    "role": "user",
                    "content": f"Previous Conversation: {previous_convo}"
                }
            ],
            temperature=0.7,
            max_completion_tokens=4096,
            top_p=0.95,
            stream=False,
            stop=None,
        )

        answer = completion.choices[0].message.content if completion.choices else None

        if answer:
            # Store chat history if user is authenticated
            if user_id:
                await save_or_update_chat(
                    user_id=user_id,
                    chat_id=validated_chat_id,
                    question=request.question,
                    previous_convo=previous_convo,
                    answer=answer
                )
                
            return {
                "answer": answer
            }
        else:
            raise HTTPException(status_code=500, detail="No response, Try again")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Endpoint for Image OCR
@app_router.post("/image-ocr")
async def image_ocr(
    file: UploadFile = File(...)
):
    # convert image to base64 with proper data URL format
    image_data = await file.read()
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Create data URL
    data_url = f"data:{file.content_type};base64,{base64_image}"

    try:
        completion = groq.chat.completions.create(
            model = "meta-llama/llama-4-scout-17b-16e-instruct",
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful Lawyer based in India. You are given an image of a document. You need to extract the text from the image. You need to return the text in a JSON format as {text: <text>}"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Please extract all text from this document image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url
                            }
                        }
                    ]
                }
            ],
            temperature=0.7,
            max_completion_tokens=1024,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
            stop=None
        )

        answer = completion.choices[0].message.content if completion.choices else None

        if answer:
            return answer
        else:
            raise HTTPException(status_code=500, detail="No response, Try again")    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app_router.post("/text-to-speech")
async def text_to_speech(request: TextToSpeechRequest):
    try:
        response = groq.audio.speech.create(
            model="playai-tts-arabic",
            voice="Nasser-PlayAI",
            response_format="wav",
            input=request.text,
        )
        
        # Generate unique filename
        audio_id = str(uuid.uuid4())
        temp_dir = Path(tempfile.gettempdir())
        audio_file_path = temp_dir / f"speech_{audio_id}.wav"
        
        # Save the audio file
        with open(audio_file_path, "wb") as f:
            f.write(response.read())
        
        return {
            "message": "Speech generated successfully",
            "audio_id": audio_id,
            "audio_url": f"/audio/{audio_id}",
            "text": request.text
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating speech: {str(e)}")

# Route to play the audio
@app_router.get("/audio/{audio_id}")
async def get_audio(audio_id: str):
    try:
        # Validate audio_id format (should be a valid UUID)
        uuid.UUID(audio_id)
        
        temp_dir = Path(tempfile.gettempdir())
        audio_file_path = temp_dir / f"speech_{audio_id}.wav"
        
        if not audio_file_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            audio_file_path,
            media_type="audio/wav",
            filename=f"speech_{audio_id}.wav",
            headers={"Content-Disposition": "inline"}
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid audio ID")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving audio: {str(e)}")

@app_router.post("/speech-to-text")
async def speech_to_text(
    file: UploadFile = File(...)
):
    try:
        # Validate file type (accept common audio formats including variations)
        allowed_types = [
            "audio/mpeg", "audio/wav", "audio/m4a", "audio/x-m4a", 
            "audio/mp3", "audio/flac", "audio/ogg", "audio/webm",
            "audio/aac", "audio/mp4"
        ]
        
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail=f"File type '{file.content_type}' not supported. Supported types: {allowed_types}")
        
        # Read file content
        file_content = await file.read()
        
        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Create transcription using Groq
        transcription = groq.audio.transcriptions.create(
            file=(file.filename, file_content),
            model="whisper-large-v3-turbo",
            prompt="Translate to english from the language in the audio",
            response_format="verbose_json",
        )
        
        return {
            "transcription": transcription.text,
            "language": getattr(transcription, 'language', None),
            "duration": getattr(transcription, 'duration', None),
            "filename": file.filename
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error transcribing audio: {type(e).__name__}: {str(e)}")

@app_router.post("/chat-hinglish")
async def chat_hinglish(request: HinglishChatRequest, current_user: dict = Depends(get_current_user)):
    try:
        user_id = current_user.get("uid")
        # Validate chat_id
        validated_chat_id = await validate_chat_id(request.chat_id, user_id)
        previous_convo = await get_formatted_previous_convo(user_id, validated_chat_id)
        
        # First translate the Hinglish question to English for better RAG search
        translation_completion = groq.chat.completions.create(
            model="qwen-qwq-32b",
            messages=[
                {
                    "role": "system",
                    "content": "You are a translator. Translate the given Hinglish text to proper English. Only return the English translation, nothing else."
                },
                {
                    "role": "user",
                    "content": f"Translate this Hinglish text to English: {request.question}"
                }
            ],
            temperature=0.3,
            max_completion_tokens=512,
            top_p=0.95,
            stream=False,
            stop=None,
        )
        
        translated_question = translation_completion.choices[0].message.content if translation_completion.choices else request.question
        
        # Retrieve previous cases using the translated English question
        research_payload = {
            "query": translated_question,
            "top_k": 2
        }
        
        async with httpx.AsyncClient() as client:
            research_response = await client.post(
                f"{BASE_API}/fetch",
                json=research_payload,
                headers={
                    "accept": "application/json",
                    "Content-Type": "application/json"
                }
            )
            
        if research_response.status_code == 200:
            previous_cases = research_response.json()
            # Log the response, truncated by 30 characters
            response_text = str(previous_cases)
            truncated_response = response_text[:-30] if len(response_text) > 30 else response_text
            logging.info(f"Research response (truncated): {truncated_response}")
        else:
            previous_cases = {}  # Fallback if research endpoint fails
            logging.warning(f"Research endpoint failed with status: {research_response.status_code}")
        
        completion = groq.chat.completions.create(
            model = "qwen-qwq-32b",
            messages= [
                {
                    "role": "system",
                    "content": "You're a helpful Lawyer based in India. You are given a question and a context. We've also implemented RAG (Retrieval-Augmented Generation) to retrieve previous cases and their verdicts. You need to answer the question based on the context and those previous cases. You MUST answer in romanized Hinglish only - that means Hindi words written in English script (Roman alphabet), mixed with English words. Do NOT use Devanagari script. Example: 'Aapka case bahut strong hai, court mein jeet ke chances zyada hain.'"
                },
                {
                    "role": "user",
                    "content": f"Previous Cases: {previous_cases}"
                },
                {
                    "role": "user",
                    "content": f"Context: {request.extracted_text}"
                },
                {
                    "role": "user",
                    "content": f"Question: {request.question}"
                },
                {
                    "role": "user",
                    "content": f"Previous Conversation: {previous_convo}"
                }
            ],
            temperature=0.7,
            max_completion_tokens=4096,
            top_p=0.95,
            stream=False,
            stop=None,
        )

        answer = completion.choices[0].message.content if completion.choices else None

        if answer:
            # Store chat history if user is authenticated
            if user_id:
                await save_or_update_chat(
                    user_id=user_id,
                    chat_id=validated_chat_id,
                    question=request.question,
                    previous_convo=previous_convo,
                    answer=answer
                )
                
            return {
                "answer": answer
            }
        else:
            raise HTTPException(status_code=500, detail="No response, Try again")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")