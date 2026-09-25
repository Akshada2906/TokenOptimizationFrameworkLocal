import { Stats } from "../api";

const n = (v: unknown) => (typeof v === "number" ? v.toLocaleString() : "–");

/** Session-level comparison: grounding sent as images vs. the same content as text. */
export default function TokenSummary({ stats }: { stats?: Stats }) {
  if (!stats) return null;
  const img = stats.grounding_image_tokens;
  const txt = stats.grounding_text_tokens;
  const pct = stats.grounding_savings_pct;
  return (
    <div className="summary">
      <span>{n(stats.graph_nodes)} nodes</span>
      <span>{n(stats.images)} images</span>
      {img !== undefined && txt !== undefined && (
        <span className="pill" title="Tokens for the grounding context, sent as images vs. as raw text">
          Grounding: <b>{n(img)}</b> image tok vs <b>{n(txt)}</b> text tok
          {typeof pct === "number" && (
            <em className={pct >= 0 ? "good" : "bad"}> ({pct >= 0 ? "−" : "+"}{Math.abs(pct)}%)</em>
          )}
        </span>
      )}
    </div>
  );
}
