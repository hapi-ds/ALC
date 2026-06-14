"""Content type utilities for document viewing and downloading.

Pure functions for MIME type resolution, previewability classification,
and RFC 6266 Content-Disposition header construction. No side effects,
no async, no database dependencies.
"""

import os
from urllib.parse import quote


# Extension-to-MIME mapping for common document types
EXTENSION_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

# Content types that can be rendered inline in a browser
PREVIEWABLE_TYPES: set[str] = {
    "application/pdf",
    "text/markdown",
    "text/plain",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def resolve_content_type(stored_content_type: str | None, storage_key: str) -> str:
    """Determine MIME type from stored value or file extension fallback.

    Resolution priority:
      1. If a stored content type is present and non-empty, use it directly.
      2. Infer from the file extension of the storage key using the
         extension-to-MIME mapping.
      3. Fall back to ``application/octet-stream`` if no match is found.

    Args:
        stored_content_type: The content type persisted at upload time,
            or None if not available.
        storage_key: The object storage key (path) for the file, used
            to extract the file extension.

    Returns:
        A MIME type string. Never returns an empty string.
    """
    if stored_content_type and stored_content_type.strip():
        return stored_content_type.strip()

    _, ext = os.path.splitext(storage_key)
    ext_lower = ext.lower()

    if ext_lower in EXTENSION_MIME_MAP:
        return EXTENSION_MIME_MAP[ext_lower]

    return "application/octet-stream"


def is_previewable(content_type: str) -> bool:
    """Return True if the content type can be rendered inline in a browser.

    Checks membership against the ``PREVIEWABLE_TYPES`` set which includes
    PDF, markdown, plain text, and common image formats.

    Args:
        content_type: A MIME type string (e.g. ``"application/pdf"``).
            Comparison is case-sensitive per MIME type conventions.

    Returns:
        True if the content type supports inline preview, False otherwise.
    """
    return content_type in PREVIEWABLE_TYPES


def build_content_disposition(disposition: str, filename: str) -> str:
    """Build RFC 6266 Content-Disposition header value with UTF-8 filename encoding.

    Produces a header value containing both an ASCII-safe ``filename``
    parameter (for legacy clients) and a ``filename*`` parameter using
    UTF-8 percent-encoding (RFC 5987) for full Unicode support.

    Args:
        disposition: The disposition type, typically ``"inline"`` or
            ``"attachment"``.
        filename: The suggested filename for the downloaded file. May
            contain Unicode characters and special characters.

    Returns:
        A complete Content-Disposition header value string conforming
        to RFC 6266. Example:
        ``attachment; filename="report.pdf"; filename*=UTF-8''report.pdf``
    """
    # Build ASCII-safe filename by replacing non-ASCII chars
    ascii_filename = filename.encode("ascii", errors="replace").decode("ascii")
    # Remove characters that are problematic in the quoted filename parameter
    ascii_filename = ascii_filename.replace('"', "'").replace("\\", "_")

    # RFC 5987 percent-encode the filename for the filename* parameter
    encoded_filename = quote(filename, safe="")

    return (
        f'{disposition}; '
        f'filename="{ascii_filename}"; '
        f"filename*=UTF-8''{encoded_filename}"
    )
