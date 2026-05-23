# Requirements Document

## Introduction

This feature transforms the static Knowledge Chat page shell into a fully functional chat-style interface for asking questions against indexed documents using the existing RAG pipeline backend. The implementation connects the KnowledgePage component to a new Zustand store (`knowledgeStore`) and the existing `POST /api/knowledge/query` and `POST /api/knowledge/conversation` endpoints. Users can ask natural-language questions, receive grounded answers with source citations linking to original documents, manage conversation history (start new, continue, clear), and experience proper loading states, error handling, and accessibility support. The backend RAG pipeline and API endpoints already exist — this phase focuses on full frontend integration and any minor backend extensions needed for conversation listing.

## Glossary

- **Knowledge_Page**: The React page component at `/knowledge` that provides the chat-style interface with message bubbles, citation display, and input controls.
- **Knowledge_Store**: The Zustand state store (`knowledgeStore.ts`) managing conversation state, messages, loading/error states, and exposing actions for querying, conversation management, and history.
- **Knowledge_API**: The FastAPI router at `/api/knowledge` providing `POST /api/knowledge/query` (new conversation query) and `POST /api/knowledge/conversation` (follow-up query) endpoints.
- **RAG_Pipeline**: The backend service that retrieves relevant document chunks, generates grounded responses, and returns source citations with conversation context management.
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the `X-Change-Reason` audit header.
- **Chat_Message**: A single message in the conversation, either from the user (question) or the assistant (answer with optional citations).
- **Source_Citation**: A reference to a specific document chunk used to ground the assistant's answer, containing document_uuid, title, version, and page_or_section.
- **Conversation_ID**: A UUID string identifying a conversation session, used to maintain context for follow-up questions.
- **Grounded_Response**: An assistant response that is backed by retrieved document content (grounded=true), as opposed to a "no content found" response (grounded=false).
- **Typing_Indicator**: A visual animation displayed while waiting for the RAG pipeline to generate a response, indicating the system is processing.

## Requirements

### Requirement 1: Knowledge Store — State Management

**User Story:** As a frontend developer, I want a Zustand store managing the complete knowledge chat lifecycle (messages, conversations, loading, errors), so that all chat-related components share consistent state.

#### Acceptance Criteria

1. THE Knowledge_Store SHALL maintain state for: `messages` (array of Chat_Message objects with role, content, citations, timestamp, and grounded flag, maximum 200 messages per conversation), `conversationId` (string or null), `isLoading` (boolean), `error` (string or null), and `inputValue` (string).
2. WHEN the `sendMessage` action is called with a non-empty question string, THE Knowledge_Store SHALL append a user Chat_Message (with timestamp set to the current client time in ISO 8601 format) to the `messages` array, set `isLoading` to true, clear `error`, clear `inputValue`, and send the appropriate API request via the API_Client.
3. WHEN `conversationId` is null and `sendMessage` is called, THE Knowledge_Store SHALL send a POST request to `/api/knowledge/query` with the question, user_id (obtained from the authenticated session state), and top_k parameter (default value of 5), and store the returned `conversation_id` in state.
4. WHEN `conversationId` is not null and `sendMessage` is called, THE Knowledge_Store SHALL send a POST request to `/api/knowledge/conversation` with the question, user_id (obtained from the authenticated session state), conversation_id, and top_k parameter (default value of 5).
5. WHEN the API response is received successfully, THE Knowledge_Store SHALL append an assistant Chat_Message to the `messages` array containing the answer text, citations array, grounded flag, timestamp set to the current client time in ISO 8601 format, and set `isLoading` to false.
6. IF the API request fails due to a network error or returns an HTTP status code of 500 or above, THEN THE Knowledge_Store SHALL set `error` to the error message string from the response body (or "Network error" if no response was received), set `isLoading` to false, and remove the optimistically-added user message from the `messages` array.
7. WHEN the `startNewConversation` action is called, THE Knowledge_Store SHALL reset `messages` to an empty array, set `conversationId` to null, clear `error`, and clear `inputValue`.
8. WHEN the `clearConversation` action is called, THE Knowledge_Store SHALL reset `messages` to an empty array, set `conversationId` to null, clear `error`, and clear `inputValue`.
9. WHILE `isLoading` is true, THE Knowledge_Store SHALL skip execution of the `sendMessage` action without modifying state (request deduplication to prevent concurrent queries).
10. IF the question string is empty or contains only whitespace when `sendMessage` is called, THEN THE Knowledge_Store SHALL not send an API request, SHALL not modify the messages array, and SHALL not modify `isLoading`.
11. IF the API request fails with HTTP 422 (validation error), THEN THE Knowledge_Store SHALL set `error` to the validation error detail from the response body, set `isLoading` to false, and remove the optimistically-added user message from the `messages` array.

