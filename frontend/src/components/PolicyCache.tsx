import { useRef, useState } from "react";
import { api, PolicyCacheSession, PolicyClaimReply } from "../api";

const usd = (value: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 4, maximumFractionDigits: 6 }).format(value);

export default function PolicyCache() {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [session, setSession] = useState<PolicyCacheSession | null>(null);
  const [claim, setClaim] = useState("");
  const [reply, setReply] = useState<PolicyClaimReply | null>(null);
  const [busy, setBusy] = useState<"upload" | "claim" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createCache = async () => {
    if (!file) return;
    setBusy("upload"); setError(null); setReply(null);
    try { setSession(await api.createPolicyCache(file)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };
  const submitClaim = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!session || !claim.trim()) return;
    setBusy("claim"); setError(null);
    try { setReply(await api.checkPolicyClaim(session.session_id, claim)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  return <main className="policy-page">
    <header className="policy-header">
      <a href="/" className="back-link">← RepoGraph</a>
      <div><strong>Expense Policy Cache POC</strong><span>Explicit Gemini prompt caching</span></div>
      <a className="pricing-link" href="https://ai.google.dev/gemini-api/docs/pricing" target="_blank" rel="noreferrer">Pricing source ↗</a>
    </header>
    <section className="policy-hero">
      <p className="eyebrow">ONE POLICY · MANY CLAIMS</p>
      <h1>Check an expense claim with cached policy context.</h1>
      <p>Upload a selectable-text expense-policy PDF once. Each claim then sends only its new details while Gemini reuses the cached policy.</p>
    </section>
    <section className="policy-grid">
      <article className="card setup-card">
        <h2>1. Create policy cache</h2>
        <p className="muted">The PDF is extracted server-side, counted, and cached with Gemini for one hour.</p>
        <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => { setFile(e.target.files?.[0] ?? null); setSession(null); setReply(null); }} />
        <button className="file-button secondary" onClick={() => input.current?.click()} disabled={busy !== null}>Choose policy PDF</button>
        <div className="selected-file">{file ? file.name : "No PDF selected"}</div>
        <button onClick={createCache} disabled={!file || busy !== null}>{busy === "upload" ? "Creating Gemini cache…" : "Create cache"}</button>
        {session && <div className="cache-ready">
          <b>Cache ready</b>
          <span>{session.source_name} · {session.pages} pages</span>
          <span>{session.policy_tokens.toLocaleString()} policy tokens · {session.cache_context_tokens.toLocaleString()} cached-context tokens</span>
          <span>Model: {session.model} · TTL: {Math.round(session.ttl_seconds / 60)} minutes</span>
        </div>}
      </article>
      <article className="card claim-card">
        <h2>2. Submit a claim</h2>
        <p className="muted">Only this claim is newly sent. The policy remains in Gemini’s explicit cache.</p>
        <form onSubmit={submitClaim}>
          <textarea value={claim} onChange={(e) => setClaim(e.target.value)} disabled={!session || busy !== null} placeholder="Example: Hotel in Chicago for two business nights…" rows={8} />
          <button disabled={!session || !claim.trim() || busy !== null}>{busy === "claim" ? "Checking claim…" : "Check cached policy"}</button>
        </form>
      </article>
    </section>
    {error && <div className="policy-error">{error}</div>}
    {reply && <section className="policy-result">
      <article className="card decision-card">
        <div className="result-heading"><div><p className="eyebrow">POLICY DECISION</p><h2>{reply.answer.classification}</h2></div><span className={`classification ${reply.answer.classification.toLowerCase().replace(/ /g, "-")}`}>{reply.answer.classification}</span></div>
        <p className="explanation">{reply.answer.explanation}</p>
        <div className="refs">{reply.answer.policy_references.map((reference) => <span key={reference}>{reference}</span>)}</div>
      </article>
      <div className="metric-grid">
        <Metric label="Cached policy tokens" value={reply.usage.cached_tokens.toLocaleString()} note="Gemini reused these" />
        <Metric label="New input tokens" value={reply.usage.new_input_tokens.toLocaleString()} note="Claim-specific context" />
        <Metric label="Output tokens" value={reply.usage.output_tokens.toLocaleString()} note={`${reply.latency_s}s response`} />
        <Metric label="Logical prompt tokens" value={reply.usage.prompt_tokens.toLocaleString()} note="Full policy + claim" />
      </div>
      <section className="cost-grid">
        <article className="card"><p className="eyebrow">THIS CLAIM</p><h3>{usd(reply.costs.this_claim.with_explicit_cache_usd)}</h3><p>with explicit cache</p><div className="cost-line"><span>No-cache equivalent</span><b>{usd(reply.costs.this_claim.without_cache_equivalent_usd)}</b></div><div className="cost-line savings"><span>Estimated saving</span><b>{usd(reply.costs.this_claim.savings_usd)}</b></div></article>
        <article className="card"><p className="eyebrow">SESSION TOTAL · {reply.costs.session.claims_after_this_one} CLAIM(S)</p><h3>{usd(reply.costs.session.net_savings_usd)}</h3><p>net saving after cache setup and one-hour storage</p><div className="cost-line"><span>Cache creation</span><b>{usd(reply.costs.session.cache_creation_usd)}</b></div><div className="cost-line"><span>TTL storage</span><b>{usd(reply.costs.session.cache_storage_for_ttl_usd)}</b></div><div className="cost-line"><span>No-cache equivalent</span><b>{usd(reply.costs.session.without_cache_equivalent_usd)}</b></div></article>
      </section>
      <p className="estimate-note">Cost is an estimate based on server-configured {reply.session.model} rates. “No-cache equivalent” is calculated from Gemini’s full logical prompt-token count; the UI does not make a duplicate non-cached model request.</p>
    </section>}
  </main>;
}

function Metric({ label, value, note }: { label: string; value: string; note: string }) {
  return <article className="card metric"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}
