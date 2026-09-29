import { FormEvent, useRef, useState } from "react";
import { api, PolicyCacheSession, PolicyClaimReply } from "./api";
import "./rationale.css";

export default function App() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [session, setSession] = useState<PolicyCacheSession | null>(null);
  const [claim, setClaim] = useState("");
  const [reply, setReply] = useState<PolicyClaimReply | null>(null);
  const [busy, setBusy] = useState<"upload" | "claim" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function createCache() {
    if (!file) return;
    setBusy("upload"); setError(null); setReply(null);
    try { setSession(await api.createPolicyCache(file)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(null); }
  }
  async function submitClaim(event: FormEvent) {
    event.preventDefault();
    if (!session || !claim.trim()) return;
    setBusy("claim"); setError(null);
    try { setReply(await api.checkClaim(session.session_id, claim)); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(null); }
  }

  return <main>
    <header><div><strong>Expense Policy Review</strong></div></header>
    <section className="hero"><p className="eyebrow">ONE POLICY · MANY CLAIMS</p><h1>Expense Claim Review</h1></section>
    <section className="setup">
      <article className="card"><h2>1. Create policy cache</h2><input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => { setFile(event.target.files?.[0] ?? null); setSession(null); setReply(null); }} /><button className="secondary" onClick={() => input.current?.click()} disabled={busy !== null}>Choose policy PDF</button><div className="file-name">{file?.name ?? "No PDF selected"}</div><button onClick={createCache} disabled={!file || busy !== null}>{busy === "upload" ? "Creating cache…" : "Create cache"}</button>{session && <div className="ready"><b>Cache ready</b><span>{session.source_name} · {session.pages} pages</span><span>{session.policy_tokens.toLocaleString()} policy tokens · {session.cache_context_tokens.toLocaleString()} cached tokens</span><span>{session.model} · {Math.round(session.ttl_seconds / 60)} minute TTL</span></div>}</article>
      <article className="card"><h2>2. Submit a claim</h2><form onSubmit={submitClaim}><textarea value={claim} onChange={(event) => setClaim(event.target.value)} disabled={!session || busy !== null} rows={8} placeholder="Example: Round-trip business-class flight from New York to London…" /><button disabled={!session || !claim.trim() || busy !== null}>{busy === "claim" ? "Checking claim…" : "Check cached policy"}</button></form></article>
    </section>
    {error && <div className="error">{error}</div>}
    {reply && <section className="results">
      <article className="card"><div className="result-header"><div><p className="eyebrow">POLICY DECISION</p><h2>{reply.answer.classification}</h2></div><b className={`badge ${reply.answer.classification.toLowerCase().replace(/ /g, "-")}`}>{reply.answer.classification}</b></div><p className="explanation">{reply.answer.explanation}</p>{(reply.answer.reasoning_summary?.length ?? 0) > 0 && <section className="rationale"><b>Decision rationale</b><ul>{reply.answer.reasoning_summary.map((item) => <li key={item}>{item}</li>)}</ul></section>}{(reply.answer.evidence_gaps?.length ?? 0) > 0 && <section className="rationale"><b>Additional information needed</b><ul>{reply.answer.evidence_gaps.map((item) => <li key={item}>{item}</li>)}</ul></section>}<div className="references">{reply.answer.policy_references.map((item) => <span key={item}>{item}</span>)}</div></article>
      <div className="metrics"><Metric label="Cached policy tokens" value={reply.usage.cached_tokens} note="Gemini reused these" /><Metric label="New input tokens" value={reply.usage.new_input_tokens} note="Claim-specific context" /><Metric label="Output tokens" value={reply.usage.output_tokens} note={`${reply.latency_s}s response`} /><Metric label="Logical prompt tokens" value={reply.usage.prompt_tokens} note="Full policy + claim" /></div>
    </section>}
  </main>;
}

function Metric({ label, value, note }: { label: string; value: number; note: string }) { return <article className="card metric"><span>{label}</span><strong>{value.toLocaleString()}</strong><small>{note}</small></article>; }
