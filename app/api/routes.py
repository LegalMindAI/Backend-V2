from fastapi import APIRouter, Depends
from app.auth.firebase_auth import get_current_user
from .endpoints import (
    chat_basic,
    chat_advanced,
    pdf_upload,
    text_to_speech,
    speech_to_text,
    image_ocr,
    get_audio,
    chat_hinglish,
    research_wrapper
)

# Create a new router that includes authentication
app_router = APIRouter()

# Route for basic chatting
app_router.post("/chat-basic", dependencies=[Depends(get_current_user)])(chat_basic)

# Route for Advanced Chatting
app_router.post("/chat-advanced", dependencies=[Depends(get_current_user)])(chat_advanced)

#Route for research cases 
app_router.post("/research", dependencies=[Depends(get_current_user)])(research_wrapper)

# Route for Text to Speech
app_router.post("/text-to-speech", dependencies=[Depends(get_current_user)])(text_to_speech)

# Route for Speech to Text
app_router.post("/speech-to-text", dependencies=[Depends(get_current_user)])(speech_to_text)

# Route for Pdf upload
app_router.post("/pdf-upload", dependencies=[Depends(get_current_user)])(pdf_upload)

# Route for Image OCR
app_router.post("/image-ocr", dependencies=[Depends(get_current_user)])(image_ocr)

# Route to Play Audio
app_router.get("/audio/{audio_id}", dependencies=[Depends(get_current_user)])(get_audio)
# Route to chat in local language
app_router.post("/chat-hinglish", dependencies=[Depends(get_current_user)])(chat_hinglish)
