# Requirements Document

## Introduction

This feature replaces all mock/placeholder AI responses in the backend service layer with real LLM inference calls to the vLLM server. The implementation covers three core capabilities: (1) chat/completion generation via the vLLM OpenAI-compatible API for the RAG pipeline, (2) real embedding generation for document indexing and semantic search, and (3) OCR text extraction from scanned PDFs using a vision model. The ModelManager orchestrates model loading/unloading on the vLLM server (since only one large model fits in GPU memory at a time), while maintaining full backward compatibility with mock mode for development and testing. All inference calls use httpx as the async HTTP client against the vLLM OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/embeddings`). The system operates in an air-gapped network with pre-downloaded model weights.

## Glossary

- **Model_Manager**: The async service (`model_manager.py`) that manages GPU model loading/unloading on the vLLM server, ensuring only one large model occupies GPU memory at a time via an async lock.
- **vLLM_Server**: The vLLM inference server exposing an OpenAI-compatible REST API at `VLLM_BASE_URL` (default `http://localhost:8000`), supporting `/v1/chat/completions`, `/v1/embeddings`, `/v1/models`, and `/health` endpoints.
- **Knowledge_Service**: The backend service (`knowledge_service.py`) responsible for document text extraction, chunking, embedding generation, indexing, and hybrid search.
- **RAG_Pipeline**: The retrieval-augmented generation service (`rag_pipeline.py`) that retrieves relevant document chunks and generates grounded responses with source citations.
- **Embedding_Model**: The multilingual embedding model (Qwen3-Embedding-0.6B or Qwen3-Embedding-8B) that produces 1024-dimensional vector representations of text chunks.
- **Chat_Model**: The chat/generation LLM (Qwen3.6-35B-A3B or Llama-3.3-70B-Instruct) used for RAG response generation via the `/v1/chat/completions` endpoint.
- **OCR_Model**: The vision-language model (google/gemma-4-E4B-it or Qwen2.5-VL-72B-Instruct) used to extract text from scanned PDF page images.
- **Model_Role**: An enum (CHAT, EMBEDDING, OCR) identifying which model should be loaded for a given inference task.
- **Mode_Switch**: The `MODEL_MANAGER_MODE` configuration setting (`gpu`, `cpu`, or `mock`) that determines whether real inference, CPU inference, or mock responses are used.
- **Health_Check**: A readiness probe against the vLLM `/health` endpoint used to confirm a model is loaded and ready for inference.
- **Inference_Client**: An async httpx client used to make HTTP requests to the vLLM OpenAI-compatible API endpoints.

## Requirements

### Requirement 1: vLLM Model Loading via API

**User Story:** As a system operator, I want the Model_Manager to load and unload models on the vLLM server dynamically, so that GPU memory is managed efficiently with only one large model active at a time.

#### Acceptance Criteria

1. WHEN `ensure_model` is called with a Model_Role in gpu or cpu mode, THE Model_Manager SHALL send an HTTP request to the vLLM_Server to load the model identified by the configured model path for that role.
2. WHEN a model load request is sent to the vLLM_Server, THE Model_Manager SHALL poll the `/health` endpoint at intervals of no more than 2 seconds until the server returns an HTTP 200 response, with a configurable timeout (default 120 seconds for gpu mode, 300 seconds for cpu mode).
3. IF the vLLM_Server `/health` endpoint does not return HTTP 200 within the configured timeout, THEN THE Model_Manager SHALL raise a ModelManagerError with a descriptive message including the model name, role, and elapsed time.
4. WHEN `_unload_model` is called in gpu or cpu mode, THE Model_Manager SHALL send an HTTP request to the vLLM_Server to unload the current model and SHALL poll the `/health` endpoint at intervals of no more than 2 seconds until the server reports no model loaded or idle status, with a timeout of 60 seconds.
5. IF the vLLM_Server does not confirm model unload within the 60-second unload timeout, THEN THE Model_Manager SHALL raise a ModelManagerError with a message including the model name that failed to unload and the elapsed time.
6. WHILE a model is being loaded or unloaded, THE Model_Manager SHALL hold the async lock to prevent concurrent model swap operations from interfering.
7. WHEN `ensure_model` is called with the same Model_Role that is already loaded and ready, THE Model_Manager SHALL return immediately without sending any requests to the vLLM_Server.
8. IF the vLLM_Server is unreachable (connection refused or timeout on initial request), THEN THE Model_Manager SHALL raise a ModelManagerError with a message indicating the server is unavailable at the configured VLLM_BASE_URL.
9. IF `_unload_model` fails during a model swap (unload preceding a new load), THEN THE Model_Manager SHALL set its internal state to not-ready, SHALL NOT attempt to load the new model, and SHALL propagate the ModelManagerError to the caller.

