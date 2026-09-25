import { useEffect, useRef, useState } from "react";
import { api } from "../api";

const STAGES = ["cloning", "analyzing", "rendering", "ready"];
const LABELS: Record<string, string> = {
  cloning: "Cloning repository",
  analyzing: "Building dependency graph",
  rendering: "Rendering PixelPrompt images",
  ready: "Ready",
};

export default function Landing({ onReady }: { onReady: (id: string) => void }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(async () => {
      try {
        const s = await api.status(pending);
        setStage(s.status);
        if (s.status === "ready") {
          clearInterval(timer);
          onReady(pending);
        } else if (s.status === "error") {
          clearInterval(timer);
          setError(s.error ?? "Something went wrong");
          setPending(null);
          setStage(null);
        }
      } catch (e) {
        clearInterval(timer);
        setError((e as Error).message);
        setPending(null);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [pending, onReady]);

  const start = async (fn: () => Promise<{ session_id: string }>) => {
    setError(null);
    setStage("queued");
    try {
      setPending((await fn()).session_id);
    } catch (e) {
      setError((e as Error).message);
      setStage(null);
    }
  };

  const busy = stage !== null;
  const current = stage ? STAGES.indexOf(stage) : -1;

  return (
    <div className="landing">
      <div className="landing-card">
        <h1>RepoGraph</h1>
        <p className="tagline">
          Chat with any codebase for a fraction of the tokens. Your repo is analyzed once into a
          dependency graph, then rendered as PixelPrompt images the assistant reads instead of raw
          source.
        </p>

        <form
          className="url-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (url.trim()) start(() => api.createFromUrl(url.trim()));
          }}
        >
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !url.trim()}>
            Analyze
          </button>
        </form>

        <div className="or">or</div>
        <button className="secondary" disabled={busy} onClick={() => folderInput.current?.click()}>
          Upload a folder
        </button>
        <input
          ref={folderInput}
          type="file"
          hidden
          // @ts-expect-error non-standard directory picker attribute
          webkitdirectory=""
          multiple
          onChange={(e) => e.target.files?.length && start(() => api.createFromFolder(e.target.files!))}
        />

        {error && <div className="error">{error}</div>}

        {busy && (
          <ol className="stepper">
            {STAGES.map((s, i) => (
              <li key={s} className={i < current ? "done" : i === current ? "active" : ""}>
                {LABELS[s]}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
