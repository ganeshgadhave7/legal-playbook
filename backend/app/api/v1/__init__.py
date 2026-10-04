"""Version 1 API routers."""
from app.api.v1.playbooks import router as playbooks_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.source_documents import router as source_documents_router

__all__ = ["source_documents_router", "retrieval_router", "playbooks_router"]
