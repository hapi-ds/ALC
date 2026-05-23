"""Async HTTP client for vLLM OpenAI-compatible API.

Handles connection pooling, retries with exponential backoff,
per-operation timeouts, and structured error reporting for all
communication with the vLLM inference server.

Endpoints used:
    - POST /v1/chat/completions — chat/generation and OCR (multimodal)
    - POST /v1/embeddings — embedding generation
    - GET /v1/models — list loaded models
    - GET /health — server readiness probe

References:
    - vLLM OpenAI-compatible API: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
    - httpx async client: https://www.python-httpx.org/async/
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Error Hierarchy
# ─────────────────────────────────────────────────────────────────────────────


class InferenceError(Exception):
    """Base exception for inference failures.

    Attributes:
        status_code: HTTP status code from the vLLM response, or None.
        endpoint: The endpoint URL that was called.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        endpoint: str = "",
    ) -> None:
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(message)


class InferenceTimeoutError(InferenceError):
    """Raised when vLLM does not respond within the configured timeout."""

    pass


class InferenceConnectionError(InferenceError):
    """Raised when vLLM server is unreachable."""

    pass


# ─────────────────────────────────────────────────────────────────────────────
# Inference Client
# ─────────────────────────────────────────────────────────────────────────────

# Retry configuration
_MAX_RETRIES = 2  # 2 additional attempts (3 total)
_BACKOFF_DELAYS = [1.0, 2.0]  # seconds: 1s after first failure, 2s after second

# HTTP status codes eligible for retry
_RETRYABLE_STATUS_CODES = {503}


