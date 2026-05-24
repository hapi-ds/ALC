"""Role-Play Engine Service for Virtual Audit conversational assessments.

This module implements:
- Session lifecycle management (start, respond, complete, abandon)
- Turn count determination based on document section count
- Session score computation (weighted average: accuracy 50%, completeness 30%, reference 20%)
- Progressive difficulty distribution (foundational 40%, applied 35%, analytical 25%)
- Pass/fail determination (score >= 0.70 AND >= 3 turns completed)
- Stale session abandonment (60+ minutes inactive)

References:
    - Design doc Section 4: Role-Play Engine Service
    - Requirements 6.1–6.13: Role-Play Scenarios — Virtual Audit Engine
    - Educational Specialist archetype (5.1) with temperature 0.4
    - InferenceClient (4.3) handles all LLM inference calls
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.training_ecosystem import (
    SessionStatus,
    VirtualAuditSession,
)

if TYPE_CHECKING:
    from alcoabase.services.agent_registry import AgentRegistryService
    from alcoabase.services.inference_client import InferenceClient
    from alcoabase.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stale session threshold in minutes (Req 6.13)
STALE_SESSION_MINUTES = 60

# Pass threshold for overall session score (Req 6.6)
PASS_SCORE_THRESHOLD = 0.70

# Minimum turns required for pass/fail determination (Req 6.6)
MIN_TURNS_FOR_RESULT = 3

# Temperature for role-play inference (Req 6.1)
ROLEPLAY_TEMPERATURE = 0.4

# Progressive difficulty distribution (Req 6.2)
DIFFICULTY_FOUNDATIONAL_RATIO = 0.40
DIFFICULTY_APPLIED_RATIO = 0.35
# Remaining 25% is analytical


# ---------------------------------------------------------------------------
# Pure functions (stateless, easily testable)
# ---------------------------------------------------------------------------


def compute_total_turns(section_count: int) -> int:
    """Determine total turns for a virtual audit based on document section count.

    Rules:
        - < 10 sections: 5 turns
        - 10–20 sections: 7 turns
        - > 20 sections: 10 turns

    Args:
        section_count: Number of sections in the source document.

    Returns:
        Total number of conversational turns for the session.

    References:
        - Requirements 6.3
        - Design doc: Turn Count Determination
    """
    if section_count < 10:
        return 5
    elif section_count <= 20:
        return 7
    else:
        return 10


def compute_session_score(turns: list[dict[str, float]]) -> float:
    """Compute overall session score as weighted average of turn scores.

    Weights: factual_accuracy 50%, completeness 30%, document_reference_quality 20%.
    Only completed turns (those with all three dimensions) are included.

    Args:
        turns: List of turn score dicts, each containing:
            - factual_accuracy (float 0.0–1.0)
            - completeness (float 0.0–1.0)
            - document_reference_quality (float 0.0–1.0)

    Returns:
        Weighted average score (0.0–1.0). Returns 0.0 if no valid turns.

    References:
        - Requirements 6.5
        - Design doc: Session Score Computation
    """
    if not turns:
        return 0.0

    total = 0.0
    count = 0
    for turn in turns:
        accuracy = turn.get("factual_accuracy")
        completeness = turn.get("completeness")
        reference = turn.get("document_reference_quality")
        if accuracy is not None and completeness is not None and reference is not None:
            total += float(accuracy) * 0.5 + float(completeness) * 0.3 + float(reference) * 0.2
            count += 1

    return total / count if count > 0 else 0.0


def determine_pass_fail(score: float, turns_completed: int) -> bool | None:
    """Determine pass/fail for a virtual audit session.

    A session passes if:
        - The overall score is >= 0.70, AND
        - At least 3 turns were completed.

    If fewer than 3 turns are completed, the session is marked as
    "Incomplete" (returns None) regardless of score.

    Args:
        score: Overall session score in [0.0, 1.0].
        turns_completed: Number of turns the user completed.

    Returns:
        True if passed, False if failed, None if incomplete (< 3 turns).

    References:
        - Requirements 6.6: Pass threshold >= 0.70 AND >= 3 turns
    """
    if turns_completed < MIN_TURNS_FOR_RESULT:
        return None  # Incomplete
    return score >= PASS_SCORE_THRESHOLD

