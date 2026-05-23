# Implementation Plan: RAG Knowledge Base UI

## Overview

This plan implements the full RAG Knowledge Base chat UI by creating a new Zustand `knowledgeStore` managing conversation state, messages, loading/error states, and actions for querying the existing backend RAG endpoints. Then it decomposes the static `KnowledgePage` shell into functional components (`ChatMessage`, `CitationList`, `TypingIndicator`, `ChatInput`) with markdown rendering, source citations, conversation management, retry logic, and comprehensive ARIA accessibility. The implementation is frontend-only — no backend changes are required.

## Tasks

- [ ] 1. Knowledge store implementation
  - [-] 1.1 Implement knowledgeStore with full state and actions
    - Create `src/frontend/src/stores/knowledgeStore.ts`
    - Define `ChatMessage` interface with `id` (UUID v4), `role` ("user" | "assistant"), `content` (max 10,000 chars), `citations` (SourceCitation[], 0-20 items), `grounded` (boolean), `timestamp` (ISO 8601 UTC)
    - Define `SourceCitation` interface with `document_uuid`, `title` (max 255 chars), `version` (semver-like), `page_or_section` (max 100 chars)
    - Define `KnowledgeState` interface with: `messages` (max 200), `conversationId` (string | null), `isLoading`, `error` (string | null), `inputValue`, `retryCount`, `lastFailedQuestion` (string | null)
    - Implement `sendMessage(question)`: guard against concurrent calls (`isLoading` check), reject whitespace-only input, append user ChatMessage optimistically (UUID id, timestamp, role="user", empty citations, grounded=true), set `isLoading=true`, clear `error` and `inputValue`
    - Route to correct endpoint: if `conversationId` is null → POST `/api/knowledge/query` with `{ question, user_id, top_k: 5 }`; if not null → POST `/api/knowledge/conversation` with `{ question, user_id, conversation_id, top_k: 5 }`
    - Use `apiClient.post` with `changeReason: "Knowledge base query"` (new) or `"Knowledge base conversation query"` (follow-up)
    - Get `user_id` from `useAuthStore.getState().user?.id`
    - On success: append assistant ChatMessage (answer, citations, grounded, timestamp), store `conversation_id`, set `isLoading=false`, reset `retryCount` to 0, clear `lastFailedQuestion`
    - On failure (network error, HTTP >= 500, HTTP 422): set `error` to message, set `isLoading=false`, remove optimistically-added user message, store question in `lastFailedQuestion`
    - Implement `retryLastMessage()`: re-send `lastFailedQuestion` if `retryCount < 3` and `lastFailedQuestion` is not null, increment `retryCount`
    - Implement `startNewConversation()`: reset messages=[], conversationId=null, error=null, inputValue="", retryCount=0, lastFailedQuestion=null
    - Implement `clearConversation()`: same reset as startNewConversation
    - Implement `setInputValue(value)`: update inputValue, cap at 2000 characters
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 2.1, 2.2, 2.4_

  - [~] 1.2 Write unit tests for knowledgeStore
    - Test initial state has correct defaults (messages=[], conversationId=null, isLoading=false, error=null, inputValue="")
    - Test `sendMessage()` appends user message and calls `/api/knowledge/query` when no conversationId
    - Test `sendMessage()` calls `/api/knowledge/conversation` when conversationId exists
    - Test `sendMessage()` stores conversation_id from response
    - Test `sendMessage()` handles successful response with citations
    - Test `sendMessage()` handles ungrounded response (grounded=false, empty citations)
    - Test `sendMessage()` handles HTTP 500 error with rollback (removes user message)
    - Test `sendMessage()` handles HTTP 422 with validation detail
    - Test `sendMessage()` skips when isLoading=true (deduplication)
    - Test `sendMessage()` rejects empty string
    - Test `sendMessage()` rejects whitespace-only string
    - Test `retryLastMessage()` re-sends last failed question
    - Test `retryLastMessage()` increments retryCount
    - Test `retryLastMessage()` does nothing when retryCount >= 3
    - Test `retryLastMessage()` does nothing when lastFailedQuestion is null
    - Test `startNewConversation()` resets all state
    - Test `clearConversation()` resets all state
    - Test `setInputValue()` updates inputValue
    - Test `setInputValue()` caps at 2000 characters
    - Mock `apiClient.post` for all tests
    - Mock `useAuthStore` to provide consistent `user.id`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStore.test.ts`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

- [ ] 2. Knowledge store property tests
  - [~] 2.1 Write property test for sendMessage state transition
    - **Property 1: sendMessage state transition**
    - Generate random non-empty, non-whitespace strings
    - Verify: user ChatMessage appended with valid UUID v4 id, role="user", trimmed question as content, empty citations, grounded=true, valid ISO 8601 timestamp; isLoading set to true; error set to null; inputValue set to ""
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 1: sendMessage state transition`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.2**

  - [~] 2.2 Write property test for endpoint routing based on conversationId
    - **Property 2: Endpoint routing based on conversationId**
    - Generate random questions with null/non-null conversationId states
    - Verify: when conversationId is null, POST sent to `/api/knowledge/query` with `{ question, user_id, top_k: 5 }`; when non-null, POST sent to `/api/knowledge/conversation` with `{ question, user_id, conversation_id, top_k: 5 }`
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 2: Endpoint routing based on conversationId`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.3, 1.4**

  - [~] 2.3 Write property test for successful response handling
    - **Property 3: Successful response appends correct assistant message**
    - Generate random API responses with answer string, citations array (0-20 items), grounded boolean, conversation_id string
    - Verify: assistant ChatMessage appended with answer as content, citations mapped correctly, grounded flag preserved, valid ISO 8601 timestamp, conversation_id stored, isLoading set to false
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 3: Successful response appends correct assistant message`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.5**

  - [~] 2.4 Write property test for failed request rollback
    - **Property 4: Failed request error handling and rollback**
    - Generate random error scenarios (network error, HTTP 500, HTTP 422)
    - Verify: error set to non-empty string, isLoading set to false, last user message removed from messages array
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 4: Failed request error handling and rollback`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.6, 1.11**

  - [~] 2.5 Write property test for reset actions
    - **Property 5: Reset actions clear all state**
    - Generate random store states (various messages, conversationId, error, inputValue combinations)
    - Verify: both `startNewConversation` and `clearConversation` set messages=[], conversationId=null, error=null, inputValue=""
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 5: Reset actions clear all state`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.7, 1.8**

  - [~] 2.6 Write property test for request deduplication
    - **Property 6: Request deduplication when loading**
    - Generate random states with isLoading=true and any question string
    - Verify: sendMessage does not modify messages, does not change isLoading, does not change error, does not initiate network request
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 6: Request deduplication when loading`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.9**

  - [~] 2.7 Write property test for whitespace rejection
    - **Property 7: Whitespace-only input rejection**
    - Generate random strings composed entirely of whitespace (spaces, tabs, newlines, empty string)
    - Verify: sendMessage does not modify messages, does not change isLoading, does not change error, does not initiate network request
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 7: Whitespace-only input rejection`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 1.10**

  - [~] 2.8 Write property test for ungrounded citations invariant
    - **Property 8: Ungrounded messages have empty citations**
    - Generate random assistant ChatMessages with grounded=false
    - Verify: citations array is empty (length 0)
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 8: Ungrounded messages have empty citations`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 2.4**

  - [~] 2.9 Write property test for timestamp formatting
    - **Property 9: Timestamp formatting**
    - Generate random timestamps at various offsets from now
    - Verify: < 60s → "just now"; 60s-60min → "N minutes ago"; 60min-24h → "N hours ago"; > 24h → "HH:MM" 24-hour format
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 9: Timestamp formatting`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 3.6**

  - [~] 2.10 Write property test for citation link correctness
    - **Property 10: Citation link correctness**
    - Generate random SourceCitations with document_uuid, title, version
    - Verify: rendered link href is `/documents/{document_uuid}` and aria-label is "Open document: {title} version {version}"
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 10: Citation link correctness`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 4.2, 9.7**

  - [~] 2.11 Write property test for error clearing on new question
    - **Property 11: New question clears previous error**
    - Generate random store states where error is not null, then call sendMessage with valid non-empty question
    - Verify: error is set to null before the API request is made
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Tag: `// Feature: rag-knowledge-base-ui, Property 11: New question clears previous error`
    - Target file: `src/frontend/src/__tests__/stores/knowledgeStoreProperties.test.ts`
    - **Validates: Requirements 8.7**

