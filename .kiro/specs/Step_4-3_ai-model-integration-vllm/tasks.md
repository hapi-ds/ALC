# Implementation Plan: AI Model Integration (vLLM)

## Overview

This plan implements real vLLM inference to replace all placeholder/mock AI responses. The architecture uses a hybrid approach: a dedicated always-on embedding vLLM instance and a shared main vLLM instance for chat/OCR (with container restart for model swaps). The InferenceClient provides async HTTP communication with retries and per-operation timeouts. Mock mode continues to work identically without any HTTP calls.

## Tasks

- [x] 1. Create InferenceClient and error types
  - [x] 1.1 Create `src/backend/src/alcoabase/services/inference_client.py` with InferenceClient class and error hierarchy
    - Define `InferenceError`, `InferenceTimeoutError`, `InferenceConnectionError` exception classes
    - Implement `InferenceClient.__init__` with `base_url`, `embedding_base_url`, `max_connections=10`, `connect_timeout=10.0`
    - Create a shared `httpx.AsyncClient` with connection pooling (max 10 connections)
    - Implement `chat_completion(model, messages, temperature=0.3, max_tokens=2048)` with 60s read timeout
    - Implement `create_embeddings(model, inputs)` with 30s read timeout
    - Implement `health_check(base_url=None)` with 5s timeout
    - Implement `list_models(base_url=None)` for checking loaded models
    - Implement `close()` to release httpx client connections
    - Implement retry logic: 2 retries with 1s/2s exponential backoff for HTTP 503 and connection errors only; no retry for 4xx
    - Log outgoing requests at DEBUG level (endpoint, model, input size) and errors at ERROR level (status, body truncated to 500 chars)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 1.2 Write property test for retry policy correctness
    - **Property 12: Retry policy correctness**
    - **Validates: Requirements 6.2, 6.3**

  - [x] 1.3 Write property test for chat response extraction
    - **Property 5: Chat response extraction**
    - **Validates: Requirements 2.4**

  - [x] 1.4 Write unit tests for InferenceClient
    - Test health check polling (mock `/health` returning 503 then 200)
    - Test timeout scenarios for each operation type (60s, 30s, 90s)
    - Test connection pooling (single httpx client instance reuse)
    - Test shutdown cleanup (client.close() called)
    - Test error response formatting (status code, truncated body, endpoint URL)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 2. Update ModelManager for real vLLM routing
  - [x] 2.1 Add `vllm_embedding_url` setting to `src/backend/src/alcoabase/config.py`
    - Add `vllm_embedding_url: str` field with default `http://localhost:8001` and alias `VLLM_EMBEDDING_URL`
    - _Requirements: 3.1, 5.6_

  - [x] 2.2 Update `src/backend/src/alcoabase/services/model_manager.py` with real vLLM API calls
    - Accept optional `InferenceClient` in constructor
    - Update `ModelStatus` dataclass to include `vllm_reachable: bool | None = None`
    - For EMBEDDING role in gpu/cpu mode: return `vllm_embedding_url` immediately (always-on instance)
    - For CHAT/OCR role in gpu/cpu mode: check loaded model via `list_models()`, restart container via subprocess if wrong model
    - Implement health check polling in `_load_model`: poll `/health` every 2s with timeout (120s gpu, 300s cpu)
    - Implement `_unload_model` for gpu/cpu mode: restart container, poll until idle, 60s timeout
    - Update `get_status` to include `vllm_reachable` field (health check with 5s timeout in gpu/cpu, None in mock)
    - Add `shutdown()` method to close InferenceClient
    - Raise `ModelManagerError` with descriptive messages on failures (unreachable, timeout, unload failure)
    - Ensure mock mode behavior is unchanged (no HTTP calls, immediate state update)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 5.1, 5.5, 5.6, 5.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 2.3 Write property test for role-to-endpoint routing correctness
    - **Property 1: Role-to-endpoint routing correctness**
    - **Validates: Requirements 1.1**

  - [x] 2.4 Write property test for same-role idempotency
    - **Property 3: Same-role idempotency**
    - **Validates: Requirements 1.7, 10.2**

  - [x] 2.5 Write property test for model swap serialization
    - **Property 2: Model swap serialization**
    - **Validates: Requirements 1.6, 10.1, 10.2**

  - [x] 2.6 Write property test for mock mode isolation
    - **Property 11: Mock mode isolation**
    - **Validates: Requirements 2.7, 3.7, 4.8, 5.1, 5.2**

  - [x] 2.7 Write unit tests for ModelManager gpu/cpu mode in `src/backend/tests/test_model_manager.py`
    - Test health check polling with mocked responses
    - Test timeout raises ModelManagerError with descriptive message
    - Test unload failure prevents new load attempt
    - Test vllm_reachable field in get_status (true/false/None)
    - Test EMBEDDING role returns embedding URL without swap
    - Test container restart subprocess call for CHAT↔OCR swap
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 9.1, 9.2, 9.3, 9.4_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Update RAG Pipeline for real chat completion
  - [x] 4.1 Update `src/backend/src/alcoabase/services/rag_pipeline.py` with real inference
    - Accept `ModelManager` and `InferenceClient` as constructor dependencies
    - Make `_generate_response` async and call `ensure_model(CHAT)` then `inference_client.chat_completion()`
    - Implement `_build_system_prompt()` with grounding instructions (answer only from context, cite [Source N], state when insufficient info, never fabricate)
    - Build messages array: system prompt → history (last 6 messages as user/assistant) → context → current question
    - Set request params: model=configured chat model name, temperature=0.3, max_tokens=2048, stream=false
    - Extract response from `choices[0].message.content`
    - Implement `_truncate_context(search_results, max_tokens=8192)` — remove lowest-relevance chunks until within limit, always keep highest-relevance chunk
    - Update `_build_context` to format as `[Source N: {title} v{version}]` followed by chunk text
    - Handle errors: log HTTP status + body (truncated 500 chars), raise on failure, propagate ModelManagerError
    - Raise timeout error if vLLM doesn't respond within 60s
    - In mock mode: use existing placeholder logic, set grounded=true when context available
    - Make `query` method properly async (await _generate_response)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 5.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 4.2 Write property test for chat completion message structure
    - **Property 4: Chat completion message structure**
    - **Validates: Requirements 2.2**

  - [x] 4.3 Write property test for context truncation by relevance
    - **Property 13: Context truncation by relevance**
    - **Validates: Requirements 7.5, 7.6**

  - [x] 4.4 Write property test for source citation formatting
    - **Property 14: Source citation formatting**
    - **Validates: Requirements 7.4**

  - [x] 4.5 Write property test for grounding flag correctness
    - **Property 15: Grounding flag correctness**
    - **Validates: Requirements 7.2, 7.3**

  - [x] 4.6 Write unit tests for RAG pipeline inference in `src/backend/tests/test_rag_pipeline_inference.py`
    - Test system prompt contains all grounding rules
    - Test message array structure (system, history, context, question)
    - Test history limited to last 6 messages
    - Test NO_CONTENT_MESSAGE returned with grounded=false when no results
    - Test error propagation from ModelManagerError
    - Test timeout handling (60s exceeded)
    - Test mock mode returns placeholder without HTTP calls
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 7.1, 7.2, 7.3_

