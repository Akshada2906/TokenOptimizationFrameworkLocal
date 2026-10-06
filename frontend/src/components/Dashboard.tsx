import { useEffect, useState } from "react";
import { api, SessionStatus } from "../api";

export default function Dashboard({ onSelectSession }: { onSelectSession: (sid: string) => void }) {
  const [sessions, setSessions] = useState<SessionStatus[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getSessions().then((data) => {
      setSessions(data);
      setLoading(false);
    }).catch(e => {
      console.error(e);
      setLoading(false);
    });
  }, []);

  const formatSource = (source: string) => {
    if (!source || source === "upload") return "Local Folder Upload";
    if (source.includes("/") || source.includes("\\")) {
      return source.split(/[/\\]/).filter(Boolean).pop() || source;
    }
    return source;
  };

  const handleDelete = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      setSessions(sessions.filter(s => s.session_id !== sid));
    } catch (e) {
      console.error(e);
      alert("Failed to delete session");
    }
  };

  return (
    <div className="landing" style={{ alignItems: "flex-start", overflow: "auto" }}>
      <div className="landing-card" style={{ width: "min(800px, 100%)", marginTop: "40px" }}>
        <h1 style={{ marginBottom: "0" }}>Dashboard</h1>
        <p className="tagline" style={{ marginTop: "4px" }}>Live Active Uploads</p>
        
        {loading ? (
          <p className="muted">Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="muted">No active sessions. Upload a repo in PixelPrompt first!</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginTop: "8px" }}>
            {sessions.map(s => (
              <div key={s.session_id} style={{
                background: "var(--panel-2)", 
                padding: "20px", 
                borderRadius: "12px",
                border: "1px solid var(--border)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)"
              }}>
                <div>
                  <div style={{ fontSize: "18px", fontWeight: "600", color: "var(--text)" }}>
                    {formatSource(s.source)}
                  </div>
                  <div className="muted" style={{ fontSize: "13px", marginTop: "6px", display: "flex", gap: "12px" }}>
                    <span>
                      Status: <span style={{ color: s.status === 'ready' ? 'var(--good)' : 'var(--text)', fontWeight: "500" }}>{s.status}</span>
                    </span>
                    {s.stats?.extracted && (
                      <span>
                        • <strong style={{ color: "var(--text)" }}>{s.stats.extracted}</strong> files
                      </span>
                    )}
                    {s.stats?.nodes !== undefined && (
                      <span>
                        • <strong style={{ color: "var(--text)" }}>{s.stats.nodes}</strong> nodes
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <button 
                    onClick={() => onSelectSession(s.session_id)}
                    style={{ padding: "8px 16px" }}
                  >
                    View Workspace
                  </button>
                  <button 
                    onClick={() => handleDelete(s.session_id)}
                    style={{ padding: "8px 16px", background: "transparent", color: "var(--bad)", border: "1px solid var(--border)" }}
                    onMouseOver={(e) => {
                      e.currentTarget.style.background = "#2a1519";
                      e.currentTarget.style.borderColor = "var(--bad)";
                    }}
                    onMouseOut={(e) => {
                      e.currentTarget.style.background = "transparent";
                      e.currentTarget.style.borderColor = "var(--border)";
                    }}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