- [~] 3. Checkpoint - Ensure all store tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Frontend knowledge chat components
  - [~] 4.1 Implement ChatMessage component
    - Create `src/frontend/src/components/knowledge/ChatMessage.tsx`
    - Accept props: `message: ChatMessage`, `onCitationClick?: (documentUuid: string) => void`
    - Render user messages: right-aligned bubble with distinct Tailwind background, plain text content, relative timestamp
    - Render assistant messages: left-aligned bubble with distinct Tailwind background, markdown-rendered content (headings, bold, italic, lists, code blocks via a lightweight markdown renderer), collapsible CitationList below, relative timestamp
    - Render ungrounded assistant messages: muted styling with info icon, no citations section
    - Constrain bubble width: max 80% on viewports ≥ 768px, max 90% on narrower, min 120px
    - Display relative timestamp: "just now" (< 60s), "N minutes ago" (< 60min), "N hours ago" (< 24h), "HH:MM" (> 24h)
    - _Requirements: 3.1, 3.2, 3.6, 3.7, 2.3, 10.2, 10.4_

  - [~] 4.2 Implement CitationList component
    - Create `src/frontend/src/components/knowledge/CitationList.tsx`
    - Accept props: `citations: SourceCitation[]`, `defaultExpanded?: boolean`
    - Render summary label showing count (e.g., "3 sources") — collapsed by default
    - Expand on click to show full citation list
    - Each citation: title as `<Link to="/documents/{document_uuid}">` with `aria-label="Open document: {title} version {version}"`, version badge, page_or_section text
    - Maximum 50 citations displayed
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 9.7_

  - [~] 4.3 Implement TypingIndicator component
    - Create `src/frontend/src/components/knowledge/TypingIndicator.tsx`
    - No props — purely visual component
    - Render left-aligned assistant-style bubble with animated dots (CSS animation using Tailwind `animate-pulse` or custom keyframes)
    - Include `aria-live="polite"` region with text "Assistant is typing"
    - _Requirements: 6.1, 6.3_

  - [~] 4.4 Implement ChatInput component
    - Create `src/frontend/src/components/knowledge/ChatInput.tsx`
    - Accept props: `value: string`, `onChange: (value: string) => void`, `onSubmit: () => void`, `disabled: boolean`, `maxLength: number`
    - Render multi-line `<textarea>` with placeholder "Ask a question about your documents...", `aria-label="Chat message input"`
    - Render Send button with Lucide `<Send>` icon, `aria-label="Send message"`
    - Enter submits (when trimmed input non-empty), Shift+Enter inserts newline
    - Both textarea and button disabled when `disabled=true` (communicates via HTML `disabled` attribute)
    - Show character count indicator (e.g., "1234/2000") when approaching limit (> 1800 chars)
    - Prevent input beyond 2000 characters
    - Do not submit when empty/whitespace
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 9.6, 9.9_

