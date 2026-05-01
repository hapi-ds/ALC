"""FastAPI router for knowledge query endpoints (RAG chat).

Provides endpoints for:
- POST /api/knowledge/query: Single knowledge query with RAG
- POST /api/knowledge/conversation: Conversational follow-up queries

References:
    - Task 13.6: Create FastAPI router /api/knowledge
    - Design doc Section 9: RAG Pipeline
"""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query

from alcoabase.services.rag_pipeline import RAGPipeline

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------


class KnowledgeQueryRequest(BaseModel):
    """Request schema for a knowledge query."""

    question: str = Field(..., min_length=1, description="The user's question")
    user_id: int = Field(..., description="ID of the querying user")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of chunks to retrieve")


class SourceCitationResponse(BaseModel):
    """Response schema for a source citation."""

    document_uuid: str
    title: str
    version: str
    page_or_section: str


class KnowledgeQueryResponse(BaseModel):
    """Response schema for a knowledge query."""

    answer: str
    citations: list[SourceCitationResponse]
    grounded: bool
    conversation_id: str


class ConversationQueryRequest(BaseModel):
    """Request schema for a conversational follow-up query."""

    question: str = Field(..., min_length=1, description="The follow-up question")
    user_id: int = Field(..., description="ID of the querying user")
    conversation_id: str = Field(..., description="Existing conversation ID")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of chunks to retrieve")


class ConversationHistoryResponse(BaseModel):
    """Response schema for conversation history."""

    conversation_id: str
    messages: list[dict[str, str]]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

_rag_pipeline: RAGPipeline | None = None


def get_rag_pipeline() -> RAGPipeline:
    """Provide the RAGPipeline instance as a FastAPI dependency.

    Returns:
        The module-level RAGPipeline instance.
    """
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/query", response_model=KnowledgeQueryResponse)
async def query_knowledge(
    request: KnowledgeQueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
) -> KnowledgeQueryResponse:
    """Query the knowledge base using RAG.

    Retrieves relevant document chunks and generates a grounded answer
    with source citations.

    Args:
        request: The query request with question and user context.
        pipeline: RAGPipeline dependency.

    Returns:
        Generated answer with citations and grounding status.
    """
    response = await pipeline.query(
        question=request.question,
        user_id=request.user_id,
    )

    return KnowledgeQueryResponse(
        answer=response.answer,
        citations=[
            SourceCitationResponse(
                document_uuid=c.document_uuid,
                title=c.title,
                version=c.version,
                page_or_section=c.page_or_section,
            )
            for c in response.citations
        ],
        grounded=response.grounded,
        conversation_id=response.conversation_id,
    )


@router.post("/conversation", response_model=KnowledgeQueryResponse)
async def conversation_query(
    request: ConversationQueryRequest,
    pipeline: RAGPipeline = Depends(get_rag_pipeline),
) -> KnowledgeQueryResponse:
    """Continue a conversation with follow-up questions.

    Uses the existing conversation history for context resolution.

    Args:
        request: The conversation query with question and conversation ID.
        pipeline: RAGPipeline dependency.

    Returns:
        Generated answer with citations and grounding status.
    """
    response = await pipeline.query(
        question=request.question,
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )

    return KnowledgeQueryResponse(
        answer=response.answer,
        citations=[
            SourceCitationResponse(
                document_uuid=c.document_uuid,
                title=c.title,
                version=c.version,
                page_or_section=c.page_or_section,
            )
            for c in response.citations
        ],
        grounded=response.grounded,
        conversation_id=response.conversation_id,
    )
