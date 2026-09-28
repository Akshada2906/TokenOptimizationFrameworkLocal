import { useState } from "react";
import Landing from "./components/Landing";
import Workspace from "./components/Workspace";
import PolicyCache from "./components/PolicyCache";

const fromUrl = () => new URLSearchParams(window.location.search).get("session");

export default function App() {
  if (window.location.pathname === "/policy-cache") return <PolicyCache />;
  const [sessionId, setSessionIdState] = useState<string | null>(fromUrl());
  const setSessionId = (id: string | null) => {
    setSessionIdState(id);
    window.history.replaceState(null, "", id ? `?session=${id}` : window.location.pathname);
  };
  return sessionId ? (
    <Workspace sessionId={sessionId} onExit={() => setSessionId(null)} />
  ) : (
    <Landing onReady={setSessionId} />
  );
}
