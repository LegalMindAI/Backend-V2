from fastapi import APIRouter
from .endpoints import chat_basic, chat_advanced, pdf_upload,text_to_speech, speech_to_text, image_ocr, get_audio

app_router = APIRouter()

# Route for basic chatting
app_router.post("/chat-basic")(chat_basic)

# Route for Advanced Chatting
app_router.post("/chat-advanced")(chat_advanced)

# Route for Text to Speech
app_router.post("/text-to-speech")(text_to_speech)

# Route for Speech to Text
app_router.post("/speech-to-text")(speech_to_text)

# Route for Pdf upload
app_router.post("/pdf-upload")(pdf_upload)

# Route for Image OCR
app_router.post("/image-ocr")(image_ocr)

# Route to Play Audio
app_router.get("/audio/{audio_id}")(get_audio)
