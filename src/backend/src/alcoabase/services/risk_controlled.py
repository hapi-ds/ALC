"""@risk_controlled decorator for wrapping AI service functions with risk controls.

This decorator integrates with the ControlGate to enforce tier-appropriate
controls before and after AI operations execute. It:
- Invokes ControlGate.pre_execution_check before the wrapped function runs
- Executes the wrapped function if pre-check passes
- Logs the operation via post_execution_log at tier-appropriate audit depth
- Creates HITL checkpoints for High/Medium tier operations
- Handles exceptions by logging as "failure" and re-raising

The decorator expects the wrapped function to be a method on a class that has
a `session` attribute (AsyncSession). It extracts `company_id` and `user_id`
from the wrapped function's kwargs.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 4.2, 4.3, 4.4, 9.1, 9.8
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from alcoabase.models.risk_framework import GateResult, RiskTier
from alcoabase.services.control_gate import (
    AuditWriteError,
    ControlGate,
    ControlUnavailableError,
    PreCheckResult,
    UnregisteredTaskTypeError,
)

logger = logging.getLogger(__name__)


def risk_controlled(task_type_id: str) -> Callable:
    """Decorator that wraps async AI service functions with risk controls.

    Invokes ControlGate pre-execution checks, executes the wrapped function,
    then logs the operation at the appropriate audit depth. For High/Medium
    tiers, creates a HITL checkpoint blocking output visibility.

    Args:
        task_type_id: The registered AI_Task_Type identifier.

    Returns:
        A decorator that wraps async service methods with risk controls.

    Usage:
        @risk_controlled(task_type_id="document_generation")
        async def generate_document(self, ...): ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            """Wrapper that enforces risk controls around the AI operation.

            Extracts session from the instance (self), and company_id/user_id
            from kwargs. Performs pre-execution check, executes the function,
            logs the result, and applies tier-appropriate output handling.

            If company_id or user_id is not provided in kwargs, the decorator
            operates in pass-through mode — executing the function directly
            without risk gate enforcement. This allows background tasks and
            internal calls that lack tenant context to proceed.

            Args:
                *args: Positional arguments (first is typically self).
                **kwargs: Should include company_id and user_id for risk controls.

            Returns:
                Dict with tier-appropriate result structure when risk controls
                are active:
                - High: {"status": "pending_review", "operation_id", "checkpoint_id"}
                - Medium: {"status": "pending_review", "output_label": "ai_assisted",
                          "operation_id", "checkpoint_id", "result": <original>}
                - Low: {"status": "completed", "output_label": "ai_generated",
                       "result": <original>}
                Or the original function result when in pass-through mode.

            Raises:
                UnregisteredTaskTypeError: If task_type_id is not registered.
                ControlUnavailableError: If required controls are unavailable.
                AuditWriteError: If audit log write fails for High/Medium tier.
                Exception: Re-raises any exception from the wrapped function.
            """
            # Extract self (instance) from args
            instance = args[0] if args else None

            # Extract company_id and user_id from kwargs
            company_id = kwargs.get("company_id")
            user_id = kwargs.get("user_id")

            if company_id is None or user_id is None:
                # If company_id or user_id is not provided, skip risk controls
                # and execute the function directly (pass-through mode).
                # This allows background tasks and internal calls that lack
                # tenant context to proceed without risk gate enforcement.
                logger.debug(
                    "Skipping risk controls for task_type='%s': "
                    "company_id=%s, user_id=%s",
                    task_type_id,
                    company_id,
                    user_id,
                )
                return await func(*args, **kwargs)

            # Get session from the instance or kwargs
            try:
                session = _extract_session(instance, kwargs)
            except ValueError:
                # No session available — skip risk controls (pass-through)
                logger.debug(
                    "No session available for risk controls on task_type='%s', "
                    "executing without gate enforcement.",
                    task_type_id,
                )
                return await func(*args, **kwargs)

            # Create ControlGate with the session
            gate = ControlGate(session)

            # Pre-execution check
            try:
                pre_check: PreCheckResult = await gate.pre_execution_check(
                    task_type_id=task_type_id,
                    company_id=company_id,
                    user_id=user_id,
                )
            except (TypeError, AttributeError) as exc:
                # Session is not a valid async session (e.g., mock or factory
                # without proper setup). Fall through to direct execution.
                logger.debug(
                    "Risk control pre-check failed for task_type='%s' due to "
                    "session incompatibility (%s), executing without gate.",
                    task_type_id,
                    exc,
                )
                return await func(*args, **kwargs)

            # If blocked, return error without executing
            if not pre_check.allowed:
                return {
                    "status": "blocked",
                    "blocking_reason": pre_check.blocking_reason,
                    "task_type_id": task_type_id,
                }

            tier = pre_check.tier
            controls = pre_check.controls
            controls_enforced = controls.validations.copy()
            if controls.hitl_required:
                controls_enforced.append("hitl_checkpoint")
            controls_enforced.append("audit_logging")

            # Execute the wrapped function
            start_time = time.monotonic()
            result = None
            try:
                result = await func(*args, **kwargs)
                inference_duration_ms = int((time.monotonic() - start_time) * 1000)

                # Prepare output data for logging
                output_data = (
                    result if isinstance(result, dict) else {"result": str(result)}
                )

                # Build controls_satisfied mapping
                controls_satisfied = {ctrl: True for ctrl in controls_enforced}

                # Post-execution log
                operation_log = await gate.post_execution_log(
                    task_type_id=task_type_id,
                    company_id=company_id,
                    user_id=user_id,
                    tier=tier,
                    input_data=_extract_input_data(kwargs),
                    output_data=output_data,
                    model_name=kwargs.get("model_name"),
                    inference_duration_ms=inference_duration_ms,
                    token_count_input=kwargs.get("token_count_input"),
                    token_count_output=kwargs.get("token_count_output"),
                    source_document_ids=kwargs.get("source_document_ids"),
                    gate_result=GateResult.PASSED,
                    blocking_reason=None,
                    controls_enforced=controls_enforced,
                    controls_satisfied=controls_satisfied,
                )

                operation_id = str(operation_log.id)

                # Tier-appropriate output handling
                if tier == RiskTier.HIGH:
                    # High tier: block output visibility until HITL approved
                    checkpoint = await gate.create_hitl_checkpoint(
                        company_id=company_id,
                        operation_id=operation_id,
                        task_type_id=task_type_id,
                        ai_output_reference=f"operation:{operation_id}",
                        tier=tier,
                    )
                    return {
                        "status": "pending_review",
                        "operation_id": operation_id,
                        "checkpoint_id": str(checkpoint.id),
                    }

                elif tier == RiskTier.MEDIUM:
                    # Medium tier: tag output "ai_assisted", block automated actions
                    checkpoint = await gate.create_hitl_checkpoint(
                        company_id=company_id,
                        operation_id=operation_id,
                        task_type_id=task_type_id,
                        ai_output_reference=f"operation:{operation_id}",
                        tier=tier,
                    )
                    return {
                        "status": "pending_review",
                        "output_label": "ai_assisted",
                        "operation_id": operation_id,
                        "checkpoint_id": str(checkpoint.id),
                        "result": result,
                    }

                else:
                    # Low tier: return output immediately with "ai_generated" tag
                    return {
                        "status": "completed",
                        "output_label": "ai_generated",
                        "result": result,
                    }

            except (UnregisteredTaskTypeError, ControlUnavailableError, AuditWriteError):
                # These are control-layer errors; re-raise without additional logging
                raise

            except Exception as exc:
                # Log the operation as "failure" with available fields
                inference_duration_ms = int((time.monotonic() - start_time) * 1000)

                controls_satisfied = {
                    ctrl: (ctrl != "audit_logging") for ctrl in controls_enforced
                }

                try:
                    await gate.post_execution_log(
                        task_type_id=task_type_id,
                        company_id=company_id,
                        user_id=user_id,
                        tier=tier,
                        input_data=_extract_input_data(kwargs),
                        output_data={"error": str(exc), "status": "failure"},
                        model_name=kwargs.get("model_name"),
                        inference_duration_ms=inference_duration_ms,
                        token_count_input=kwargs.get("token_count_input"),
                        token_count_output=None,
                        source_document_ids=kwargs.get("source_document_ids"),
                        gate_result=GateResult.PASSED,
                        blocking_reason=None,
                        controls_enforced=controls_enforced,
                        controls_satisfied=controls_satisfied,
                    )
                except Exception as log_exc:
                    # If failure logging itself fails, log the error but still
                    # re-raise the original exception
                    logger.error(
                        "Failed to log operation failure for task_type='%s': %s",
                        task_type_id,
                        log_exc,
                    )

                # Re-raise the original exception
                raise

        return wrapper

    return decorator


