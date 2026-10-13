import { useEffect, useState } from "react";
import { del, get, post } from "./api";
import Dashboard from "./components/Dashboard";
import Login from "./components/Login";
import Logo from "./components/Logo";
import type { Me } from "./types";

export default function App() {
  const [user, setUser] = useState<Me | null | undefined>(undefined);   // undefined = still checking
  const [notice, setNotice] = useState<string>();

  useEffect(() => { get<Me>("/api/auth/me").then(setUser).catch(() => setUser(null)); }, []);
  if (user === undefined) return <div className="grid min-h-screen place-items-center"><Logo size={44} /></div>;
  if (!user) return <Login notice={notice} />;
  return <Dashboard user={user}
    onLogout={async () => { await post("/api/auth/logout", {}).catch(() => {}); setNotice("You have been signed out."); setUser(null); }}
    onDeleted={async () => { await del("/api/auth/me").catch(() => {}); setNotice("Your account and everything you searched for have been deleted."); setUser(null); }} />;
}