### Requirement 2: Chat Completion Inference

**User Story:** As a user querying the knowledge base, I want the RAG pipeline to generate real LLM responses grounded in retrieved document context, so that I receive accurate and helpful answers instead of placeholder text.

#### Acceptance Criteria

1. WHEN `_generate_response` is called in the RAG_Pipeline with a question, context, and history, THE RAG_Pipeline SHALL asynchronously call `ensure_model(CHAT)` on the Model_Manager and then send a POST request to `{vllm_base_url}/v1/chat/completions` with a structured messages array using the Inference_Client.
2. THE RAG_Pipeline SHALL construct the chat messages array with: a system message instructing the model to answer based only on the provided context and cite sources, the conversation history limited to the last 6 messages formatted as alternating user/assistant messages, the retrieved context chunks as a user message, and the current question as the final user message.
3. THE RAG_Pipeline SHALL include the following parameters in the chat completion request: `model` set to the configured chat model name, `temperature` set to 0.3 (for factual grounding), `max_tokens` set to 2048, and `stream` set to false.
4. WHEN the vLLM_Server returns an HTTP 200 response for a chat completion request, THE RAG_Pipeline SHALL extract the assistant message content from `choices[0].message.content` in the response and return it as the generated answer.
5. IF the vLLM_Server returns an HTTP error status (4xx or 5xx) for a chat completion request, THEN THE RAG_Pipeline SHALL log the HTTP status code and response body (truncated to 500 characters) and raise an exception with a message indicating that response generation failed.
6. IF the vLLM_Server does not respond within 60 seconds for a chat completion request, THEN THE RAG_Pipeline SHALL raise a timeout error with a message indicating the 60-second timeout was exceeded.
7. WHILE the Model_Manager mode is set to "mock", THE RAG_Pipeline SHALL use the existing placeholder `_generate_response` logic without making any HTTP requests to the vLLM_Server.
8. IF `ensure_model(CHAT)` raises a ModelManagerError before the chat completion request is sent, THEN THE RAG_Pipeline SHALL propagate the error to the caller without sending any request to the vLLM_Server.
9. THE RAG_Pipeline SHALL accept a Model_Manager instance and an Inference_Client instance as constructor dependencies to support both real inference and mock mode.

### Requirement 3: Embedding Generation

**User Story:** As a system indexing documents, I want real vector embeddings generated from document text chunks, so that semantic search produces meaningful results based on actual content similarity.

#### Acceptance Criteria

1. WHEN `generate_embeddings` is called on the Knowledge_Service with a non-empty list of text chunks in gpu or cpu mode, THE Knowledge_Service SHALL call `ensure_model(EMBEDDING)` on the Model_Manager and then send a POST request to `{vllm_base_url}/v1/embeddings` with the chunks as input.
2. THE Knowledge_Service SHALL send embedding requests in batches of no more than 32 chunks per request to avoid exceeding the vLLM_Server token limits, processing all batches sequentially and concatenating results in input order.
3. WHEN the vLLM_Server returns a successful embedding response, THE Knowledge_Service SHALL extract the embedding vectors from the response data array and return them as a list of float lists in the same order as the input chunks.
4. THE Knowledge_Service SHALL validate that each returned embedding vector has exactly `model_embedding_dimension` dimensions (1024 by default) and SHALL raise a ValueError if the dimension does not match.
5. IF the vLLM_Server returns an HTTP error status (4xx or 5xx) for an embedding request, THEN THE Knowledge_Service SHALL log the error including the HTTP status code and response body, and raise an exception with a message indicating embedding generation failed for the affected batch.
6. IF the vLLM_Server does not respond within 30 seconds for an embedding request, THEN THE Knowledge_Service SHALL raise a timeout error.
7. WHILE the Model_Manager mode is set to "mock", THE Knowledge_Service SHALL use the existing random vector generation logic without making any HTTP requests to the vLLM_Server.
8. THE Knowledge_Service SHALL include the `model` parameter set to the configured embedding model name in each embedding request.
9. WHEN `generate_embeddings` is called with an empty list of text chunks, THE Knowledge_Service SHALL return an empty list without calling `ensure_model` or making any HTTP requests to the vLLM_Server.

