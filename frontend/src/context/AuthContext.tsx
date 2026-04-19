import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { clearWebUiToken, getWebUiToken, setWebUiToken } from '@/lib/authStorage';

type AuthContextValue = {
  ready: boolean;
  needsLogin: boolean;
  token: string | null;
  login: (password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [needsLogin, setNeedsLogin] = useState(false);
  const [token, setToken] = useState<string | null>(() => getWebUiToken());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch('/api/auth/webui/status');
        const d = (await r.json()) as { webui_login_required?: boolean };
        if (!cancelled) setNeedsLogin(!!d.webui_login_required);
      } catch {
        if (!cancelled) setNeedsLogin(false);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (password: string) => {
    const r = await fetch('/api/auth/webui/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    if (!r.ok) {
      let msg = r.statusText;
      try {
        const j = (await r.json()) as { detail?: unknown };
        const d = j.detail;
        if (typeof d === 'string') msg = d;
        else if (Array.isArray(d))
          msg = d.map((x: { msg?: string }) => x.msg || '').filter(Boolean).join(' ');
      } catch {
        /* ignore */
      }
      throw new Error(msg);
    }
    const data = (await r.json()) as { access_token: string };
    setWebUiToken(data.access_token);
    setToken(data.access_token);
  }, []);

  const logout = useCallback(() => {
    clearWebUiToken();
    setToken(null);
  }, []);

  const value = useMemo(
    () => ({ ready, needsLogin, token, login, logout }),
    [ready, needsLogin, token, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