### Requirement 2: Knowledge Store — Message Data Model

**User Story:** As a frontend developer, I want a well-defined message data model that captures all information needed for rendering chat bubbles and citations, so that the UI can display rich conversation content.

#### Acceptance Criteria

1. THE Knowledge_Store SHALL define each Chat_Message with the following fields: `id` (UUID v4 string generated at message creation time), `role` (either "user" or "assistant"), `content` (non-empty string with a maximum length of 10,000 characters), `citations` (array of Source_Citation objects containing between 0 and 20 items, empty for user messages), `grounded` (boolean, always true for user messages), and `timestamp` (ISO 8601 UTC string representing when the message was created).
2. THE Knowledge_Store SHALL define each Source_Citation with the following fields: `document_uuid` (string matching the Document-UUID format from the document repository), `title` (string, maximum 255 characters), `version` (string in semver-like format, e.g., "1.0", "2.1"), and `page_or_section` (string, maximum 100 characters, representing the page number or section heading of the cited content).
3. WHEN an assistant message has `grounded` set to false, THE Knowledge_Page SHALL render the message with muted styling and an info icon to indicate that no relevant content was found in the knowledge base.
4. IF an assistant Chat_Message has `grounded` set to false, THEN THE Knowledge_Store SHALL ensure the `citations` array is empty for that message.

### Requirement 3: Chat Message Display

**User Story:** As a user, I want to see my questions and the assistant's answers displayed as chat bubbles in a conversational layout, so that I can follow the dialogue naturally.

#### Acceptance Criteria

1. THE Knowledge_Page SHALL render user messages as right-aligned chat bubbles with a distinct background color and the message content text displayed as plain text.
2. THE Knowledge_Page SHALL render assistant messages as left-aligned chat bubbles with a distinct background color, the answer content text rendered as formatted markdown (headings, bold, italic, lists, code blocks), and any associated source citations below the answer.
3. WHEN a new message is added to the conversation and the message area is scrolled to within 100 pixels of the bottom, THE Knowledge_Page SHALL automatically scroll the message area to the bottom to show the latest message.
4. IF a new message is added to the conversation and the user has scrolled more than 100 pixels above the bottom of the message area, THEN THE Knowledge_Page SHALL not auto-scroll and SHALL display a "New message" indicator that, when clicked, scrolls to the bottom.
5. WHEN the conversation has no messages (initial state or after clearing), THE Knowledge_Page SHALL display a welcome placeholder with the heading text "Ask questions about your documents" and a subtitle describing that users can ask natural language questions and receive answers with source citations from their indexed documents.
6. THE Knowledge_Page SHALL display a timestamp on each message showing when the message was sent, formatted as relative time ("just now" for under 60 seconds, "N minutes ago" for under 60 minutes, "N hours ago" for under 24 hours) and switching to short time format "HH:MM" (24-hour) for messages older than 24 hours.
7. WHEN an assistant message contains markdown syntax, THE Knowledge_Page SHALL render the markdown as formatted HTML (supporting headings, bold, italic, inline code, code blocks, and lists) rather than displaying raw markdown text.

### Requirement 4: Source Citation Display

**User Story:** As a user, I want to see which documents were used to generate an answer, with clickable links to the original documents, so that I can verify the information and access the source material.

#### Acceptance Criteria

1. WHEN an assistant message has one or more citations, THE Knowledge_Page SHALL render a "Sources" section below the answer text listing each citation with the document title, version, and page_or_section.
2. WHEN an assistant message has one or more citations, THE Knowledge_Page SHALL render each citation title as a clickable link that navigates to `/documents/{document_uuid}`.
3. WHEN an assistant message has one or more citations, THE Knowledge_Page SHALL display the citation version as a badge (e.g., "v1.0") adjacent to the title link, and the page_or_section as secondary text displayed after the badge on the same line.
4. WHEN an assistant message has `grounded` set to false (no relevant content found), THE Knowledge_Page SHALL not render a Sources section and SHALL display a visual indicator (e.g., an info icon with muted styling) that the response is not backed by document content.
5. WHEN an assistant message has citations, THE Knowledge_Page SHALL display the number of sources referenced (e.g., "3 sources") as a summary label that defaults to collapsed state, and SHALL expand to show the full citation list when the user activates the summary element.
6. WHEN an assistant message has citations, THE Knowledge_Page SHALL display a maximum of 50 citations in the expanded list, matching the maximum retrievable from the backend.
7. IF a citation link is activated but the target document is unavailable, THEN THE Knowledge_Page SHALL navigate to `/documents/{document_uuid}` and the documents page SHALL handle the missing resource by displaying an error message indicating the document was not found.