- [ ] 5. KnowledgePage full integration
  - [~] 5.1 Rewrite KnowledgePage with full component integration
    - Rewrite `src/frontend/src/pages/KnowledgePage.tsx` from static shell to full implementation
    - Full-height flex column layout: header → scrollable message area → input area anchored at bottom
    - Header: title "Knowledge Chat", subtitle "Ask questions about your documents with source citations", "New Conversation" button (`aria-label="Start new conversation"`), "Clear" button (`aria-label="Clear conversation"`), conversation status label ("New conversation" / "Ongoing conversation")
    - Message area: `role="log"`, `aria-label="Conversation messages"`, `aria-busy` toggled with isLoading
    - Welcome placeholder when no messages: heading "Ask questions about your documents", subtitle about natural language questions with source citations
    - Wire `ChatMessage` components for each message in the conversation
    - Wire `TypingIndicator` when `isLoading` is true (displayed below last user message)
    - Wire `ChatInput` connected to `knowledgeStore.inputValue`, `setInputValue`, `sendMessage`
    - Auto-scroll: when within 100px of bottom → auto-scroll on new message; when scrolled up → show "New message" indicator
    - Disable input and Send button while `isLoading` is true
    - Error display: inline error message in chat area with "Retry" button calling `retryLastMessage()`
    - Disable Retry after 3 attempts with message "Retries exhausted. Please try a different question."
    - HTTP 422 error: display validation detail from response
    - Clear confirmation dialog: show when messages exist, "Confirm"/"Cancel" buttons
    - Clear button disabled when no messages
    - `aria-live="polite"` region announcing new assistant messages and errors
    - Return focus to input after submit, clear, or retry
    - Responsive: same flex layout on narrow viewports without overflow
    - _Requirements: 3.3, 3.4, 3.5, 5.4, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