### Requirement 4: OCR Text Extraction via Vision Model

**User Story:** As a user uploading scanned PDFs, I want the system to extract text from page images using a vision model, so that scanned documents become searchable and queryable in the knowledge base.

#### Acceptance Criteria

1. WHEN `_ocr_extract_text` is called with PDF file bytes in gpu or cpu mode, THE Knowledge_Service SHALL convert each PDF page to a PNG image at 300 DPI resolution using PyMuPDF (fitz), call `ensure_model(OCR)` on the Model_Manager, and send each page image to the vLLM_Server for text extraction, processing a maximum of 500 pages per document.
2. THE Knowledge_Service SHALL send each page image to `{vllm_base_url}/v1/chat/completions` with a multimodal message containing the base64-encoded image and a system prompt instructing the model to extract all visible text from the image, and SHALL include the `model` parameter set to the configured OCR model name, `max_tokens` set to 4096, and `temperature` set to 0.1.
3. WHEN the vLLM_Server returns a successful response for a page OCR request, THE Knowledge_Service SHALL extract the text content from the assistant message and concatenate all page texts with newline separators to produce the final extracted text.
4. IF the vLLM_Server returns an error for a specific page OCR request, THEN THE Knowledge_Service SHALL log a warning including the page number and HTTP status code, skip the failed page, and continue processing remaining pages.
5. IF all pages fail OCR extraction, THEN THE Knowledge_Service SHALL return an empty string and log an error indicating complete OCR failure for the document.
6. THE Knowledge_Service SHALL process PDF pages sequentially (one at a time) to avoid overwhelming the vLLM_Server with concurrent vision inference requests.
7. IF the vLLM_Server does not respond within 90 seconds for a single page OCR request, THEN THE Knowledge_Service SHALL log a timeout warning for that page, skip it, and continue with the next page.
8. WHILE the Model_Manager mode is set to "mock", THE Knowledge_Service SHALL return the existing placeholder text "[OCR_PENDING: Scanned PDF text extraction requires Model_Manager]" without making any HTTP requests.
9. IF the PDF contains zero pages, THEN THE Knowledge_Service SHALL return an empty string and log a warning indicating the document has no pages to process.

### Requirement 5: Mode Switch Backward Compatibility

**User Story:** As a developer, I want the mock mode to continue working identically to the current behavior, so that development and testing can proceed without GPU hardware or a running vLLM server.

#### Acceptance Criteria

1. WHILE the Model_Manager mode is "mock", THE Model_Manager SHALL simulate model loading by updating internal state (current_role, model_name, is_ready set to true, gpu_memory_used_gb set to 0.0) without making any HTTP requests to the vLLM_Server, and SHALL return the configured vllm_base_url to the caller.
2. WHILE the Model_Manager mode is "mock", THE Knowledge_Service `generate_embeddings` method SHALL return random normalized vectors of exactly `model_embedding_dimension` dimensions (default 1024), one vector per input chunk, without making any HTTP requests to the vLLM_Server.
3. WHILE the Model_Manager mode is "mock", THE RAG_Pipeline `_generate_response` method SHALL return the existing placeholder response text without making any HTTP requests, and SHALL set the `grounded` flag to true in the RAGResponse when context chunks are available.
4. WHILE the Model_Manager mode is "mock", THE Knowledge_Service `_ocr_extract_text` method SHALL return the exact placeholder text "[OCR_PENDING: Scanned PDF text extraction requires Model_Manager]" without making any HTTP requests.
5. THE Model_Manager SHALL determine the operating mode from the `MODEL_MANAGER_MODE` environment variable (accepting only the values "gpu", "cpu", or "mock") at initialization time via Pydantic settings, and the mode SHALL not change during the lifetime of the application process.
6. WHEN the mode is switched from "mock" to "gpu" or "cpu" via environment variable change and application restart, THE system SHALL begin using real vLLM inference without requiring any code changes.
7. IF the `MODEL_MANAGER_MODE` environment variable is not set, THEN THE Model_Manager SHALL default to "mock" mode.

