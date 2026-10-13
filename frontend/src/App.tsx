import { useState } from "react";
import Landing from "./components/Landing";
import Workspace from "./components/Workspace";
import PromptCaching from "./components/PromptCaching";

const fromUrl = () => new URLSearchParams(window.location.search).get("session");

export default function App() {
  const [sessionId, setSessionIdState] = useState<string | null>(fromUrl());
  const setSessionId = (id: string | null) => {
    setSessionIdState(id);
    window.history.replaceState(null, "", id ? `?session=${id}` : window.location.pathname);
  };
  if (window.location.pathname.startsWith("/prompt-caching")) return <PromptCaching />;
  return sessionId ? (
    <Workspace sessionId={sessionId} onExit={() => setSessionId(null)} />
  ) : (
    <Landing onReady={setSessionId} />
  );
}
