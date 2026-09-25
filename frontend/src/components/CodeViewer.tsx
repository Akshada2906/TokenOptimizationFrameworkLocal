import Editor from "@monaco-editor/react";

const LANGS: Record<string, string> = {
  py: "python", js: "javascript", jsx: "javascript", ts: "typescript", tsx: "typescript",
  json: "json", md: "markdown", java: "java", go: "go", rs: "rust", rb: "ruby", php: "php",
  css: "css", html: "html", yml: "yaml", yaml: "yaml", sh: "shell", sql: "sql", c: "c",
  cpp: "cpp", cs: "csharp", kt: "kotlin", swift: "swift", toml: "ini",
};

export default function CodeViewer({
  path,
  content,
  error,
}: {
  path: string | null;
  content: string;
  error: string | null;
}) {
  const ext = path?.split(".").pop()?.toLowerCase() ?? "";
  return (
    <div className="pane editor">
      <div className="pane-title">{path ?? "Editor"}</div>
      {!path ? (
        <div className="empty">Open a file to view it. The assistant sees the open file when you chat.</div>
      ) : error ? (
        <div className="empty">{error}</div>
      ) : (
        <Editor
          height="100%"
          theme="vs-dark"
          path={path}
          language={LANGS[ext] ?? "plaintext"}
          value={content}
          options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false }}
        />
      )}
    </div>
  );
}
