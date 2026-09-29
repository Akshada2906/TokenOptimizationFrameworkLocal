export interface PolicyCacheSession {
  session_id: string; source_name: string; pages: number; extracted_characters: number;
  policy_tokens: number; cache_context_tokens: number; model: string; ttl_seconds: number;
  expires_at: number; claims_processed: number;
}
export interface PolicyClaimReply {
  answer: {
    classification: "Compliant" | "Non-compliant" | "Needs review";
    explanation: string;
    policy_references: string[];
    reasoning_summary: string[];
    evidence_gaps: string[];
  };
  usage: { prompt_tokens: number; cached_tokens: number; new_input_tokens: number; output_tokens: number };
  latency_s: number;
  session: PolicyCacheSession;
}
async function json<T>(response: Response): Promise<T> {
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || response.statusText); }
  return response.json();
}
export const api = {
  createPolicyCache(file: File) { const form = new FormData(); form.append("file", file); return fetch("/api/prompt-caching/policies", { method: "POST", body: form }).then(json<PolicyCacheSession>); },
  checkClaim(id: string, claim: string) { return fetch(`/api/prompt-caching/policies/${encodeURIComponent(id)}/claims`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ claim }) }).then(json<PolicyClaimReply>); },
};
