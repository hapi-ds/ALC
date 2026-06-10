"""Literature source adapters (plugin directory).

This package contains the abstract base adapter interface and built-in
adapters for PubMed, Crossref, and arXiv. Custom adapters placed in the
configured adapter directory are discovered at startup.
"""

from alcoabase.literature.adapters.base import AdapterMetadata, BaseSourceAdapter

__all__ = ["AdapterMetadata", "BaseSourceAdapter"]
