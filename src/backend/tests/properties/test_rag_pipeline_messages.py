"""Property-based tests for RAG pipeline chat completion message structure.

Tests Property 4 from the AI Model Integration (vLLM) design document,
validating that the messages array sent to `/v1/chat/completions` contains:
1. A system message with grounding instructions as the first element
2. Conversation history messages as alternating user/assistant pairs (limited to last 6)
3. The context as a user message
4. The current question as the final user message

**Validates: Requirements 2.2**

References:
    - Design: .kiro/specs/Step_4-3_ai-model-integration-vllm/design.md (Property 4)
    - Requirements: .kiro/specs/Step_4-3_ai-model-integration-vllm/requirements.md (2.2)
"""

# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.rag_pipeline import ConversationMessage, RAGPipeline


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for generating non-empty question strings
st_question = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# Strategy for generating non-empty context strings
st_context = st.text(min_size=1, max_size=500).filter(lambda s: s.strip())

# Strategy for generating a single conversation message
st_conversation_message = st.builds(
    ConversationMessage,
    role=st.sampled_from(["user", "assistant"]),
    content=st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
)

# Strategy for generating conversation history as alternating user/assistant pairs
# History should be pairs of (user, assistant) messages
st_history_pair = st.tuples(
    st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
    st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
)

st_history_pairs = st.lists(st_history_pair, min_size=0, max_size=5)


def _build_history_from_pairs(
    pairs: list[tuple[str, str]],
) -> list[ConversationMessage]:
    """Build a conversation history from user/assistant pairs."""
    history: list[ConversationMessage] = []
    for user_content, assistant_content in pairs:
        history.append(ConversationMessage(role="user", content=user_content))
        history.append(ConversationMessage(role="assistant", content=assistant_content))
    return history


# Strategy for generating arbitrary-length history (may not be perfectly paired)
st_arbitrary_history = st.lists(st_conversation_message, min_size=0, max_size=10)


# ---------------------------------------------------------------------------
# Property 4a: First message is always a system message with grounding instructions
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history_pairs=st_history_pairs,
)
def test_first_message_is_system_with_grounding(
    question: str,
    context: str,
    history_pairs: list[tuple[str, str]],
) -> None:
    """For any combination of question, context, and conversation history,
    the first message in the messages array SHALL be a system message
    containing grounding instructions.

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()
    history = _build_history_from_pairs(history_pairs)

    messages = pipeline._build_messages(question, context, history)

    # First message must be system role
    assert messages[0]["role"] == "system", (
        f"Expected first message role to be 'system', got '{messages[0]['role']}'"
    )

    # System message must contain grounding instructions
    system_content = messages[0]["content"]
    assert "context" in system_content.lower() or "provided" in system_content.lower(), (
        "System message should contain grounding instructions about context"
    )
    assert "Source" in system_content or "source" in system_content, (
        "System message should mention source citation format"
    )
    assert "fabricate" in system_content.lower() or "never" in system_content.lower(), (
        "System message should instruct not to fabricate information"
    )


# ---------------------------------------------------------------------------
# Property 4b: History messages follow system message as user/assistant pairs
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history_pairs=st_history_pairs,
)
def test_history_messages_follow_system_as_pairs(
    question: str,
    context: str,
    history_pairs: list[tuple[str, str]],
) -> None:
    """For any conversation history, the history messages SHALL appear
    after the system message as user/assistant role messages, limited
    to the last 6 messages.

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()
    history = _build_history_from_pairs(history_pairs)

    messages = pipeline._build_messages(question, context, history)

    # Calculate expected history messages (limited to last 6)
    expected_history = history[-6:]
    num_history = len(expected_history)

    # History messages start at index 1 (after system message)
    history_section = messages[1 : 1 + num_history]

    # Verify each history message matches
    for i, (msg, expected) in enumerate(zip(history_section, expected_history)):
        assert msg["role"] == expected.role, (
            f"History message {i} role mismatch: expected '{expected.role}', "
            f"got '{msg['role']}'"
        )
        assert msg["content"] == expected.content, (
            f"History message {i} content mismatch"
        )


