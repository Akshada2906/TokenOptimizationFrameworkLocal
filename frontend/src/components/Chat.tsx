import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, ChatStats, UsedImage } from "../api";

interface Msg {
  role: "user" | "assistant";
  content: string;
  stats?: ChatStats;
  images?: UsedImage[];
  error?: boolean;
}

const fmt = (v: number) => v.toLocaleString();

function TokenBreakdown({ s, images, sessionId }: { s: ChatStats; images: UsedImage[]; sessionId: string }) {
  const diff = s.text_tokens - s.image_tokens;
  const pct = s.text_tokens ? Math.round((Math.abs(diff) / s.text_tokens) * 100) : 0;
  const graph = images.filter((i) => i.source === "grounding").length;
  const code = images.filter((i) => i.source === "code");
  const codeFiles = new Set(code.map((i) => i.file)).size;
  const fresh = images.filter((i) => i.source === "file").length;
  return (
    <div className="tokens">
      <div className="compare-line">
        <span><b>{fmt(s.image_tokens)}</b> image tokens</span>
        <span className="vs">vs</span>
        <span><b>{fmt(s.text_tokens)}</b> as text</span>
        <span className={diff >= 0 ? "good badge" : "bad badge"}>
          {diff >= 0 ? `${pct}% fewer tokens` : `${pct}% more tokens`}
        </span>
      </div>
      <div className="chips">
        <span className="chip">image tokens: <b>{fmt(s.image_tokens)}</b></span>
        <span className="chip" title="The text contained in these images, if it had been sent as plain text">text tokens (as text): <b>{fmt(s.text_tokens)}</b></span>
        <span className="chip">output tokens: <b>{fmt(s.output_tokens)}</b></span>
        <span className="chip">images used: <b>{images.length}</b></span>
      </div>
      <div className="parts">
        {graph} graph/docs pages · {code.length} code images from {codeFiles} files
        {fresh > 0 && ` · ${fresh} fresh file pages`}
      </div>
      {images.length > 0 && (
        <div className="picked">
          <div className="picked-title">Images sent to the model</div>
          <div className="picked-grid">
            {images.map((im, i) => {
              const url = api.contextImageUrl(sessionId, im.name);
              const label = im.file ?? im.title;
              return (
                <a key={i} className="picked-item" href={url} target="_blank" rel="noreferrer" title={im.reason}>
                  <img src={url} alt={label} loading="lazy" />
                  <span className="picked-name">
                    {label}
                    {im.pages && im.pages > 1 ? ` (${im.page}/${im.pages})` : ""}
                  </span>
                  {im.reason && <span className="picked-reason">{im.reason}</span>}
                </a>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Chat({ sessionId, openFile }: { sessionId: string; openFile: string | null }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const r = await api.chat(sessionId, text, openFile);
      setMsgs((m) => [...m, { role: "assistant", content: r.answer, stats: r.stats, images: r.images_used }]);
    } catch (e) {
      setMsgs((m) => [...m, { role: "assistant", content: (e as Error).message, error: true }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pane chat">
      <div className="pane-title">
        Assistant {openFile && <span className="muted">· open: {openFile}</span>}
      </div>
      <div className="messages">
        {msgs.length === 0 && (
          <div className="empty">
            Ask about the architecture ("what calls this function?") or open a file and ask about
            it ("any bugs here?").
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role} ${m.error ? "err" : ""}`}>
            {m.role === "assistant" ? <ReactMarkdown>{m.content}</ReactMarkdown> : m.content}
            {m.stats && <TokenBreakdown s={m.stats} images={m.images ?? []} sessionId={sessionId} />}
          </div>
        ))}
        {busy && <div className="msg assistant thinking">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this repo…"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