### Requirement 5: Chat Input and Message Submission

**User Story:** As a user, I want to type questions and submit them easily using keyboard or button, so that I can interact with the knowledge base efficiently.

#### Acceptance Criteria

1. THE Knowledge_Page SHALL display a multi-line text input field (textarea) at the bottom of the chat area with placeholder text "Ask a question about your documents...", a maximum input length of 2000 characters, and a Send button with an icon.
2. WHEN the user presses the Enter key while the input is focused and the trimmed input is not empty, THE Knowledge_Page SHALL call `sendMessage` on the Knowledge_Store with the current trimmed input value, clear the input field, and return focus to the input field.
3. WHEN the user clicks the Send button and the trimmed input is not empty, THE Knowledge_Page SHALL call `sendMessage` on the Knowledge_Store with the current trimmed input value, clear the input field, and return focus to the input field.
4. WHILE `isLoading` is true, THE Knowledge_Page SHALL disable the Send button and the input field to prevent duplicate submissions.
5. IF the input field is empty or contains only whitespace characters, THEN THE Knowledge_Page SHALL disable the Send button and SHALL not submit on Enter key press.
6. WHEN the user presses Shift+Enter while the input is focused, THE Knowledge_Page SHALL insert a newline in the input field without submitting the message, allowing multi-line questions.
7. IF the user input exceeds 2000 characters, THEN THE Knowledge_Page SHALL prevent further character entry and SHALL display a character count indicator showing the current length relative to the maximum.

### Requirement 6: Loading State and Typing Indicator

**User Story:** As a user, I want to see a visual indicator while the system is processing my question, so that I know the system is working and have not encountered an error.

#### Acceptance Criteria

1. WHILE `isLoading` is true, THE Knowledge_Page SHALL display a Typing_Indicator in the message area below the last user message, styled as a left-aligned assistant bubble with an animated dots pattern, and with an `aria-live="polite"` region announcing "Assistant is typing" to screen readers.
2. WHILE `isLoading` is true, THE Knowledge_Page SHALL keep the message area scrolled to the bottom so the typing indicator is visible, and SHALL disable the message input field and send button to prevent duplicate submissions.
3. WHEN the assistant response is received, THE Knowledge_Page SHALL remove the Typing_Indicator and replace it with the actual assistant message bubble within 200 milliseconds of receiving the response.
4. IF the assistant response is not received within 30 seconds, THEN THE Knowledge_Page SHALL remove the Typing_Indicator, re-enable the message input field and send button, and display an inline error message indicating the request timed out with an option to retry.

### Requirement 7: Conversation Management

**User Story:** As a user, I want to start new conversations and clear the current conversation, so that I can organize my queries by topic and start fresh when needed.

#### Acceptance Criteria

1. THE Knowledge_Page SHALL display a "New Conversation" button in the header area that calls `startNewConversation` on the Knowledge_Store when clicked.
2. WHEN the user clicks "New Conversation", THE Knowledge_Page SHALL clear all messages, reset the conversation ID, and display the welcome placeholder state.
3. THE Knowledge_Page SHALL display a "Clear" button in the header area that calls `clearConversation` on the Knowledge_Store when the user confirms the action.
4. WHEN the user clicks "Clear" while messages exist in the conversation, THE Knowledge_Page SHALL display a confirmation dialog with a message indicating the conversation will be permanently removed, a "Confirm" button to proceed with clearing, and a "Cancel" button to dismiss the dialog without clearing.
5. IF the user clicks "Cancel" on the clear confirmation dialog, THEN THE Knowledge_Page SHALL dismiss the dialog and preserve the current conversation state unchanged.
6. IF the user clicks "Clear" while no messages exist in the conversation, THEN THE Knowledge_Page SHALL disable the "Clear" button or not trigger the confirmation dialog, preventing a no-op clear action.
7. THE Knowledge_Page SHALL display a conversation status label in the header area showing "New conversation" when `conversationId` is null, and "Ongoing conversation" when `conversationId` is not null.

### Requirement 8: Error Handling

**User Story:** As a user, I want graceful handling of errors during knowledge queries, so that I always understand the system state and can recover from failures.

