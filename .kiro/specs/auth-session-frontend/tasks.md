# Implementation Plan: Authentication & Session Management - Frontend

## Overview

This plan implements the full-stack authentication system for AlcoaBase: backend auth endpoints (login, refresh, logout, re-authenticate, me) with JWT token management and server-side refresh token storage, plus the frontend login page, token storage, API client, auth store, route guards, session timer, and re-authentication dialog. Tasks are ordered so each builds on the previous, with backend endpoints first (since frontend depends on them), then frontend infrastructure, then UI components, then integration wiring.

## Tasks

- [x] 1. Backend: RefreshToken model and database migration
  - [x] 1.1 Create the RefreshToken SQLAlchemy model
    - Create `src/backend/src/alcoabase/models/refresh_token.py`
    - Define `RefreshToken` class with columns: id, jti (String(36), unique, indexed), user_id (ForeignKey to users.id), expires_at (DateTime with timezone), revoked_at (DateTime nullable), created_at (server_default=func.now())
    - Import and register in models package `__init__.py`
    - _Requirements: 2.2, 2.5_

  - [x] 1.2 Create Alembic migration for refresh_tokens table
    - Generate migration with `alembic revision --autogenerate -m "add_refresh_tokens_table"`
    - Verify migration creates the table with proper indexes on `jti` column
    - _Requirements: 2.2_

- [x] 2. Backend: Auth schemas and service
  - [x] 2.1 Create auth Pydantic schemas
    - Create `src/backend/src/alcoabase/schemas/auth.py`
    - Define: `LoginRequest(username, password)`, `LoginResponse(access_token, token_type, expires_in, user)`, `RefreshResponse(access_token, token_type, expires_in)`, `LogoutResponse(message)`, `ReAuthRequest(password)`, `ReAuthResponse(verified, signature_token, expires_in)`, `MeResponse(id, username, email, full_name, roles, companies)`
    - Use Pydantic v2 model syntax with proper type hints
    - _Requirements: 1.3, 1.4, 7.1, 7.3_

  - [x] 2.2 Create auth service with token management
    - Create `src/backend/src/alcoabase/services/auth_service.py`
    - Implement `AuthService` class with methods: `authenticate_user(username, password)`, `create_access_token(user_id, username)`, `create_refresh_token(user_id)`, `refresh_access_token(refresh_jti)`, `revoke_refresh_token(jti)`, `verify_password(plain, hashed)`, `get_user_profile(user_id)`
    - Access tokens: 15-min expiry, HS256, payload with sub, username, exp, iat, type="access"
    - Refresh tokens: 7-day expiry, HS256, payload with sub, exp, iat, jti (uuid4), type="refresh"
    - Use `python-jose` for JWT encoding/decoding and `passlib[bcrypt]` for password hashing
    - Store refresh tokens in the database for revocation support
    - _Requirements: 2.1, 2.2, 2.5, 5.1, 5.2_

  - [x] 2.3 Write pytest unit tests for auth service
    - Test token creation returns valid JWTs with correct claims
    - Test password verification with correct and incorrect passwords
    - Test refresh token revocation marks token as revoked
    - Test expired token detection
    - _Requirements: 2.1, 2.2, 5.1_

