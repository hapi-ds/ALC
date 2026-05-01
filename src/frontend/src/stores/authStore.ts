import { create } from "zustand";

interface User {
  id: number;
  username: string;
  email: string;
  roles: string[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  reAuthenticate: (password: string) => Promise<boolean>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,

  login: async (_username: string, _password: string) => {
    set({ isLoading: true });
    // Placeholder: will integrate with backend auth API
    set({
      user: { id: 1, username: "admin", email: "admin@local", roles: ["admin"] },
      isAuthenticated: true,
      isLoading: false,
    });
  },

  logout: () => {
    set({ user: null, isAuthenticated: false });
  },

  reAuthenticate: async (_password: string) => {
    // Placeholder: re-authentication for signature flows
    return true;
  },
}));