class InferenceClient:
    """Async HTTP client for vLLM OpenAI-compatible API.

    Handles connection pooling, retries with exponential backoff,
    per-operation timeouts, and structured error reporting.

    Args:
        base_url: Base URL for the main vLLM instance (chat/OCR).
        embedding_base_url: Base URL for the dedicated embedding vLLM instance.
            If None, uses base_url for embeddings as well.
        max_connections: Maximum number of concurrent connections in the pool.
        connect_timeout: Timeout in seconds for establishing a connection.
    """

    def __init__(
        self,
        base_url: str,
        embedding_base_url: str | None = None,
        max_connections: int = 10,
        connect_timeout: float = 10.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._embedding_base_url = (
            embedding_base_url.rstrip("/") if embedding_base_url else self._base_url
        )
        self._connect_timeout = connect_timeout

        # Create a shared httpx.AsyncClient with connection pooling
        self._client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_connections=max_connections,
                max_keepalive_connections=max_connections,
            ),
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=60.0,  # default read timeout; overridden per-operation
                write=30.0,
                pool=10.0,
            ),
        )

    async def chat_completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> str:
        """Send chat completion request and return assistant message content.

        Args:
            model: The model identifier to use for generation.
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (lower = more deterministic).
            max_tokens: Maximum tokens to generate in the response.
            timeout: Read timeout in seconds (default 60s, use 90s for OCR).

        Returns:
            The assistant's response text from choices[0].message.content.

        Raises:
            InferenceError: If the request fails after all retries.
            InferenceTimeoutError: If the request exceeds the read timeout.
            InferenceConnectionError: If the server is unreachable.
        """
        endpoint = f"{self._base_url}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        # Calculate input size for logging
        input_size = sum(
            len(str(m.get("content", ""))) for m in messages
        )
        logger.debug(
            "POST %s | model=%s | input_size=%d chars",
            endpoint,
            model,
            input_size,
        )

        response = await self._request_with_retry(
            method="POST",
            url=endpoint,
            json=payload,
            read_timeout=timeout,
        )

        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def create_embeddings(
        self,
        model: str,
        inputs: list[str],
    ) -> list[list[float]]:
        """Send embedding request and return list of embedding vectors.

        Args:
            model: The embedding model identifier.
            inputs: List of text strings to embed.

        Returns:
            List of embedding vectors in the same order as inputs.

        Raises:
            InferenceError: If the request fails after all retries.
            InferenceTimeoutError: If the request exceeds the 30s read timeout.
            InferenceConnectionError: If the server is unreachable.
        """
        endpoint = f"{self._embedding_base_url}/v1/embeddings"
        payload = {
            "model": model,
            "input": inputs,
        }

        input_size = sum(len(s) for s in inputs)
        logger.debug(
            "POST %s | model=%s | input_size=%d chars | batch_size=%d",
            endpoint,
            model,
            input_size,
            len(inputs),
        )

        response = await self._request_with_retry(
            method="POST",
            url=endpoint,
            json=payload,
            read_timeout=30.0,
        )

        data = response.json()
        # Sort by index to ensure order matches input
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    async def health_check(self, base_url: str | None = None) -> bool:
        """Check if vLLM server is healthy.

        Sends GET /health and returns True if HTTP 200 is received.

        Args:
            base_url: Override base URL to check. If None, uses the main base_url.

        Returns:
            True if the server is healthy, False otherwise.
        """
        url = (base_url.rstrip("/") if base_url else self._base_url) + "/health"
        logger.debug("GET %s", url)

        try:
            response = await self._client.get(
                url,
                timeout=httpx.Timeout(
                    connect=self._connect_timeout,
                    read=5.0,
                    write=5.0,
                    pool=5.0,
                ),
            )
            return response.status_code == 200
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
            return False
        except httpx.HTTPError:
            return False

    async def list_models(self, base_url: str | None = None) -> list[str]:
        """List currently loaded models on the vLLM server.

        Sends GET /v1/models and returns model IDs.

        Args:
            base_url: Override base URL to query. If None, uses the main base_url.

        Returns:
            List of model ID strings currently loaded.

        Raises:
            InferenceError: If the request fails.
            InferenceConnectionError: If the server is unreachable.
        """
        url = (base_url.rstrip("/") if base_url else self._base_url) + "/v1/models"
        logger.debug("GET %s", url)

        try:
            response = await self._client.get(
                url,
                timeout=httpx.Timeout(
                    connect=self._connect_timeout,
                    read=5.0,
                    write=5.0,
                    pool=5.0,
                ),
            )
            if response.status_code != 200:
                body = response.text[:500]
                logger.error(
                    "GET %s failed | status=%d | body=%s",
                    url,
                    response.status_code,
                    body,
                )
                raise InferenceError(
                    f"Failed to list models: HTTP {response.status_code} - {body}",
                    status_code=response.status_code,
                    endpoint=url,
                )
            data = response.json()
            return [m["id"] for m in data.get("data", [])]
        except httpx.ConnectError as e:
            raise InferenceConnectionError(
                f"Cannot connect to vLLM at {url}: {e}",
                endpoint=url,
            ) from e
        except httpx.ConnectTimeout as e:
            raise InferenceConnectionError(
                f"Cannot connect to vLLM at {url}: connection timeout",
                endpoint=url,
            ) from e

    async def close(self) -> None:
        """Close the httpx client and release all connections."""
        await self._client.aclose()
        logger.debug("InferenceClient closed, connections released")

    # ─────────────────────────────────────────────────────────────────────
    # Internal: Request with retry logic
    # ─────────────────────────────────────────────────────────────────────

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        read_timeout: float = 60.0,
    ) -> httpx.Response:
        """Execute an HTTP request with retry logic for transient failures.

        Retries up to 2 additional attempts (3 total) for HTTP 503 and
        connection errors. Uses exponential backoff: 1s then 2s.
        Does NOT retry 4xx errors.

        Args:
            method: HTTP method (GET, POST, etc.).
            url: Full URL to request.
            json: JSON payload for the request body.
            read_timeout: Read timeout in seconds for this specific request.

        Returns:
            The successful httpx.Response.

        Raises:
            InferenceError: If the request fails after all retries with an HTTP error.
            InferenceTimeoutError: If the request times out after all retries.
            InferenceConnectionError: If the server is unreachable after all retries.
        """
        timeout = httpx.Timeout(
            connect=self._connect_timeout,
            read=read_timeout,
            write=30.0,
            pool=10.0,
        )

        last_exception: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    timeout=timeout,
                )

                # Success
                if response.status_code < 400:
                    return response

                # 4xx — client error, do NOT retry
                if 400 <= response.status_code < 500:
                    body = response.text[:500]
                    logger.error(
                        "%s %s failed | status=%d | body=%s",
                        method,
                        url,
                        response.status_code,
                        body,
                    )
                    raise InferenceError(
                        f"Request to {url} failed: HTTP {response.status_code} - {body}",
                        status_code=response.status_code,
                        endpoint=url,
                    )

                # 503 — retryable
                if response.status_code in _RETRYABLE_STATUS_CODES:
                    body = response.text[:500]
                    last_exception = InferenceError(
                        f"Request to {url} failed: HTTP {response.status_code} - {body}",
                        status_code=response.status_code,
                        endpoint=url,
                    )
                    if attempt < _MAX_RETRIES:
                        delay = _BACKOFF_DELAYS[attempt]
                        logger.warning(
                            "%s %s returned %d, retrying in %.1fs (attempt %d/%d)",
                            method,
                            url,
                            response.status_code,
                            delay,
                            attempt + 1,
                            _MAX_RETRIES + 1,
                        )
                        await asyncio.sleep(delay)
                        continue

                    # All retries exhausted
                    logger.error(
                        "%s %s failed after %d attempts | status=%d | body=%s",
                        method,
                        url,
                        _MAX_RETRIES + 1,
                        response.status_code,
                        body,
                    )
                    raise last_exception

                # Other 5xx — NOT retryable per spec (only 503 is retried)
                body = response.text[:500]
                logger.error(
                    "%s %s failed | status=%d | body=%s",
                    method,
                    url,
                    response.status_code,
                    body,
                )
                raise InferenceError(
                    f"Request to {url} failed: HTTP {response.status_code} - {body}",
                    status_code=response.status_code,
                    endpoint=url,
                )

            except httpx.ReadTimeout as e:
                # Read timeouts are NOT retried — they indicate the server
                # accepted the connection but is too slow to respond.
                logger.error(
                    "%s %s timed out (timeout=%.1fs)",
                    method,
                    url,
                    read_timeout,
                )
                raise InferenceTimeoutError(
                    f"Request to {url} timed out after {read_timeout}s",
                    endpoint=url,
                ) from e

            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                last_exception = InferenceConnectionError(
                    f"Cannot connect to vLLM at {url}: {e}",
                    endpoint=url,
                )
                if attempt < _MAX_RETRIES:
                    delay = _BACKOFF_DELAYS[attempt]
                    logger.warning(
                        "%s %s connection failed, retrying in %.1fs (attempt %d/%d)",
                        method,
                        url,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "%s %s connection failed after %d attempts: %s",
                    method,
                    url,
                    _MAX_RETRIES + 1,
                    str(e),
                )
                raise last_exception from e

        # Should not reach here, but just in case
        raise last_exception or InferenceError(  # pragma: no cover
            f"Request to {url} failed unexpectedly", endpoint=url
        )