- [x] 3. Backend: Auth API router
  - [x] 3.1 Create auth router with all endpoints
    - Create `src/backend/src/alcoabase/api/auth.py`
    - Implement `POST /login`: validate credentials, issue access token in response body, set refresh token as httpOnly cookie (Secure, SameSite=Lax, Path=/api/v1/auth)
    - Implement `POST /refresh`: read refresh token from cookie, validate and rotate, return new access token + new cookie
    - Implement `POST /logout`: read refresh token from cookie, revoke in DB, clear cookie
    - Implement `POST /re-authenticate`: require Bearer token, validate password, return short-lived signature_token (120s)
    - Implement `GET /me`: require Bearer token, return user profile with company memberships
    - Add `get_current_user` dependency that decodes Bearer token and returns user_id
    - _Requirements: 1.3, 1.5, 2.2, 2.5, 6.2, 7.1, 7.3, 7.4_

  - [x] 3.2 Register auth router in main API router
    - Import auth router in `src/backend/src/alcoabase/api/router.py`
    - Register with `api_router.include_router(auth_router, prefix="/v1/auth")`
    - _Requirements: 1.3_

  - [x] 3.3 Write pytest integration tests for auth endpoints
    - Test login with valid credentials returns 200 + access_token + Set-Cookie
    - Test login with invalid credentials returns 401
    - Test login with missing fields returns 422
    - Test refresh with valid cookie returns new access_token
    - Test refresh with expired/revoked token returns 401
    - Test logout clears cookie and revokes token
    - Test re-authenticate with valid password returns signature_token
    - Test re-authenticate with invalid password returns 401
    - Test /me with valid token returns user profile
    - Test /me with expired token returns 401
    - _Requirements: 1.3, 1.5, 2.2, 6.2, 7.3, 7.4_

- [x] 4. Checkpoint - Backend auth complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Frontend: Token storage module
  - [x] 5.1 Create token storage module
    - Create `src/frontend/src/lib/tokenStorage.ts`
    - Implement module-scoped closure storing access token in a private variable (not localStorage/sessionStorage)
    - Export functions: `getAccessToken(): string | null`, `setAccessToken(token: string): void`, `clearAccessToken(): void`, `getTokenExpiry(): number | null` (decodes JWT exp claim via base64)
    - Implement `decodeTokenExpiry` helper that parses JWT payload without a library (base64url decode of second segment)
    - _Requirements: 2.1, 2.4, 5.1_

  - [x] 5.2 Write property test for token storage round-trip (Property 1)
    - **Property 1: Token storage round-trip and clear**
    - **Validates: Requirements 2.1, 2.4, 2.5**
    - Use fast-check to generate arbitrary non-empty strings as tokens
    - Assert: setAccessToken(t) then getAccessToken() === t
    - Assert: after clearAccessToken(), getAccessToken() === null
    - Assert: localStorage and sessionStorage do not contain the token at any point

  - [x] 5.3 Write property test for JWT exp claim decoding (Property 9)
    - **Property 9: JWT exp claim decoding round-trip**
    - **Validates: Requirements 5.1**
    - Use fast-check to generate arbitrary integer timestamps
    - Create mock JWT with that exp claim (base64url encode header.payload.signature)
    - Assert: getTokenExpiry() returns the original timestamp
    - Assert: for tokens without exp claim, returns null

- [x] 6. Frontend: API client
  - [x] 6.1 Create API client wrapper
    - Create `src/frontend/src/lib/apiClient.ts`
    - Implement thin wrapper around native `fetch` with methods: `get<T>`, `post<T>`, `put<T>`, `delete<T>`
    - Attach `Authorization: Bearer <token>` from tokenStorage for authenticated requests
    - Support `skipAuth` option for public endpoints
    - Set `credentials: 'include'` to send httpOnly cookies
    - Set `Content-Type: application/json` and serialize body for non-GET requests
    - On 401: attempt one refresh call to `/api/v1/auth/refresh`, retry original request on success, clear auth state on failure
    - Attach `X-User-Id` and `X-Company-Id` headers when tenant context is available (read from auth store)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 6.2 Write property test for Bearer token attachment (Property 4)
    - **Property 4: API client attaches Bearer token for protected endpoints**
    - **Validates: Requirements 3.1**
    - Use fast-check to generate arbitrary URL paths and token strings
    - Mock fetch, assert Authorization header is present with correct token for non-skipAuth requests

  - [x] 6.3 Write property test for 401 retry logic (Property 5)
    - **Property 5: API client 401 retry with refresh**
    - **Validates: Requirements 3.3, 3.4**
    - Use fast-check to generate sequences of success/failure refresh outcomes
    - Assert: exactly one refresh attempt on 401, retry on success, clear state on failure

  - [x] 6.4 Write property test for tenant header attachment (Property 6)
    - **Property 6: API client attaches tenant headers when context exists**
    - **Validates: Requirements 3.5**
    - Use fast-check to generate optional userId/companyId pairs
    - Assert: headers present when context set, absent when not set

  - [x] 6.5 Write property test for JSON serialization (Property 7)
    - **Property 7: API client JSON serialization for non-GET requests**
    - **Validates: Requirements 3.6**
    - Use fast-check to generate HTTP methods and body objects
    - Assert: Content-Type set and body serialized for non-GET, no body for GET