### Requirement 6: Inference Client Configuration and Error Handling

**User Story:** As a system administrator, I want robust HTTP client configuration with proper timeouts, retries, and error reporting, so that transient vLLM server issues do not cause silent failures or data corruption.

#### Acceptance Criteria

1. THE Inference_Client SHALL be configured as an async httpx client with a connection timeout of 10 seconds and separate read timeouts per operation type: 60 seconds for chat completions, 30 seconds for embeddings, and 90 seconds for OCR requests.
2. THE Inference_Client SHALL retry failed requests up to 2 additional attempts (3 total attempts) with exponential backoff delays of 1 second after the first failure and 2 seconds after the second failure, for HTTP 503 (Service Unavailable) responses and connection errors (ConnectionError, ConnectTimeout) only.
3. THE Inference_Client SHALL not retry requests that receive HTTP 400 (Bad Request), HTTP 422 (Validation Error), or any other 4xx response, as these indicate client-side issues that will not resolve on retry.
4. IF a request fails after all retry attempts are exhausted, THEN THE Inference_Client SHALL raise an exception containing the HTTP status code, response body (truncated to 500 characters if longer), and the endpoint URL that was called.
5. THE Inference_Client SHALL log all outgoing requests at DEBUG level (including endpoint URL, model name, and input size in characters) and all error responses at ERROR level (including HTTP status code, endpoint URL, and response body truncated to 500 characters).
6. THE Inference_Client SHALL use a single shared httpx.AsyncClient instance per Model_Manager lifetime to benefit from connection pooling, configured with a maximum of 10 concurrent connections to the vLLM_Server.
7. WHEN the application shuts down, THE Inference_Client SHALL close the httpx.AsyncClient instance and release all connections within 5 seconds.
8. IF a connection to the vLLM_Server cannot be established within the 10-second connection timeout, THEN THE Inference_Client SHALL treat this as a connection error eligible for retry per criterion 2.

### Requirement 7: RAG System Prompt and Grounding Enforcement

**User Story:** As a compliance officer, I want the LLM to only answer based on retrieved document content and clearly indicate when it cannot answer, so that responses are traceable to source documents and hallucination is minimized.

#### Acceptance Criteria

1. THE RAG_Pipeline SHALL include a system prompt instructing the Chat_Model to: (a) answer only based on the provided context, (b) cite source numbers using the format [Source N] when referencing information, (c) state clearly when the context does not contain sufficient information to answer, and (d) never fabricate information not present in the context.
2. WHEN the Chat_Model generates a response with document context available, THE RAG_Pipeline SHALL set the `grounded` flag to true in the RAGResponse.
3. WHEN no search results are retrieved (empty results list from hybrid_search), THE RAG_Pipeline SHALL return the existing NO_CONTENT_MESSAGE with `grounded` set to false without calling the Chat_Model.
4. THE RAG_Pipeline SHALL format each context chunk with the source reference pattern `[Source N: title vVersion]` followed by the chunk text, so the Chat_Model can reference specific sources in its response.
5. THE RAG_Pipeline SHALL limit the total context passed to the Chat_Model to a maximum of 8192 tokens (approximated by whitespace splitting where 1 token equals 1 whitespace-delimited word) by removing the lowest-relevance-scored chunks until the combined context is within the limit.
6. IF the total context from all retrieved chunks exceeds 8192 tokens after truncation, THEN THE RAG_Pipeline SHALL include at least the single highest-relevance chunk regardless of its individual token count.

