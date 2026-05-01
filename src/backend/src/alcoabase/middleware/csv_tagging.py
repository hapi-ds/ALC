"""CSV validation record tagging middleware.

This middleware identifies requests from the CSV Test User and sets a flag
on the request state so that downstream services mark created records with
``is_csv_validation_record = True``.

This ensures that validation test data is clearly separated from production
GxP data and can be excluded from standard user searches.

References:
    - Computer System Validation (CSV) methodology
    - GAMP 5 guidelines for computerized system validation
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

# The dedicated CSV Test User identifier used by the validation runner.
# This user is hidden from standard user lists and its requests are auto-tagged.
CSV_TEST_USER_ID = "csv_validation_runner"
CSV_TEST_USER_HEADER = "X-CSV-Test-User"


class CSVTaggingMiddleware(BaseHTTPMiddleware):
    """Tag requests from the CSV validation runner.

    When the CSV Test User is authenticated, this middleware sets
    ``request.state.is_csv_validation_request = True`` so that downstream
    services mark created records with ``is_csv_validation_record = True``.

    Detection is performed by checking:
    1. The ``X-CSV-Test-User`` header (set by the CSV runner container)
    2. The JWT token subject claim matching the CSV test user ID

    Args:
        app: The ASGI application to wrap.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Process the request, tagging CSV validation requests.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The HTTP response.
        """
        # Default: not a CSV validation request
        request.state.is_csv_validation_request = False

        # Check for CSV Test User via dedicated header
        csv_header = request.headers.get(CSV_TEST_USER_HEADER, "")
        if csv_header == CSV_TEST_USER_ID:
            request.state.is_csv_validation_request = True
        else:
            # Check JWT token subject for CSV test user identity
            user_id = getattr(request.state, "user_id", None)
            if user_id == CSV_TEST_USER_ID:
                request.state.is_csv_validation_request = True

        response = await call_next(request)
        return response
