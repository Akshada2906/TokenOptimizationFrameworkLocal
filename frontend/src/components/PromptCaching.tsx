import { FormEvent, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  api,
  type ClaimReply,
  type PolicyReply,
  type PolicySession,
} from "../api";

type Mode = "question" | "claim";

const number = new Intl.NumberFormat();

function Usage({ result }: { result: PolicyReply | ClaimReply }) {
  return (
    <div className="metric-grid">
      <div className="metric"><span>Cached input reused</span><strong>{number.format(result.usage.cached_tokens)}</strong><small>tokens saved from resending</small></div>
      <div className="metric"><span>Fresh input</span><strong>{number.format(result.usage.new_input_tokens)}</strong><small>new tokens this request</small></div>
      <div className="metric"><span>Output</span><strong>{number.format(result.usage.output_tokens)}</strong><small>generated tokens</small></div>
      <div className="metric"><span>Latency</span><strong>{result.latency_s.toFixed(2)}s</strong><small>answer request only</small></div>
    </div>
  );
}

export default function PromptCaching() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [session, setSession] = useState<PolicySession | null>(null);
  const [mode, setMode] = useState<Mode>("question");
  const [input, setInput] = useState("");
  const [result, setResult] = useState<PolicyReply | ClaimReply | null>(null);
  const [busy, setBusy] = useState<"prepare" | "answer" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const prepare = async (demo: boolean) => {
    if (!demo && !file) return;
    setBusy("prepare");
    setError(null);
    setResult(null);
    try {
      setSession(demo ? await api.createDemoPolicy() : await api.createPolicy(file!));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!session || !input.trim()) return;
    setBusy("answer");
    setError(null);
    try {
      const reply = mode === "question"
        ? await api.askPolicy(session.session_id, input.trim())
        : await api.checkClaim(session.session_id, input.trim());
      setResult(reply);
      setSession(reply.session);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const claim = result && typeof result.answer !== "string" ? result.answer : null;
  const answer = result && typeof result.answer === "string" ? result.answer : null;

  return (
    <main className="policy-page">
      <header className="policy-header">
        <a className="back-link" href="/">← RepoGraph</a>
        <div><b>Expense Policy POC</b><span>Hybrid PixelPrompt + native visuals + Gemini cache</span></div>
      </header>

      <section className="policy-hero">
        <p className="eyebrow">100-PAGE MULTIMODAL POLICY</p>
        <h1>Ask the policy or classify a claim.</h1>
        <p>Prose and parsed tables become PixelPrompt images. Diagrams, receipts, and other visual regions stay as original PDF images. A page-ordered manifest keeps both streams aligned.</p>
      </section>

      <section className="policy-grid">
        <div className="card setup-card">
          <div><p className="eyebrow">STEP 1</p><h2>Prepare the policy cache</h2></div>
          <p className="muted">Use the supplied synthetic 100-page policy or upload another PDF. Initial preparation runs once; expired Gemini caches are recreated automatically from the saved images.</p>
          <div className="policy-actions">
            <button onClick={() => prepare(true)} disabled={busy !== null}>Use 100-page demo</button>
            <button className="secondary" onClick={() => fileInput.current?.click()} disabled={busy !== null}>Choose PDF</button>
            <input ref={fileInput} hidden type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          {file && <div className="selected-file">Selected: {file.name} <button className="small" onClick={() => prepare(false)} disabled={busy !== null}>Prepare upload</button></div>}
          {busy === "prepare" && <div className="cache-progress">Parsing 100 pages, rendering ordered images, and creating the cache…</div>}
          {session && (
            <div className="cache-ready">
              <b>Cache ready · {session.pages} pages · {number.format(session.cache_context_tokens)} context tokens</b>
              <span>{session.text_images} text · {session.table_images} table · {session.visual_images} original visual images · prepared in {session.preparation_s.toFixed(1)}s</span>
              <span>Automatic renewals: {session.cache_renewals}</span>
            </div>
          )}
        </div>

        <div className="card claim-card">
          <div><p className="eyebrow">STEP 2</p><h2>Test the cached policy</h2></div>
          <div className="mode-tabs">
            <button className={mode === "question" ? "active" : "secondary"} onClick={() => { setMode("question"); setResult(null); }}>Ask policy</button>
            <button className={mode === "claim" ? "active" : "secondary"} onClick={() => { setMode("claim"); setResult(null); }}>Classify claim</button>
          </div>
          <form onSubmit={submit}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={mode === "question" ? "Example: According to the workflow diagram, what happens after Finance validates a claim?" : "Example: INR 1,420 restaurant dinner for two; receipt shows tax included, business purpose and attendees are documented."}
              disabled={!session || busy !== null}
            />
            <button disabled={!session || !input.trim() || busy !== null}>{busy === "answer" ? "Checking…" : mode === "question" ? "Ask question" : "Classify claim"}</button>
          </form>
        </div>
      </section>

      {error && <div className="policy-error">{error}</div>}

      {result && (
        <section className="policy-result">
          <div className="card">
            {answer && <div className="policy-answer"><ReactMarkdown>{answer}</ReactMarkdown></div>}
            {claim && (
              <>
                <div className="result-heading"><div><p className="eyebrow">CLAIM DECISION</p><h2>{claim.classification}</h2></div><span className={`classification ${claim.classification.toLowerCase().replace(" ", "-")}`}>{claim.classification}</span></div>
                <p className="explanation">{claim.explanation}</p>
                <ul>{claim.reasoning_summary.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                {!!claim.policy_references.length && <div className="refs">{claim.policy_references.map((ref) => <span key={ref}>{ref}</span>)}</div>}
                {!!claim.evidence_gaps.length && <p className="evidence-gaps"><b>Evidence needed:</b> {claim.evidence_gaps.join("; ")}</p>}
              </>
            )}
          </div>
          <div className="card"><p className="eyebrow">CACHE MEASUREMENT</p><Usage result={result} /></div>
        </section>
      )}
    </main>
  );
}
