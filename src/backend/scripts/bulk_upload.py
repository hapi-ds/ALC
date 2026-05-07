"""Bulk upload documents from a directory tree to the AlcoaBase API.

Recursively walks a directory and uploads each file as a document via
the /api/v1/documents endpoint, deriving metadata from the file path.

Usage:
    python scripts/bulk_upload.py --directory ./docs --api-url http://localhost:8000 \
        --company-id 1 --user-id 1 --token mytoken

Environment Variables:
    ALCOABASE_TOKEN: Bearer token for API authentication (alternative to --token).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import httpx


class FileMetadata(NamedTuple):
    """Metadata derived from a file's path relative to the root directory."""

    path: Path
    title: str
    folder_path: str


@dataclass
class UploadSummary:
    """Tracks upload results for final summary reporting."""

    total: int = 0
    successful: int = 0
    failed: int = 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the bulk upload tool.

    Args:
        argv: Argument list to parse. Defaults to sys.argv[1:].

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Bulk upload documents from a directory tree to the AlcoaBase API."
    )

    # Required arguments
    parser.add_argument(
        "--directory",
        required=True,
        help="Root directory to recursively walk",
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="Base API URL (e.g., http://localhost:8000)",
    )
    parser.add_argument(
        "--company-id",
        required=True,
        help="Company ID for X-Company-Id header",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID for upload attribution",
    )

    # Optional arguments
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer token (or set ALCOABASE_TOKEN env var)",
    )
    parser.add_argument(
        "--document-type",
        default="General",
        help='Document type for all uploads (default: "General")',
    )
    parser.add_argument(
        "--tags",
        default="",
        help="Comma-separated tags to apply to all uploads",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files without uploading",
    )

    return parser.parse_args(argv)


def validate_directory(directory: str) -> Path:
    """Validate that the given directory exists and is readable.

    Args:
        directory: Path string to validate.

    Returns:
        Resolved Path object for the directory.

    Raises:
        SystemExit: If directory does not exist or is not readable.
    """
    path = Path(directory).resolve()

    if not path.exists():
        print(f"ERROR: Directory does not exist: {directory}", file=sys.stderr)
        sys.exit(1)

    if not path.is_dir():
        print(f"ERROR: Path is not a directory: {directory}", file=sys.stderr)
        sys.exit(1)

    if not os.access(path, os.R_OK):
        print(f"ERROR: Directory is not readable: {directory}", file=sys.stderr)
        sys.exit(1)

    return path


def walk_directory(root: Path) -> list[Path]:
    """Recursively walk a directory tree and return all regular files.

    Args:
        root: Root directory to walk.

    Returns:
        Sorted list of Path objects for all regular files found.
    """
    files = [p for p in root.rglob("*") if p.is_file()]
    return sorted(files)


def derive_metadata(file_path: Path, root: Path) -> FileMetadata:
    """Derive upload metadata from a file's path relative to the root directory.

    Args:
        file_path: Absolute path to the file.
        root: Root directory used as the base for relative path computation.

    Returns:
        FileMetadata with title (filename stem) and folder_path (relative parent).
    """
    relative = file_path.relative_to(root)
    title = file_path.stem
    folder_path = str(relative.parent) if str(relative.parent) != "." else ""

    return FileMetadata(path=file_path, title=title, folder_path=folder_path)


def upload_file(
    client: httpx.Client,
    file_meta: FileMetadata,
    api_url: str,
    document_type: str,
    tags: str,
    user_id: str,
) -> bool:
    """Upload a single file to the document API.

    Args:
        client: Configured httpx client with auth headers.
        file_meta: Metadata for the file to upload.
        api_url: Base API URL.
        document_type: Document type to assign.
        tags: Comma-separated tags string.
        user_id: User ID for upload attribution.

    Returns:
        True if upload succeeded, False otherwise.
    """
    url = f"{api_url.rstrip('/')}/api/v1/documents"

    try:
        with open(file_meta.path, "rb") as f:
            files = {"file": (file_meta.path.name, f)}
            data = {
                "title": file_meta.title,
                "folder_path": file_meta.folder_path,
                "document_type": document_type,
                "tags": tags,
                "user_id": user_id,
            }
            response = client.post(url, files=files, data=data)

        if response.status_code >= 400:
            detail = response.text
            print(
                f"  ERROR [{file_meta.path}]: {response.status_code} - {detail}",
                file=sys.stderr,
            )
            return False

        return True

    except httpx.HTTPError as e:
        print(f"  ERROR [{file_meta.path}]: {e}", file=sys.stderr)
        return False


def print_summary(summary: UploadSummary) -> None:
    """Print the final upload summary.

    Args:
        summary: UploadSummary with totals.
    """
    print("\n--- Upload Summary ---")
    print(f"Total files:        {summary.total}")
    print(f"Successful uploads: {summary.successful}")
    print(f"Failed uploads:     {summary.failed}")


def resolve_token(token_arg: str | None) -> str:
    """Resolve the authentication token from argument or environment variable.

    Args:
        token_arg: Token passed via --token argument, or None.

    Returns:
        The resolved token string.

    Raises:
        SystemExit: If no token is available from either source.
    """
    token = token_arg or os.environ.get("ALCOABASE_TOKEN", "")
    if not token:
        print(
            "ERROR: No authentication token provided. "
            "Use --token or set ALCOABASE_TOKEN environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def main(argv: list[str] | None = None) -> None:
    """Main entry point for the bulk upload CLI tool.

    Args:
        argv: Argument list to parse. Defaults to sys.argv[1:].
    """
    args = parse_args(argv)

    # Validate directory
    root = validate_directory(args.directory)

    # Resolve token
    token = resolve_token(args.token)

    # Walk directory
    files = walk_directory(root)

    if not files:
        print("No files found in directory.")
        return

    # Derive metadata for all files
    file_metas = [derive_metadata(f, root) for f in files]

    summary = UploadSummary(total=len(file_metas))

    # Dry-run mode
    if args.dry_run:
        print(f"Dry run: {summary.total} files would be uploaded:\n")
        for meta in file_metas:
            print(f"  {meta.path} -> title='{meta.title}', folder_path='{meta.folder_path}'")
        print_summary(summary)
        return

    # Upload loop
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": args.company_id,
    }

    with httpx.Client(headers=headers, timeout=60.0) as client:
        for i, meta in enumerate(file_metas, start=1):
            print(f"Uploading file {i} of {summary.total}: {meta.path.name}")
            success = upload_file(
                client=client,
                file_meta=meta,
                api_url=args.api_url,
                document_type=args.document_type,
                tags=args.tags,
                user_id=args.user_id,
            )
            if success:
                summary.successful += 1
            else:
                summary.failed += 1

    print_summary(summary)


if __name__ == "__main__":
    main()