#### Acceptance Criteria

1. IF the Knowledge_API returns HTTP 500 or the network request does not respond within 30 seconds, THEN THE Knowledge_Page SHALL display an error message inline in the chat area styled as a system message with the text "Something went wrong. Please try again." and a "Retry" button.
2. WHEN the user clicks the "Retry" button on an error message, THE Knowledge_Page SHALL re-send the last failed question using the current conversation context, up to a maximum of 3 consecutive retry attempts per failed question.
3. IF the user has reached the maximum of 3 consecutive retry attempts for the same failed question, THEN THE Knowledge_Page SHALL disable the "Retry" button and display a message indicating that retries are exhausted and the user should try a different question.
4. IF the Knowledge_API returns HTTP 422 (validation error), THEN THE Knowledge_Page SHALL display an inline error message showing the validation detail extracted from the API response body (e.g., "Question must not be empty").
5. IF the user's session expires during a query (API_Client throws "Session expired"), THEN THE Knowledge_Page SHALL not display a chat error and SHALL allow the API_Client's existing redirect-to-login flow to handle the session expiry.
6. IF the Knowledge_Store `error` is not null, THEN THE Knowledge_Page SHALL display the error in the chat area and SHALL re-enable the input field and Send button so the user can try a different question.
7. WHEN the user submits a new question or a retry succeeds, THE Knowledge_Page SHALL remove any previously displayed error message from the chat area.

### Requirement 9: Accessibility and ARIA Support

**User Story:** As a user relying on assistive technology, I want the knowledge chat interface to be fully accessible, so that I can effectively ask questions and read answers using a screen reader or keyboard.

#### Acceptance Criteria

1. THE Knowledge_Page SHALL include `role="log"` and `aria-label="Conversation messages"` on the message area container to identify it as a chat log for assistive technology.
2. WHEN a new assistant message or error message is added to the conversation, THE Knowledge_Page SHALL announce the new content to screen readers using an `aria-live="polite"` region.
3. THE Knowledge_Page SHALL ensure all interactive elements (input field, Send button, New Conversation button, Clear button, citation links, Retry button) are reachable via keyboard Tab navigation in a logical order.
4. THE Knowledge_Page SHALL provide `aria-label` attributes on the Send button ("Send message"), New Conversation button ("Start new conversation"), and Clear button ("Clear conversation").
5. WHILE `isLoading` is true, THE Knowledge_Page SHALL set `aria-busy="true"` on the message area container to inform assistive technology that content is loading, and SHALL set `aria-busy="false"` when `isLoading` becomes false.
6. THE Knowledge_Page SHALL provide `aria-label="Chat message input"` on the text input field.
7. THE Knowledge_Page SHALL ensure each citation link has an accessible label in the format "Open document: {title} version {version}".
8. WHEN a message is submitted, a conversation is cleared, or a Retry action completes, THE Knowledge_Page SHALL return keyboard focus to the chat input field.
9. WHILE the Send button or input field is disabled during loading, THE Knowledge_Page SHALL communicate the disabled state to assistive technology via the HTML `disabled` attribute on both elements.

### Requirement 10: Responsive Layout and Visual Design

**User Story:** As a user, I want the knowledge chat interface to be visually polished and responsive, so that I can use it comfortably on different screen sizes.

#### Acceptance Criteria

1. THE Knowledge_Page SHALL use a full-height flex column layout where the message area expands to fill all available vertical space between the header and the input area, and the input area remains anchored at the bottom of the flex container (not viewport-fixed).
2. THE Knowledge_Page SHALL constrain each message bubble width to a maximum of 80% of the chat area width on viewports 768px and wider, and a maximum of 90% of the chat area width on viewports narrower than 768px, with a minimum bubble width of 120px.
3. WHEN messages exceed the visible height of the chat area, THE Knowledge_Page SHALL render the message area with vertical scroll overflow, keeping the input area visible without scrolling.
4. THE Knowledge_Page SHALL style user message bubbles and assistant message bubbles with different Tailwind CSS theme background color classes so that the two roles are visually distinguishable without relying on alignment alone.
5. THE Knowledge_Page SHALL display the page header with the title "Knowledge Chat" using the same heading level and styling as other page shells in the application, and the subtitle "Ask questions about your documents with source citations" using muted foreground text below the title.
6. WHEN the viewport width is narrower than 768px, THE Knowledge_Page SHALL maintain the same flex column layout structure (header, scrollable message area, input area) without horizontal overflow or content clipping.