# ---------------------------------------------------------------------------
# Property 4c: History is limited to last 6 messages
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history_pairs=st.lists(st_history_pair, min_size=4, max_size=8),
)
def test_history_limited_to_last_6_messages(
    question: str,
    context: str,
    history_pairs: list[tuple[str, str]],
) -> None:
    """For any conversation history with more than 6 messages,
    only the last 6 messages SHALL be included in the messages array.

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()
    history = _build_history_from_pairs(history_pairs)

    messages = pipeline._build_messages(question, context, history)

    # Count history messages in the output (between system and context+question)
    # Total structure: system(1) + history(N) + context(1) + question(1)
    num_history_in_output = len(messages) - 3  # subtract system, context, question

    # History should be at most 6 messages
    assert num_history_in_output <= 6, (
        f"Expected at most 6 history messages, got {num_history_in_output}"
    )

    # If original history has more than 6, exactly 6 should be included
    if len(history) > 6:
        assert num_history_in_output == 6, (
            f"Expected exactly 6 history messages when history has {len(history)} "
            f"messages, got {num_history_in_output}"
        )


# ---------------------------------------------------------------------------
# Property 4d: Context appears as a user message before the question
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history_pairs=st_history_pairs,
)
def test_context_appears_as_user_message(
    question: str,
    context: str,
    history_pairs: list[tuple[str, str]],
) -> None:
    """For any context string, it SHALL appear as a user message
    in the messages array, positioned after history and before the question.

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()
    history = _build_history_from_pairs(history_pairs)

    messages = pipeline._build_messages(question, context, history)

    # Context message is the second-to-last message
    context_msg = messages[-2]

    assert context_msg["role"] == "user", (
        f"Expected context message role to be 'user', got '{context_msg['role']}'"
    )
    assert context in context_msg["content"], (
        "Context message should contain the context text"
    )


# ---------------------------------------------------------------------------
# Property 4e: Current question is the final user message
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history_pairs=st_history_pairs,
)
def test_question_is_final_message(
    question: str,
    context: str,
    history_pairs: list[tuple[str, str]],
) -> None:
    """For any question string, it SHALL be the final user message
    in the messages array.

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()
    history = _build_history_from_pairs(history_pairs)

    messages = pipeline._build_messages(question, context, history)

    # Last message must be the question
    last_msg = messages[-1]

    assert last_msg["role"] == "user", (
        f"Expected final message role to be 'user', got '{last_msg['role']}'"
    )
    assert last_msg["content"] == question, (
        f"Expected final message content to be the question, "
        f"got '{last_msg['content'][:50]}...'"
    )


# ---------------------------------------------------------------------------
# Property 4f: Overall message structure ordering is correct
# ---------------------------------------------------------------------------


# Feature: Step_4-3_ai-model-integration-vllm, Property 4: Chat completion message structure
@settings(max_examples=100, deadline=None)
@given(
    question=st_question,
    context=st_context,
    history=st_arbitrary_history,
)
def test_overall_message_structure(
    question: str,
    context: str,
    history: list[ConversationMessage],
) -> None:
    """For any combination of question, context, and conversation history,
    the messages array SHALL have the structure:
    [system, ...history (max 6), context_user, question_user].

    **Validates: Requirements 2.2**
    """
    pipeline = RAGPipeline()

    messages = pipeline._build_messages(question, context, history)

    # Minimum length: system + context + question = 3
    assert len(messages) >= 3, (
        f"Expected at least 3 messages, got {len(messages)}"
    )

    # Maximum length: system + 6 history + context + question = 9
    assert len(messages) <= 9, (
        f"Expected at most 9 messages (1 system + 6 history + 1 context + 1 question), "
        f"got {len(messages)}"
    )

    # First is always system
    assert messages[0]["role"] == "system"

    # Last is always the question
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == question

    # Second to last is always the context
    assert messages[-2]["role"] == "user"
    assert context in messages[-2]["content"]

    # All messages have 'role' and 'content' keys
    for i, msg in enumerate(messages):
        assert "role" in msg, f"Message {i} missing 'role' key"
        assert "content" in msg, f"Message {i} missing 'content' key"
        assert msg["role"] in ("system", "user", "assistant"), (
            f"Message {i} has invalid role '{msg['role']}'"
        )
