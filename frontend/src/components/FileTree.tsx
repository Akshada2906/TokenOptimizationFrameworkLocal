import { useState } from "react";
import { TreeNode } from "../api";

function Node({
  node,
  depth,
  selected,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selected: string | null;
  onSelect: (p: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const pad = { paddingLeft: 10 + depth * 14 };
  if (node.type === "dir") {
    return (
      <>
        <div className="tree-row dir" style={pad} onClick={() => setOpen(!open)}>
          <span className="caret">{open ? "▾" : "▸"}</span> {node.name}
        </div>
        {open &&
          node.children?.map((c) => (
            <Node key={c.path} node={c} depth={depth + 1} selected={selected} onSelect={onSelect} />
          ))}
      </>
    );
  }
  return (
    <div
      className={`tree-row file ${selected === node.path ? "selected" : ""}`}
      style={pad}
      onClick={() => onSelect(node.path)}
    >
      {node.name}
    </div>
  );
}

export default function FileTree({
  nodes,
  selected,
  onSelect,
}: {
  nodes: TreeNode[];
  selected: string | null;
  onSelect: (p: string) => void;
}) {
  return (
    <div className="pane tree">
      <div className="pane-title">Files</div>
      <div className="tree-body">
        {nodes.map((n) => (
          <Node key={n.path} node={n} depth={0} selected={selected} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
