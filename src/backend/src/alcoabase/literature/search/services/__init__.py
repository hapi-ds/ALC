"""Service layer for the Literature Search & Citation UI subsystem (Phase 9.6).

This sub-package provides the LiteratureSearchService, which orchestrates
search execution, internalization, saved searches, citation collections,
and traceability link management. Also provides ExportService for CSV/PDF
export generation.
"""

from alcoabase.literature.search.services.export_service import ExportService

__all__ = [
    "ExportService",
]

# LiteratureSearchService is imported conditionally to avoid import errors
# when it hasn't been implemented yet (it's a separate task).
try:
    from alcoabase.literature.search.services.literature_search_service import (  # noqa: F401
        LiteratureSearchService,
    )

    __all__.append("LiteratureSearchService")
except ImportError:
    pass
