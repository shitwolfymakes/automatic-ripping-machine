import { defineStore } from "pinia";
import { api, clearToken, getToken, setToken, setUnauthorizedHandler } from "../api/client";
import type {
  LoginRequest,
  LoginResponse,
  PasswordChangeRequest,
} from "../api/types";

interface AuthState {
  token: string | null;
  username: string | null;
  passwordMustChange: boolean;
  expiresAt: string | null;
}

export const useAuthStore = defineStore("auth", {
  state: (): AuthState => ({
    token: null,
    username: null,
    passwordMustChange: false,
    expiresAt: null,
  }),
  getters: {
    isAuthenticated: (s): boolean => s.token !== null,
  },
  actions: {
    hydrate() {
      this.token = getToken();
      // Wire the api client so a 401 anywhere resets the store. The router
      // guard then redirects to /login on its own pass.
      setUnauthorizedHandler(() => {
        this.reset();
      });
    },
    async login(req: LoginRequest): Promise<LoginResponse> {
      const resp = await api.post<LoginResponse>("/api/auth/login", req);
      setToken(resp.access_token);
      this.token = resp.access_token;
      this.username = req.username;
      this.passwordMustChange = resp.password_must_change;
      this.expiresAt = resp.expires_at;
      return resp;
    },
    async changePassword(req: PasswordChangeRequest): Promise<void> {
      await api.post<{ ok: boolean }>("/api/auth/password", req);
      this.passwordMustChange = false;
    },
    async logout(): Promise<void> {
      try {
        await api.post<{ ok: boolean }>("/api/auth/logout");
      } catch {
        // server is no-op anyway; ignore failures.
      }
      this.reset();
    },
    reset() {
      clearToken();
      this.token = null;
      this.username = null;
      this.passwordMustChange = false;
      this.expiresAt = null;
    },
  },
});