- [x] 7. Frontend: Auth store refactor
  - [x] 7.1 Refactor auth store with real implementation
    - Modify `src/frontend/src/stores/authStore.ts`
    - Replace placeholder implementation with real API calls via apiClient
    - Implement `login(username, password)`: call POST /api/v1/auth/login, store access token, set user state
    - Implement `logout()`: call POST /api/v1/auth/logout, clear all tokens and state, navigate to /login
    - Implement `refreshToken()`: call POST /api/v1/auth/refresh, update access token, return success/failure
    - Implement `initialize()`: attempt refresh on app mount, populate user from /me endpoint if successful
    - Implement `reAuthenticate(password)`: call POST /api/v1/auth/re-authenticate, return verified + signatureToken
    - Implement `clearSession(reason?)`: clear all state, set sessionExpired flag if reason provided
    - Add `activeCompanyId` and `activeCompanySlug` to state for tenant context
    - _Requirements: 1.3, 1.4, 2.5, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.3, 8.1, 8.2, 8.3, 8.4_

  - [x] 7.2 Write property test for logout state reset (Property 10)
    - **Property 10: Logout resets all application state regardless of API outcome**
    - **Validates: Requirements 6.1, 6.3, 6.4, 6.5**
    - Use fast-check to generate arbitrary initial auth states and API outcomes (success, network error, server error)
    - Assert: after logout, user is null, isAuthenticated is false, tokens cleared, tenant context null

- [x] 8. Frontend: Route guard component
  - [x] 8.1 Create RouteGuard component
    - Create `src/frontend/src/components/auth/RouteGuard.tsx`
    - Check `isAuthenticated` and `isLoading` from auth store
    - While loading: render a centered loading spinner
    - If unauthenticated: redirect to `/login?redirect=<encodeURIComponent(currentPath)>`
    - If authenticated: render children
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 8.2 Write property test for route guard redirect logic (Property 8)
    - **Property 8: Route guard redirects unauthenticated users with URL preservation**
    - **Validates: Requirements 4.1, 4.2**
    - Use fast-check to generate arbitrary URL paths
    - Assert: redirect URL is `/login?redirect=<encoded_path>` when unauthenticated

- [x] 9. Frontend: Login page
  - [x] 9.1 Create LoginPage component
    - Create `src/frontend/src/pages/LoginPage.tsx`
    - Use react-hook-form for form state management with validation rules (username required, password required)
    - Include username field with label, password field with label, submit button
    - Add password visibility toggle (eye/eye-off icon from lucide-react) with aria-label
    - Show loading spinner on submit button while request is in progress, disable button
    - Display error messages with aria-describedby and aria-live="polite" region
    - On success: redirect to `redirect` query param or "/" (default landing page)
    - If already authenticated: redirect away from login page to default landing
    - Support Enter key submission from any field
    - Ensure logical tab order and WCAG 2.1 AA color contrast
    - Use shadcn/ui components (Input, Button, Label, Card) for consistent styling
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 4.4, 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 9.2 Write property test for login form validation (Property 2)
    - **Property 2: Login form validation rejects empty fields**
    - **Validates: Requirements 1.2**
    - Use fast-check to generate pairs of (username, password) strings including empty/whitespace-only
    - Assert: validation error shown when either field is empty/whitespace, no error when both non-empty

  - [x] 9.3 Write property test for post-login redirect (Property 3)
    - **Property 3: Post-login redirect preserves requested URL**
    - **Validates: Requirements 1.4**
    - Use fast-check to generate valid URL paths
    - Assert: after successful login, navigation goes to the redirect param value or "/" when absent

  - [x] 9.4 Write property test for password visibility toggle (Property 12)
    - **Property 12: Password visibility toggle state**
    - **Validates: Requirements 9.2, 9.3**
    - Use fast-check to generate arbitrary positive integers N (number of toggles)
    - Assert: field type is "text" when N is odd, "password" when N is even

