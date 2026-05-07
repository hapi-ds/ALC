# Document Upload Guide

This guide covers uploading documents to AlcoaBase via the web interface and the bulk upload CLI tool.

## Web Interface Upload

### Uploading a Single Document

1. Navigate to the **Documents** page (the default landing page after login).
2. Click the **Upload Document** button in the top-right corner.
3. In the upload dialog:
   - **File** — Click the dashed area or drag and drop a file onto it. The selected filename will appear.
   - **Title** — Enter a descriptive title (required, max 500 characters).
   - **Folder Path** — Enter the logical folder path, e.g. `/quality/sops` (required, max 1000 characters).
   - **Document Type** — Select from: SOP, Protocol, Report, General, Policy, Form.
   - **Tags** — Optionally enter comma-separated tags, e.g. `quality, review, batch-record`.
4. Click **Upload**. A spinner indicates progress.
5. On success the dialog closes and the document list refreshes with your new document.
6. On failure an error message appears inside the dialog.

### Uploading a New Version

1. Click on a document in the list to open its detail view.
2. Click the **New Version** button.
3. In the version dialog:
   - **File** — Select the updated file.
   - **Version Type** — Choose **Major** (e.g. 1.0 → 2.0) or **Minor** (e.g. 1.0 → 1.1).
   - **Change Reason** — Describe what changed (required).
4. Click **Upload Version**.
5. The version history updates with the new entry.

### Browsing and Filtering

- **Pagination** — Use Previous/Next buttons below the document list.
- **Filter by tag** — Type a tag name in the tag filter input.
- **Filter by folder path** — Type a path in the folder path input.
- **Clear filters** — Click the Clear button to reset.

---

## Bulk Upload CLI

The bulk upload tool recursively walks a directory and uploads every file as a document.

### Prerequisites

- Python 3.11+ with `uv` installed
- The backend running and accessible (e.g. `http://localhost:8080`)
- A valid authentication token (or set `ALCOABASE_TOKEN` environment variable)
- Your user ID and company ID (check the admin panel or database)

### Basic Usage

```bash
cd src/backend

uv run python scripts/bulk_upload.py \
  --directory /path/to/documents \
  --api-url http://localhost:8080 \
  --company-id 2 \
  --user-id 1 \
  --token YOUR_TOKEN
```

### All Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--directory` | Yes | — | Root directory to recursively walk |
| `--api-url` | Yes | — | Backend API base URL |
| `--company-id` | Yes | — | Company ID for multi-tenancy |
| `--user-id` | Yes | — | User ID for audit attribution |
| `--token` | No | `ALCOABASE_TOKEN` env var | Bearer token for authentication |
| `--document-type` | No | `General` | Document type for all uploads |
| `--tags` | No | (empty) | Comma-separated tags for all uploads |
| `--dry-run` | No | off | List files without uploading |

### Dry Run

Preview what would be uploaded without making any API calls:

```bash
uv run python scripts/bulk_upload.py \
  --directory ./my-docs \
  --api-url http://localhost:8080 \
  --company-id 2 \
  --user-id 1 \
  --token mytoken \
  --dry-run
```

Output:
```
Dry run: 5 files would be uploaded:

  /path/to/my-docs/report.pdf -> title='report', folder_path='/'
  /path/to/my-docs/sops/cleaning.docx -> title='cleaning', folder_path='sops'
  ...

--- Upload Summary ---
Total files:        5
Successful uploads: 0
Failed uploads:     0
```

### How Metadata is Derived

For each file found in the directory tree:

| Field | Derived From | Example |
|-------|-------------|---------|
| `title` | Filename without extension | `cleaning-procedure.pdf` → `cleaning-procedure` |
| `folder_path` | Relative directory from root | `sops/cleaning.pdf` → `sops`, root-level → `/` |
| `document_type` | `--document-type` argument | `General` (default) |
| `tags` | `--tags` argument | Applied to all files |

### Error Handling

- If a single file fails, the tool logs the error and continues with remaining files.
- The final summary shows total, successful, and failed counts.
- Exit code 1 if the directory doesn't exist or no token is provided.

### Example with Tags and Document Type

```bash
uv run python scripts/bulk_upload.py \
  --directory /shared/quality-docs \
  --api-url http://localhost:8080 \
  --company-id 2 \
  --user-id 1 \
  --token mytoken \
  --document-type SOP \
  --tags "quality,imported,2026"
```

### Using Environment Variable for Token

```bash
export ALCOABASE_TOKEN="your-bearer-token"

uv run python scripts/bulk_upload.py \
  --directory ./docs \
  --api-url http://localhost:8080 \
  --company-id 2 \
  --user-id 1
```