- [ ] 6. Frontend component tests
  - [~] 6.1 Write unit tests for ChatMessage component
    - Test renders user message right-aligned with correct background class
    - Test renders assistant message left-aligned with correct background class
    - Test renders markdown content as HTML (headings, bold, lists, code blocks)
    - Test renders ungrounded message with muted styling and info icon
    - Test displays relative timestamp correctly
    - Test renders CitationList for assistant messages with citations
    - Test does not render CitationList for ungrounded messages
    - Target file: `src/frontend/src/__tests__/components/knowledge/ChatMessage.test.tsx`
    - _Requirements: 3.1, 3.2, 3.6, 3.7, 2.3_

  - [~] 6.2 Write unit tests for CitationList component
    - Test renders collapsed with source count (e.g., "3 sources")
    - Test expands on click to show citation details
    - Test renders title as link to `/documents/{document_uuid}`
    - Test renders version badge and page_or_section text
    - Test limits display to 50 citations
    - Test link has correct aria-label "Open document: {title} version {version}"
    - Target file: `src/frontend/src/__tests__/components/knowledge/CitationList.test.tsx`
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 9.7_

  - [~] 6.3 Write unit tests for TypingIndicator component
    - Test renders animated dots in assistant bubble style
    - Test has aria-live="polite" with "Assistant is typing" text
    - Target file: `src/frontend/src/__tests__/components/knowledge/TypingIndicator.test.tsx`
    - _Requirements: 6.1_

  - [~] 6.4 Write unit tests for ChatInput component
    - Test renders textarea with placeholder and aria-label
    - Test renders Send button with aria-label
    - Test submits on Enter when non-empty
    - Test inserts newline on Shift+Enter
    - Test disables both elements when disabled=true
    - Test shows character count near limit (> 1800 chars)
    - Test prevents input beyond 2000 characters
    - Test does not submit when empty/whitespace
    - Target file: `src/frontend/src/__tests__/components/knowledge/ChatInput.test.tsx`
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 9.6, 9.9_

  - [~] 6.5 Write unit tests for KnowledgePage integration
    - Test renders header with title "Knowledge Chat" and subtitle
    - Test renders welcome placeholder when no messages
    - Test renders New Conversation and Clear buttons with aria-labels
    - Test shows conversation status label ("New conversation" / "Ongoing conversation")
    - Test renders message area with role="log" and aria-label
    - Test sets aria-busy="true" during loading
    - Test shows typing indicator during loading
    - Test shows error message with Retry button on failure
    - Test disables Retry after 3 attempts
    - Test shows confirmation dialog on Clear click when messages exist
    - Test Cancel on dialog preserves state
    - Test Clear button disabled when no messages
    - Test auto-scroll behavior when near bottom
    - Test "New message" indicator when scrolled up
    - Target file: `src/frontend/src/__tests__/components/knowledge/KnowledgePage.test.tsx`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5_

- [~] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Frontend uses React/TypeScript/Zustand with Vitest and fast-check for PBT (`npx vitest run` from `src/frontend/`)
- API prefix is `/api` (NOT `/api/v1`) for knowledge endpoints
- Knowledge router prefix is `/knowledge` (full paths: `POST /api/knowledge/query`, `POST /api/knowledge/conversation`)
- X-Change-Reason header required on POST requests (enforced by audit middleware)
- The `apiClient` handles 401 retry + redirect to login transparently
- No backend changes required — existing RAG pipeline endpoints are used as-is
- The `user_id` is obtained from `useAuthStore.getState().user?.id`
- Follow the same store pattern as `searchStore.ts` for consistency
