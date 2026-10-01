import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken, setUnauthorizedHandler } from "./api";
import type { AuthUser } from "./types";

interface AuthState {
  user: AuthUser | null;
  loading: boolean; // true while validating a stored token on first load
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // A 401 anywhere (expired/cleared token) drops us back to the login screen.
    setUnauthorizedHandler(() => setUser(null));
    (async () => {
      if (getToken()) {
        try {
          setUser(await api.me());
        } catch {
          // Invalid token -- request() already cleared it; just stay logged out.
        }
      }
      setLoading(false);
    })();
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = async (username: string, password: string) => {
    setUser((await api.login(username, password)).user);
  };
  const register = async (username: string, password: string) => {
    setUser((await api.register(username, password)).user);
  };
  const logout = async () => {
    await api.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
