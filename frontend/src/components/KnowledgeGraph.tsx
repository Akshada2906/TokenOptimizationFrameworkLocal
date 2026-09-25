import { api, GraphInfo } from "../api";

const kb = (n: number) => (n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`);

/** Shows the code-review-graph folder (name, location, files) and the interactive knowledge graph. */
export default function KnowledgeGraph({
  sessionId,
  info,
  onClose,
}: {
  sessionId: string;
  info: GraphInfo;
  onClose: () => void;
}) {
  const root = info.files.filter((f) => !f.path.includes("/"));
  const wiki = info.files.filter((f) => f.path.startsWith("wiki/"));
  const other = info.files.filter((f) => f.path.includes("/") && !f.path.startsWith("wiki/"));
  const link = (path: string) => api.graphFileUrl(sessionId, path);

  return (
    <div className="kg-backdrop" onClick={onClose}>
      <div className="kg" onClick={(e) => e.stopPropagation()}>
        <div className="kg-head">
          <div>
            <div className="kg-title">
              <span className="folder-icon">▸</span> {info.folder}/
            </div>
            <div className="kg-path" title={info.path ?? ""}>{info.path ?? "no graph folder"}</div>
          </div>
          <div className="kg-badges">
            <span className="pill"><b>{info.files.length}</b> files</span>
            <span className="pill"><b>{info.nodes.toLocaleString()}</b> nodes</span>
            <span className="pill"><b>{info.edges.toLocaleString()}</b> edges</span>
            <span className="pill">{info.generated ? "created by RepoGraph" : "already in the repo"}</span>
            <button className="secondary small" onClick={onClose}>Close</button>
          </div>
        </div>

        <div className="kg-body">
          <div className="kg-files">
            <div className="kg-section">Files in {info.folder}/ ({info.files.length})</div>
            {root.map((f) => (
              <a key={f.path} href={link(f.path)} target="_blank" rel="noreferrer" className="kg-file">
                <span>{f.path}</span>
                <em>{kb(f.size)}</em>
              </a>
            ))}
            {wiki.length > 0 && <div className="kg-section">wiki/ ({wiki.length} articles)</div>}
            {wiki.map((f) => (
              <a key={f.path} href={link(f.path)} target="_blank" rel="noreferrer" className="kg-file">
                <span>{f.path.replace("wiki/", "")}</span>
                <em>{kb(f.size)}</em>
              </a>
            ))}
            {other.map((f) => (
              <a key={f.path} href={link(f.path)} target="_blank" rel="noreferrer" className="kg-file">
                <span>{f.path}</span>
                <em>{kb(f.size)}</em>
              </a>
            ))}
          </div>

          <div className="kg-graph">
            {info.has_html ? (
              <iframe title="Knowledge graph" src={api.graphHtmlUrl(sessionId)} sandbox="allow-scripts" />
            ) : (
              <div className="empty">This repository's graph has no interactive view (graph.html).</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
