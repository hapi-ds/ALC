"""ALC Documentation Suite Generation Script.

Generates 2 guide documents (User Guide + Admin Guide), uploads them into
the ALC corporate governance environment, applies tags and the governance
workflow, and supports versioning on re-execution.

All operations execute within a single database transaction. On success
the transaction is committed and the DocumentationGenerationReport is printed
to stdout as JSON. On failure the transaction is rolled back and error
details are printed to stderr as JSON.

Usage:
    uv run python -m alcoabase.scripts.generate_documentation

Exit codes:
    0 — Success (DocumentationGenerationReport printed to stdout as JSON)
    1 — Failure (DocumentationGenerationError printed to stderr as JSON)

References:
    - Design doc: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
    - Requirements: 4.1, 4.5
"""

import asyncio
import sys

from alcoabase.database import init_db
from alcoabase.schemas.documentation_generation import DocumentationGenerationError
from alcoabase.services.documentation_generator_service import (
    DocumentationGeneratorService,
)


def _classify_failed_operation(error_message: str) -> tuple[str, str | None]:
    """Classify the failed operation from the error message.

    Args:
        error_message: The exception message string.

    Returns:
        Tuple of (failed_operation, document_title or None).
    """
    msg = error_message.lower()

    if "not provisioned" in msg or "not found" in msg:
        return "prerequisite_check", None
    if "already in progress" in msg or "advisory" in msg:
        return "concurrent_lock", None
    if "cross-reference" in msg or "cross_reference" in msg:
        return "cross_reference_load", None
    if "content" in msg or "heading" in msg or "empty" in msg or "section" in msg:
        return "content_generation", None
    if "upload" in msg or "storage" in msg or "minio" in msg:
        return "document_upload", None
    if "tag" in msg:
        return "tag_application", None
    if "workflow" in msg and "not found" not in msg:
        return "workflow_assignment", None

    return "prerequisite_check", None


async def main() -> None:
    """Execute the ALC Documentation Suite generation sequence.

    Creates an async database session, runs the full documentation generator
    service within a single transaction, and handles commit/rollback based
    on outcome.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.database import get_engine

    # Initialize the database engine
    await init_db()
    engine = get_engine()

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            service = DocumentationGeneratorService(session)
            report = await service.execute()
            await session.commit()

            # Print DocumentationGenerationReport as JSON to stdout
            print(report.model_dump_json(indent=2))

        except Exception as exc:
            await session.rollback()

            # Construct and print DocumentationGenerationError as JSON to stderr
            error_message = str(exc)
            failed_operation, document_title = _classify_failed_operation(
                error_message
            )

            error_response = DocumentationGenerationError(
                error=error_message,
                failed_operation=failed_operation,
                document_title=document_title,
                detail=error_message,
            )
            print(error_response.model_dump_json(indent=2), file=sys.stderr)
            sys.exit(1)

    # Dispose the engine to cleanly close connections
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