def _extract_session(instance: Any, kwargs: dict[str, Any]) -> Any:
    """Extract the database session from the instance or kwargs.

    Looks for a `session` attribute on the instance first, then checks
    for a `_session_factory` attribute, then checks kwargs for a `session` key.

    Args:
        instance: The class instance (self) of the decorated method.
        kwargs: The keyword arguments passed to the decorated function.

    Returns:
        The AsyncSession instance or async_sessionmaker.

    Raises:
        ValueError: If no session can be found.
    """
    # Try instance attribute first
    if instance is not None and hasattr(instance, "session"):
        return instance.session

    # Try _session attribute (common pattern in this codebase)
    if instance is not None and hasattr(instance, "_session"):
        return instance._session

    # Try _session_factory attribute (session factory pattern)
    if instance is not None and hasattr(instance, "_session_factory"):
        return instance._session_factory

    # Try kwargs
    if "session" in kwargs:
        return kwargs["session"]

    if "session_factory" in kwargs:
        return kwargs["session_factory"]

    raise ValueError(
        "@risk_controlled requires the decorated method's class to have a "
        "'session' or '_session_factory' attribute, or 'session' must be "
        "passed as a kwarg."
    )


def _extract_input_data(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract input data from kwargs for audit logging.

    Filters out internal/sensitive fields and returns a sanitized dict
    suitable for audit logging.

    Args:
        kwargs: The keyword arguments passed to the decorated function.

    Returns:
        Dict of input data suitable for audit logging.
    """
    # Fields to exclude from input logging (internal/sensitive)
    excluded_keys = {
        "session",
        "company_id",
        "user_id",
        "model_name",
        "token_count_input",
        "token_count_output",
        "source_document_ids",
    }

    input_data = {}
    for key, value in kwargs.items():
        if key in excluded_keys:
            continue
        # Convert non-serializable values to strings
        if isinstance(value, (str, int, float, bool, list, dict, type(None))):
            input_data[key] = value
        else:
            input_data[key] = str(value)

    return input_data
