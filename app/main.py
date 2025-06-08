from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api.routes import app_router
from .auth.firebase_auth import auth_router

app = FastAPI(title="Legal AI")

# Include auth router (without authentication)
app.include_router(auth_router)

# Include API routes (with authentication)
app.include_router(app_router)

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# default route
@app.get("/")
async def root():
    return {"message": "Welcome to the LegalAI v2 API"}