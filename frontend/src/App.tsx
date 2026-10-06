import { useState } from "react";
import Landing from "./components/Landing";
import Workspace from "./components/Workspace";
import PromptCaching from "./components/PromptCaching";
import Dashboard from "./components/Dashboard";

const fromUrl = () => new URLSearchParams(window.location.search).get("session");

export default function App() {
  const [sessionId, setSessionIdState] = useState<string | null>(fromUrl());
  const [activeTab, setActiveTab] = useState<"dashboard" | "pixelprompt" | "prompt_caching">(
    fromUrl() ? "pixelprompt" : "dashboard"
  );
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const setSessionId = (id: string | null) => {
    setSessionIdState(id);
    window.history.replaceState(null, "", id ? `?session=${id}` : window.location.pathname);
  };

  const renderContent = () => {
    if (activeTab === "dashboard") {
      return (
        <Dashboard 
          onSelectSession={(sid) => {
            setSessionId(sid);
            setActiveTab("pixelprompt");
          }} 
        />
      );
    }
    if (activeTab === "prompt_caching") {
      return <PromptCaching />;
    }
    
    return sessionId ? (
      <Workspace sessionId={sessionId} onExit={() => setSessionId(null)} />
    ) : (
      <Landing onReady={setSessionId} />
    );
  };

  return (
    <div className="app-layout">
      {isSidebarOpen ? (
        <nav className="sidebar">
          <div className="brand" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Token Optimization</span>
            <button className="collapse-btn" onClick={() => setIsSidebarOpen(false)} title="Collapse Sidebar">
              ◀
            </button>
          </div>
          <button 
            className={`nav-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            Dashboard
          </button>
          <button 
            className={`nav-btn ${activeTab === 'pixelprompt' ? 'active' : ''}`}
            onClick={() => setActiveTab('pixelprompt')}
          >
            PixelPrompt
          </button>
          <button 
            className={`nav-btn ${activeTab === 'prompt_caching' ? 'active' : ''}`}
            onClick={() => setActiveTab('prompt_caching')}
          >
            Prompt Caching
          </button>
        </nav>
      ) : (
        <div className="sidebar-collapsed">
          <button className="expand-btn" onClick={() => setIsSidebarOpen(true)} title="Expand Sidebar">
            ▶
          </button>
        </div>
      )}
      <main className="main-content" style={{ position: "relative" }}>
        {renderContent()}
      </main>
    </div>
  );
}
