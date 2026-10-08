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
  const asText = images.filter((i) => i.source === "text");
  images = images.filter((i) => i.source !== "text");
  const graph = images.filter((i) => i.source === "grounding").length;
  const code = images.filter((i) => i.source === "code");
  const codeFiles = new Set(code.flatMap((i) => i.files ?? (i.file ? [i.file] : []))).size;
  const [showPickedImages, setShowPickedImages] = useState(false);

  return (
    <div className="tokens">
      {images.length > 0 && <div className="compare-line">
        <span><b>{fmt(s.image_tokens)}</b> image tokens</span>
        <span className="vs">vs</span>
        <span><b>{fmt(s.text_tokens)}</b> as text</span>
        <span className={diff >= 0 ? "good badge" : "bad badge"}>
          {diff >= 0 ? `${pct}% fewer tokens` : `${pct}% more tokens`}
        </span>
      </div>}
      <div className="chips">
        <span className="chip">image tokens: <b>{fmt(s.image_tokens)}</b></span>
        <span className="chip" title="The text contained in these images, if it had been sent as plain text">text tokens (as text): <b>{fmt(s.text_tokens)}</b></span>
        {(s.sent_as_text_tokens ?? 0) > 0 && (
          <span className="chip">sent as text: <b>{fmt(s.sent_as_text_tokens ?? 0)}</b></span>
        )}
        <span className="chip">output tokens: <b>{fmt(s.output_tokens)}</b></span>
        <span className="chip">images used: <b>{images.length}</b></span>
      </div>
      <div className="parts">
        {graph} graph/docs pages · {code.length} code images from {codeFiles} files
      </div>
      {asText.length > 0 && (
        <div className="text-note">
          <b>Sent as plain text, not images</b>, because the text cost fewer tokens than the image:
          <ul>
            {asText.map((t, i) => (
              <li key={i}>
                {t.file ?? t.title} — <b>{fmt(t.text_tokens ?? 0)}</b> text tokens vs {fmt(t.image_tokens_avoided ?? 0)} image tokens
              </li>
            ))}
          </ul>
        </div>
      )}
      {images.length > 0 && (
        <div className="picked">
          <div className="picked-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Images sent to the model</span>
            <button 
              onClick={() => setShowPickedImages(!showPickedImages)}
              style={{
                fontSize: '11px',
                padding: '2px 8px',
                background: 'transparent',
                border: '1px solid var(--border)',
                color: 'var(--text)',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              {showPickedImages ? 'Hide Images' : 'Show Images'}
            </button>
          </div>
          {showPickedImages && (
            <div className="picked-grid">
              {images.map((im, i) => {
                const url = api.contextImageUrl(sessionId, im.name);
                const label = im.files ? im.files.join(", ") : im.file ?? im.title;
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
          )}
        </div>
      )}
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  const [showImages, setShowImages] = useState(false);
  // Simple check for markdown images
  const hasImages = content.includes("![");

  return (
    <div className="msg-content">
      {hasImages && (
        <button 
          onClick={() => setShowImages(!showImages)} 
          style={{ 
            marginBottom: '8px', 
            fontSize: '12px', 
            padding: '4px 8px', 
            borderRadius: '4px',
            background: 'var(--panel-2)',
            border: '1px solid var(--border)',
            color: 'var(--text)'
          }}
        >
          {showImages ? "Hide Generated Images" : "Show Generated Images"}
        </button>
      )}
      <ReactMarkdown
        components={{
          img: ({ node, ...props }) => {
            if (!showImages) return null;
            return <img {...props} style={{ maxWidth: '100%', borderRadius: '4px', marginTop: '8px' }} />;
          }
        }}
      >
        {content}
      </ReactMarkdown>
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
            {m.role === "assistant" ? (
              <MessageContent content={m.content} />
            ) : (
              m.content
            )}
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