- [x] 5. Update Knowledge Service for real embeddings
  - [x] 5.1 Update `src/backend/src/alcoabase/services/knowledge_service.py` embedding generation
    - Accept `ModelManager` and `InferenceClient` as constructor dependencies
    - Make `generate_embeddings` async
    - In gpu/cpu mode: call `ensure_model(EMBEDDING)` then batch chunks (max 32 per request) to `inference_client.create_embeddings()`
    - Process batches sequentially, concatenate results in input order
    - Validate each returned vector has exactly `model_embedding_dimension` dimensions; raise ValueError on mismatch
    - Return empty list for empty input without calling ensure_model or making HTTP requests
    - Include `model` parameter set to configured embedding model name
    - Handle HTTP errors: log status + body, raise exception for failed batch
    - Handle timeout: raise after 30s
    - In mock mode: use existing random vector generation (unchanged)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 5.2, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.2 Write property test for embedding batch size constraint
    - **Property 6: Embedding batch size constraint**
    - **Validates: Requirements 3.2**

  - [x] 5.3 Write property test for embedding order preservation
    - **Property 7: Embedding order preservation**
    - **Validates: Requirements 3.3**

  - [x] 5.4 Write property test for embedding dimension validation
    - **Property 8: Embedding dimension validation**
    - **Validates: Requirements 3.4**

  - [x] 5.5 Write unit tests for embedding generation in `src/backend/tests/test_knowledge_service_embeddings.py`
    - Test batching with various chunk counts (1, 32, 33, 64, 100)
    - Test empty input returns empty list without HTTP calls
    - Test dimension mismatch raises ValueError
    - Test mock mode returns random vectors of correct dimension
    - Test HTTP error handling and logging
    - Test timeout raises after 30s
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement OCR text extraction via vision model
  - [x] 7.1 Update `src/backend/src/alcoabase/services/knowledge_service.py` OCR extraction
    - Make `_ocr_extract_text` async
    - In gpu/cpu mode: convert each PDF page to PNG at 300 DPI using PyMuPDF (fitz)
    - Call `ensure_model(OCR)` on ModelManager
    - Send each page image to `inference_client.chat_completion()` with multimodal message (base64-encoded image + system prompt for text extraction)
    - Set params: model=configured OCR model name, max_tokens=4096, temperature=0.1
    - Process pages sequentially (one at a time), max 500 pages per document
    - Concatenate successful page texts with newline separators
    - On per-page error: log warning with page number and status, skip page, continue
    - On per-page timeout (90s): log warning, skip page, continue
    - If all pages fail: return empty string, log error
    - If PDF has zero pages: return empty string, log warning
    - In mock mode: return existing placeholder text unchanged
    - Update `extract_text_with_ocr_fallback` to be async and await `_ocr_extract_text`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 5.4_

  - [x] 7.2 Write property test for OCR page text concatenation
    - **Property 9: OCR page text concatenation**
    - **Validates: Requirements 4.3**

  - [x] 7.3 Write property test for OCR resilience — failed pages skipped
    - **Property 10: OCR resilience — failed pages skipped**
    - **Validates: Requirements 4.4**

  - [x] 7.4 Write unit tests for OCR extraction in `src/backend/tests/test_knowledge_service_ocr.py`
    - Test multimodal message format (base64 image encoding, system prompt)
    - Test sequential page processing
    - Test page failure skipping with warning log
    - Test all-pages-fail returns empty string
    - Test zero-page PDF returns empty string
    - Test 500-page limit
    - Test 90s per-page timeout handling
    - Test mock mode returns placeholder text
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

- [x] 8. Wire components together and add test dependency
  - [x] 8.1 Add `respx` dev dependency and wire service constructors
    - Run `uv add --dev respx` from `src/backend/`
    - Ensure `ModelManager`, `KnowledgeService`, and `RAGPipeline` constructors properly instantiate and share `InferenceClient`
    - Verify `InferenceClient` is created once and passed to all services that need it
    - Ensure `shutdown()` on ModelManager closes the shared InferenceClient
    - Verify all async methods are properly awaited throughout the call chain
    - _Requirements: 2.9, 6.6, 6.7_

  - [x] 8.2 Write integration tests verifying end-to-end flow with mocked HTTP
    - Test full RAG query flow: query → ensure_model → chat_completion → response
    - Test full embedding flow: chunks → ensure_model → create_embeddings → vectors
    - Test full OCR flow: PDF bytes → ensure_model → multimodal chat → text
    - Test mock mode end-to-end (no HTTP calls made)
    - _Requirements: 2.1, 3.1, 4.1, 5.1, 5.2, 5.3, 5.4_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All HTTP mocking uses `respx` library for httpx async client
- Property tests use `@given(...)` with `@settings(max_examples=100)`
- Run tests with `uv run pytest --tb=short -q` from `src/backend/`

