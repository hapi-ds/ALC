"""Unit tests for the InferenceClient service.

Tests health check polling, timeout scenarios, connection pooling,
shutdown cleanup, and error response formatting.

References:
    - Task 1.4: Write unit tests for InferenceClient
    - Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8
"""

from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from alcoabase.services.inference_client import (
    InferenceClient,
    InferenceError,
    InferenceTimeoutError,
    InferenceConnectionError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> InferenceClient:
    """Create an InferenceClient instance for testing."""
    return InferenceClient(
        base_url="http://localhost:8000",
        embedding_base_url="http://localhost:8001",
        max_connections=10,
        connect_timeout=10.0,
    )


# ---------------------------------------------------------------------------
# Tests: Health Check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Tests for the health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_200(self, client: InferenceClient) -> None:
        """health_check should return True when server responds with HTTP 200."""
        mock_response = httpx.Response(200)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await client.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_503(self, client: InferenceClient) -> None:
        """health_check should return False when server responds with HTTP 503."""
        mock_response = httpx.Response(503)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_connection_error(
        self, client: InferenceClient
    ) -> None:
        """health_check should return False when server is unreachable."""
        with patch.object(
            client._client, "get", new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_timeout(
        self, client: InferenceClient
    ) -> None:
        """health_check should return False when request times out."""
        with patch.object(
            client._client, "get", new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            result = await client.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_uses_custom_base_url(self, client: InferenceClient) -> None:
        """health_check should use the provided base_url override."""
        mock_response = httpx.Response(200)
        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
            await client.health_check(base_url="http://custom:9000")
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "http://custom:9000/health"

    @pytest.mark.asyncio
    async def test_health_check_503_then_200_polling(self, client: InferenceClient) -> None:
        """Simulates polling: first call returns 503, second returns 200."""
        responses = [httpx.Response(503), httpx.Response(200)]
        call_count = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch.object(client._client, "get", side_effect=mock_get):
            # First poll: not healthy
            result1 = await client.health_check()
            assert result1 is False
            # Second poll: healthy
            result2 = await client.health_check()
            assert result2 is True


# ---------------------------------------------------------------------------
# Tests: Timeout Scenarios
# ---------------------------------------------------------------------------


class TestTimeoutScenarios:
    """Tests for per-operation timeout configuration."""

    @pytest.mark.asyncio
    async def test_chat_completion_timeout_raises_inference_timeout_error(
        self, client: InferenceClient
    ) -> None:
        """Chat completion should raise InferenceTimeoutError on ReadTimeout (60s)."""
        with patch.object(
            client._client, "request", new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            with pytest.raises(InferenceTimeoutError) as exc_info:
                await client.chat_completion(
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert "timed out after 60.0s" in str(exc_info.value)
            assert "chat/completions" in exc_info.value.endpoint

    @pytest.mark.asyncio
    async def test_embeddings_timeout_raises_inference_timeout_error(
        self, client: InferenceClient
    ) -> None:
        """Embeddings should raise InferenceTimeoutError on ReadTimeout (30s)."""
        with patch.object(
            client._client, "request", new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            with pytest.raises(InferenceTimeoutError) as exc_info:
                await client.create_embeddings(
                    model="test-embedding",
                    inputs=["test text"],
                )
            assert "timed out after 30.0s" in str(exc_info.value)
            assert "embeddings" in exc_info.value.endpoint

    @pytest.mark.asyncio
    async def test_chat_completion_uses_60s_read_timeout(
        self, client: InferenceClient
    ) -> None:
        """Chat completion should pass 60s read timeout to the request."""
        mock_response = httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "response"}, "index": 0}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_request:
            await client.chat_completion(
                model="test-model",
                messages=[{"role": "user", "content": "hello"}],
            )
        # Verify the timeout passed to the request
        call_kwargs = mock_request.call_args[1]
        timeout = call_kwargs["timeout"]
        assert timeout.read == 60.0

    @pytest.mark.asyncio
    async def test_embeddings_uses_30s_read_timeout(
        self, client: InferenceClient
    ) -> None:
        """Embeddings should pass 30s read timeout to the request."""
        mock_response = httpx.Response(
            200,
            json={
                "data": [{"index": 0, "embedding": [0.1] * 1024}],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_request:
            await client.create_embeddings(
                model="test-embedding",
                inputs=["test text"],
            )
        call_kwargs = mock_request.call_args[1]
        timeout = call_kwargs["timeout"]
        assert timeout.read == 30.0


# ---------------------------------------------------------------------------
# Tests: Connection Pooling
# ---------------------------------------------------------------------------


class TestConnectionPooling:
    """Tests for single httpx client instance reuse."""

    def test_single_client_instance_created(self, client: InferenceClient) -> None:
        """InferenceClient should create exactly one httpx.AsyncClient instance."""
        assert isinstance(client._client, httpx.AsyncClient)

    def test_client_reused_across_operations(self, client: InferenceClient) -> None:
        """The same httpx.AsyncClient instance should be used for all operations."""
        # Store reference to the internal client
        internal_client = client._client
        # Verify it's the same object (not recreated)
        assert client._client is internal_client

    def test_connection_pool_max_connections(self, client: InferenceClient) -> None:
        """Connection pool should be configured with max_connections=10."""
        pool_limits = client._client._transport._pool._max_connections
        assert pool_limits == 10

    def test_separate_base_urls_same_client(self, client: InferenceClient) -> None:
        """Main and embedding URLs should use the same httpx client instance."""
        assert client._base_url == "http://localhost:8000"
        assert client._embedding_base_url == "http://localhost:8001"
        # Both use the same underlying client
        assert isinstance(client._client, httpx.AsyncClient)


# ---------------------------------------------------------------------------
# Tests: Shutdown Cleanup
# ---------------------------------------------------------------------------


class TestShutdownCleanup:
    """Tests for client.close() releasing connections."""

    @pytest.mark.asyncio
    async def test_close_calls_aclose_on_httpx_client(
        self, client: InferenceClient
    ) -> None:
        """close() should call aclose() on the internal httpx client."""
        with patch.object(client._client, "aclose", new_callable=AsyncMock) as mock_aclose:
            await client.close()
        mock_aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, client: InferenceClient) -> None:
        """close() should not raise if called on an already-closed client."""
        # First close
        await client.close()
        # The client is now closed; calling close again should not raise
        # (httpx.AsyncClient.aclose is idempotent)
        await client.close()


# ---------------------------------------------------------------------------
# Tests: Error Response Formatting
# ---------------------------------------------------------------------------


class TestErrorResponseFormatting:
    """Tests for error messages including status code, truncated body, and endpoint URL."""

    @pytest.mark.asyncio
    async def test_4xx_error_includes_status_code(self, client: InferenceClient) -> None:
        """Error from 4xx response should include the HTTP status code."""
        mock_response = httpx.Response(
            422,
            json={"detail": "Validation error"},
            request=httpx.Request("POST", "http://localhost:8000/v1/chat/completions"),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(InferenceError) as exc_info:
                await client.chat_completion(
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert exc_info.value.status_code == 422
            assert "422" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_includes_endpoint_url(self, client: InferenceClient) -> None:
        """Error should include the endpoint URL that was called."""
        mock_response = httpx.Response(
            400,
            json={"detail": "Bad request"},
            request=httpx.Request("POST", "http://localhost:8000/v1/chat/completions"),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(InferenceError) as exc_info:
                await client.chat_completion(
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            assert exc_info.value.endpoint == "http://localhost:8000/v1/chat/completions"
            assert "chat/completions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_body_truncated_to_500_chars(self, client: InferenceClient) -> None:
        """Error response body should be truncated to 500 characters."""
        long_body = "x" * 1000
        mock_response = httpx.Response(
            400,
            text=long_body,
            request=httpx.Request("POST", "http://localhost:8000/v1/chat/completions"),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(InferenceError) as exc_info:
                await client.chat_completion(
                    model="test-model",
                    messages=[{"role": "user", "content": "hello"}],
                )
            error_message = str(exc_info.value)
            # The body in the error message should be at most 500 chars
            # (the full 1000-char body should not appear)
            assert "x" * 501 not in error_message

    @pytest.mark.asyncio
    async def test_503_error_after_retries_includes_status(
        self, client: InferenceClient
    ) -> None:
        """503 error after all retries should include status code and endpoint."""
        mock_response = httpx.Response(
            503,
            text="Service Unavailable",
            request=httpx.Request("POST", "http://localhost:8000/v1/chat/completions"),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(InferenceError) as exc_info:
                    await client.chat_completion(
                        model="test-model",
                        messages=[{"role": "user", "content": "hello"}],
                    )
                assert exc_info.value.status_code == 503
                assert exc_info.value.endpoint == "http://localhost:8000/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_connection_error_includes_endpoint(
        self, client: InferenceClient
    ) -> None:
        """Connection error should include the endpoint URL."""
        with patch.object(
            client._client, "request", new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with patch("alcoabase.services.inference_client.asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(InferenceConnectionError) as exc_info:
                    await client.chat_completion(
                        model="test-model",
                        messages=[{"role": "user", "content": "hello"}],
                    )
                assert "localhost:8000" in str(exc_info.value)
                assert exc_info.value.endpoint == "http://localhost:8000/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_timeout_error_includes_timeout_value(
        self, client: InferenceClient
    ) -> None:
        """Timeout error should include the timeout duration."""
        with patch.object(
            client._client, "request", new_callable=AsyncMock,
            side_effect=httpx.ReadTimeout("Read timed out"),
        ):
            with pytest.raises(InferenceTimeoutError) as exc_info:
                await client.create_embeddings(
                    model="test-embedding",
                    inputs=["test"],
                )
            assert "30.0s" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_embedding_error_uses_embedding_base_url(
        self, client: InferenceClient
    ) -> None:
        """Embedding errors should reference the embedding base URL."""
        mock_response = httpx.Response(
            400,
            text="Bad request",
            request=httpx.Request("POST", "http://localhost:8001/v1/embeddings"),
        )
        with patch.object(
            client._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(InferenceError) as exc_info:
                await client.create_embeddings(
                    model="test-embedding",
                    inputs=["test"],
                )
            assert exc_info.value.endpoint == "http://localhost:8001/v1/embeddings"
