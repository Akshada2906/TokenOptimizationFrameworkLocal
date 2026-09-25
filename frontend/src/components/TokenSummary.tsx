import { Stats } from "../api";

const n = (v: unknown) => (typeof v === "number" ? v.toLocaleString() : "–");

/** Session-level facts only. Images and token counts are shown per answer, for what was actually sent. */
export default function TokenSummary({ stats }: { stats?: Stats }) {
  if (!stats) return null;
  return (
    <div className="summary">
      <span>{n(stats.graph_nodes)} nodes</span>
      <span>{n(stats.code_files)} files indexed</span>
    </div>
  );
}
