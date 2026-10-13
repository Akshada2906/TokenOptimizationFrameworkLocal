import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { canPickFolder, pickProjectFolder, saveGraphInto } from "../folderAccess";

const STAGES = ["cloning", "analyzing", "rendering", "saving", "ready"];
const LABELS: Record<string, string> = {
  cloning: "Cloning repository",
  analyzing: "Building dependency graph",
  rendering: "Rendering PixelPrompt images",
  saving: "Saving code-review-graph into your folder",
  ready: "Ready",
};

export default function Landing({ onReady }: { onReady: (id: string) => void }) {
  const [url, setUrl] = useState("");
  const [localPath, setLocalPath] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<string | null>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<string | null>(null);
  const dirHandle = useRef<any>(null);

  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(async () => {
      try {
        const s = await api.status(pending);
        setStage(s.status);
        if (s.status === "ready") {
          clearInterval(timer);
          if (dirHandle.current) {
            setStage("saving");
            try {
              await saveGraphInto(dirHandle.current, pending);
            } catch (e) {
              console.warn("Could not save code-review-graph into the folder", e);
            }
          }
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

  const pickFolder = async () => {
    setError(null);
    try {
      const { dir, files } = await pickProjectFolder();
      if (!files.length) return setError("No source code files found in that folder.");
      dirHandle.current = dir;
      await start(() => api.createFromFiles(files));
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    }
  };

  const busy = stage !== null;
  const steps = STAGES.filter((s) => s !== "saving" || dirHandle.current);
  const current = stage ? steps.indexOf(stage) : -1;

  return (
    <div className="landing">
      <div className="landing-card">
        <h1>RepoGraph</h1>
        <p className="tagline">
          Chat with any codebase for a fraction of the tokens. Your repo is analyzed once into a
          dependency graph, then rendered as PixelPrompt images the assistant reads instead of raw
          source.
        </p>
        <a className="policy-poc-link" href="/prompt-caching">
          Open the expense-policy prompt-caching POC →
        </a>

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

        {canPickFolder() && (
          <>
            <div className="or">or pick a project folder (code-review-graph/ is saved inside it)</div>
            <button disabled={busy} onClick={pickFolder}>
              Pick project folder
            </button>
          </>
        )}

        <div className="or">or a folder on this machine (code-review-graph/ is created inside it)</div>
        <form
          className="url-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (localPath.trim()) start(() => api.createFromLocal(localPath.trim()));
          }}
        >
          <input
            value={localPath}
            onChange={(e) => setLocalPath(e.target.value)}
            placeholder="/Users/you/projects/my-repo"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !localPath.trim()}>
            Analyze
          </button>
        </form>

        <div className="or">or upload a copy of a folder (graph is not saved to your disk)</div>
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
            {steps.map((s, i) => (
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
