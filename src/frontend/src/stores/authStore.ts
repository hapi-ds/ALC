import { create } from "zustand";
import { apiClient, ApiError } from "@/lib/apiClient";
import {
  setAccessToken,
  clearAccessToken,
} from "@/lib/tokenStorage";
import { setAuthStoreAccessor, setClearSessionFn } from "@/lib/apiClient";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  roles: string[];
}

interface LoginResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

interface RefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

interface ReAuthResponse {
  verified: boolean;
  signature_token: string;
  expires_in: number;
}

interface MeResponse {
  id: number;
  username: string;
  email: string;
  full_name: string;
  roles: string[];
  companies: Array<{
    company_id: number;
    company_slug: string;
    role: string;
  }>;
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  sessionExpired: boolean;
  activeCompanyId: number | null;
  activeCompanySlug: string | null;

  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  initialize: () => Promise<void>;
  reAuthenticate: (
    password: string,
  ) => Promise<{ verified: boolean; signatureToken?: string }>;
  clearSession: (reason?: string) => void;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  sessionExpired: false,
  activeCompanyId: null,
  activeCompanySlug: null,

  login: async (username: string, password: string) => {
    set({ isLoading: true });
    try {
      const data = await apiClient.post<LoginResponse>(
        "/api/v1/auth/login",
        { username, password },
        { skipAuth: true },
      );

      setAccessToken(data.access_token);

      // Set active company from user's first company if available
      set({
        user: data.user,
        isAuthenticated: true,
        isLoading: false,
        sessionExpired: false,
      });
    } catch (error) {
      set({ isLoading: false });
      throw error;
    }
  },

  logout: async () => {
    // Always clear local state regardless of API outcome (fail-open)
    try {
      await apiClient.post("/api/v1/auth/logout");
    } catch {
      // Intentionally swallowed — fail-open for logout
    } finally {
      clearAccessToken();
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        sessionExpired: false,
        activeCompanyId: null,
        activeCompanySlug: null,
      });
      window.location.href = "/login";
    }
  },

  refreshToken: async () => {
    try {
      const data = await apiClient.post<RefreshResponse>(
        "/api/v1/auth/refresh",
        undefined,
        { skipAuth: true },
      );

      setAccessToken(data.access_token);
      return true;
    } catch {
      return false;
    }
  },

  initialize: async () => {
    set({ isLoading: true });
    try {
      // Attempt to refresh the token (refresh token is in httpOnly cookie)
      const refreshed = await get().refreshToken();

      if (refreshed) {
        // Populate user from /me endpoint
        const me = await apiClient.get<MeResponse>("/api/v1/auth/me");

        // Set active company from first company membership if available
        const firstCompany = me.companies?.[0];

        set({
          user: {
            id: me.id,
            username: me.username,
            email: me.email,
            full_name: me.full_name,
            roles: me.roles,
          },
          isAuthenticated: true,
          isLoading: false,
          sessionExpired: false,
          activeCompanyId: firstCompany?.company_id ?? null,
          activeCompanySlug: firstCompany?.company_slug ?? null,
        });
      } else {
        // No valid session — set unauthenticated without error
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        });
      }
    } catch {
      // Initialization failed — set unauthenticated without error
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },

  reAuthenticate: async (password: string) => {
    try {
      const data = await apiClient.post<ReAuthResponse>(
        "/api/v1/auth/re-authenticate",
        { password },
      );

      return {
        verified: data.verified,
        signatureToken: data.signature_token,
      };
    } catch (error) {
      // ApiError means the server responded (e.g., 401 invalid password)
      // Non-ApiError means a network/connection failure — re-throw so callers
      // can distinguish and avoid counting it as a failed auth attempt.
      if (error instanceof ApiError) {
        return { verified: false };
      }
      throw error;
    }
  },

  clearSession: (reason?: string) => {
    clearAccessToken();
    set({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      sessionExpired: !!reason,
      activeCompanyId: null,
      activeCompanySlug: null,
    });
  },
}));

// ---------------------------------------------------------------------------
// Register auth store accessor with apiClient (avoids circular imports)
// ---------------------------------------------------------------------------

setAuthStoreAccessor(() => {
  const state = useAuthStore.getState();
  return {
    userId: state.user?.id ?? null,
    companyId: state.activeCompanyId,
  };
});

setClearSessionFn(() => {
  useAuthStore.getState().clearSession("session_expired");
});