### Requirement 8: Embedding Generation for Search Queries

**User Story:** As a user performing semantic search, I want my search query to be embedded using the same model as the indexed documents, so that semantic similarity matching works correctly.

#### Acceptance Criteria

1. WHEN `hybrid_search` is called on the Knowledge_Service in gpu or cpu mode, THE Knowledge_Service SHALL generate an embedding for the search query by calling `ensure_model(EMBEDDING)` on the Model_Manager and then requesting an embedding from the vLLM_Server using the same Embedding_Model used for document indexing.
2. THE Knowledge_Service SHALL call `generate_embeddings` with a single-element list containing the search query text to produce exactly one query embedding vector of `model_embedding_dimension` dimensions (default 1024).
3. THE Knowledge_Service SHALL use the query embedding vector for kNN similarity matching against indexed document chunk embeddings in the hybrid search scoring.
4. WHILE the Model_Manager mode is "mock", THE Knowledge_Service SHALL continue using the existing keyword matching logic for hybrid_search without generating query embeddings and without making any HTTP requests.
5. IF embedding generation fails for the search query (timeout or HTTP error), THEN THE Knowledge_Service SHALL fall back to keyword-only search and log a warning indicating that semantic search is unavailable for this query.

### Requirement 9: vLLM Server Health Monitoring

**User Story:** As a system administrator, I want the Model_Manager to expose health status information about the vLLM server connection, so that I can monitor system readiness and diagnose issues.

#### Acceptance Criteria

1. THE Model_Manager `get_status` method SHALL return a status object including a `vllm_reachable` field: true if the vLLM_Server `/health` endpoint responded with HTTP 200 within the timeout, false if it failed, or null when in mock mode.
2. WHEN `get_status` is called in gpu or cpu mode, THE Model_Manager SHALL perform an HTTP GET request to `{vllm_base_url}/health` with a 5-second timeout to determine vLLM_Server reachability.
3. WHEN `get_status` is called in mock mode, THE Model_Manager SHALL set `vllm_reachable` to null (not applicable) without making any HTTP requests.
4. IF the vLLM_Server health check fails during `get_status` (connection error, timeout, or non-200 response), THEN THE Model_Manager SHALL set `vllm_reachable` to false and log a warning containing the failure reason, but SHALL not raise an exception.
5. THE Model_Manager `get_status` method SHALL include the `current_role` (ModelRole enum value or null), `current_model_name` (string or null), `gpu_memory_used_gb` (float), `is_ready` (boolean), and `mode` (string: "gpu", "cpu", or "mock") fields.
6. THE Model_Manager `get_status` method SHALL complete within 6 seconds regardless of vLLM_Server responsiveness (5-second health check timeout plus 1-second processing margin).

### Requirement 10: Concurrent Inference Request Handling

**User Story:** As a system handling multiple simultaneous users, I want inference requests to be queued properly when a model swap is in progress, so that no requests are lost or receive errors due to model transitions.

#### Acceptance Criteria

1. WHILE the Model_Manager async lock is held (model swap in progress), THE Model_Manager SHALL queue incoming `ensure_model` calls using asyncio.Lock, which processes waiting coroutines sequentially in FIFO order after the lock is released.
2. WHEN multiple inference requests arrive for the same Model_Role that is already loaded and ready (is_ready is true), THE Model_Manager SHALL allow them to proceed concurrently without acquiring the model swap lock.
3. WHEN an inference request arrives for a different Model_Role than the currently loaded role, THE Model_Manager SHALL acquire the async lock, unload the current model, load the requested model, and then allow the request to proceed.
4. IF a model swap fails during a queued request, THEN THE Model_Manager SHALL raise a ModelManagerError to the caller whose request triggered the swap, and subsequent queued callers requesting the same failed role SHALL also receive a ModelManagerError when they attempt their own swap.
5. THE Model_Manager SHALL use a single asyncio.Lock instance to serialize all model swap operations, preventing deadlock by ensuring no nested lock acquisition occurs within the swap path.
