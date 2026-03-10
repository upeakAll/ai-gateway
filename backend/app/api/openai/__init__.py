"""OpenAI-compatible API endpoints."""

from fastapi import APIRouter

from app.api.openai.chat import router as chat_router
from app.api.openai.embeddings import router as embeddings_router
from app.api.openai.models import router as models_router

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

# Include sub-routers
router.include_router(chat_router)
router.include_router(embeddings_router)
router.include_router(models_router)

__all__ = ["router"]