- [x] 10. Checkpoint - Frontend core components complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Frontend: Session timer hook
  - [x] 11.1 Create useSessionTimer hook
    - Create `src/frontend/src/hooks/useSessionTimer.ts`
    - Track token expiry from tokenStorage, trigger proactive refresh 60s before expiry
    - Track user activity (mouse, keyboard, touch events) for inactivity detection
    - Default inactivity timeout: 30 minutes, warning 60s before logout
    - Return: `showInactivityWarning`, `showExpiryWarning`, `remainingSeconds`, `dismissWarning()`, `extendSession()`
    - On inactivity timeout: call auth store logout
    - On token refresh failure: set sessionExpired state
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 11.2 Write unit tests for session timer hook
    - Test proactive refresh triggers at correct time using fake timers
    - Test inactivity warning appears after configured timeout
    - Test user activity resets the inactivity timer
    - Test extendSession dismisses warning and resets timer
    - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 12. Frontend: Re-authentication dialog
  - [x] 12.1 Create ReAuthDialog component
    - Create `src/frontend/src/components/auth/ReAuthDialog.tsx`
    - Modal overlay using shadcn/ui Dialog component
    - Display current username as read-only field
    - Password input field with submit button
    - Track consecutive failed attempts (max 5)
    - On success: call `onSuccess(signatureToken)` and close
    - On cancel: call `onCancel()` and close
    - On 5th failure: lock session via auth store, redirect to login
    - Show error messages for invalid password and network errors
    - Network errors do NOT count toward the 5-attempt limit
    - Accessible: aria-labelledby, aria-describedby, focus trap
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 12.2 Write property test for re-auth lockout (Property 11)
    - **Property 11: Re-auth lockout after 5 consecutive failures**
    - **Validates: Requirements 7.6**
    - Use fast-check to generate sequences of N failed attempts (1-10)
    - Assert: session locked and redirect on N >= 5, dialog remains open for N < 5

- [x] 13. Frontend: App integration and wiring
  - [x] 13.1 Wire RouteGuard and LoginPage into App.tsx
    - Modify `src/frontend/src/App.tsx`
    - Add `/login` route rendering LoginPage (outside RouteGuard)
    - Wrap all protected routes with RouteGuard component
    - Call `authStore.initialize()` in App mount (or a top-level provider)
    - Add session timer hook at the app level (inside RouteGuard)
    - Ensure setup wizard routes remain public (no auth required)
    - _Requirements: 4.1, 4.4, 4.5, 8.1, 8.4_

  - [x] 13.2 Update main.tsx if needed for auth initialization
    - Ensure BrowserRouter wraps everything (already does)
    - Verify no conflicts with existing routing setup
    - _Requirements: 8.1_

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Backend tasks (1-3) must be completed before frontend API integration tasks (6-7)
- Token storage (5) and API client (6) must be completed before auth store refactor (7)
- Property tests validate the 12 correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- The existing `authStore.ts` placeholder will be fully replaced in task 7.1
- All frontend code uses TypeScript; all backend code uses Python with FastAPI
