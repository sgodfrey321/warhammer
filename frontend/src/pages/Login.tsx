import { useState } from "react";
import { ApiError } from "../api";
import { useAuth } from "../AuthContext";

function describeError(err: unknown, mode: "login" | "register"): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return "Can't reach the server — is the backend running? (restart dev.py after code changes)";
    if (err.status === 401) return "Invalid username or password.";
    if (err.status === 409) return "That username is already taken.";
    if (err.status === 404) return "Server is missing the auth routes — restart the backend (dev.py) to pick them up.";
    if (err.status === 422) return "Username and password are both required.";
    return `${mode === "login" ? "Sign-in" : "Registration"} failed (${err.status}).`;
  }
  return `${mode === "login" ? "Sign-in" : "Registration"} failed.`;
}

export function Login() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(username.trim(), password);
      else await register(username.trim(), password);
    } catch (err) {
      setError(describeError(err, mode));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={handleSubmit}>
        <h1>Warhammer Manager</h1>
        <p className="muted">{mode === "login" ? "Sign in to your account" : "Create an account"}</p>

        <label className="auth-field">
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus required />
        </label>
        <label className="auth-field">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <p className="error">{error}</p>}

        <button type="submit" disabled={busy || !username.trim() || !password}>
          {busy ? "…" : mode === "login" ? "Sign in" : "Register"}
        </button>

        <p className="muted auth-switch">
          {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>
      </form>
    </div>
  );
}
