import { useEffect, useState } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { api, GraphInfo, SessionStatus, TreeNode } from "../api";
import Chat from "./Chat";
import CodeViewer from "./CodeViewer";
import FileTree from "./FileTree";
import KnowledgeGraph from "./KnowledgeGraph";
import TokenSummary from "./TokenSummary";

export default function Workspace({ sessionId, onExit }: { sessionId: string; onExit: () => void }) {
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [graph, setGraph] = useState<GraphInfo | null>(null);
  const [showGraph, setShowGraph] = useState(false);

  useEffect(() => {
    api.tree(sessionId).then(setTree).catch(() => setTree([]));
    api.status(sessionId).then(setStatus);
    api.graph(sessionId).then(setGraph).catch(() => setGraph(null));
  }, [sessionId]);

  const openFile = async (path: string) => {
    setOpenPath(path);
    setFileError(null);
    try {
      setContent((await api.file(sessionId, path)).content);
    } catch (e) {
      setContent("");
      setFileError((e as Error).message);
    }
  };

  return (
    <div className="workspace">
      <header>
        <strong>RepoGraph</strong>
        <TokenSummary stats={status?.stats} />
        <div className="spacer" />
        {graph && (
          <button className="secondary small" onClick={() => setShowGraph(true)}>
            Knowledge graph · {graph.folder}/ · {graph.files.length} files
          </button>
        )}
        <button className="secondary small" onClick={onExit}>
          New repo
        </button>
      </header>

      <PanelGroup direction="horizontal" className="panes">
        <Panel defaultSize={20} minSize={12}>
          <FileTree nodes={tree} selected={openPath} onSelect={openFile} />
        </Panel>
        <PanelResizeHandle className="handle" />
        <Panel defaultSize={42} minSize={20}>
          <CodeViewer path={openPath} content={content} error={fileError} sessionId={sessionId} />
        </Panel>
        <PanelResizeHandle className="handle" />
        <Panel defaultSize={38} minSize={22}>
          <Chat sessionId={sessionId} openFile={openPath} />
        </Panel>
      </PanelGroup>

      {showGraph && graph && (
        <KnowledgeGraph sessionId={sessionId} info={graph} onClose={() => setShowGraph(false)} />
      )}
    </div>
  );
}
