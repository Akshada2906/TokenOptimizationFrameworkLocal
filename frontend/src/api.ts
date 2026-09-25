export type Stats = Record<string, any>;

export interface SessionStatus {
  session_id: string;
  status: string;
  error: string | null;
  source: string;
  stats: Stats;
}

export interface TreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: TreeNode[];
}

export interface ChatStats {
  image_tokens: number;
  text_tokens: number;
  output_tokens: number;
  images_used: number;
  sent_as_text_tokens?: number;
  units_as_text?: number;
}

export interface UsedImage {
  name: string;
  kind: string;
  title: string;
  width: number;
  height: number;
  source: "grounding" | "code" | "file" | "text";
  text_tokens?: number;
  image_tokens_avoided?: number;
  file?: string;
  page?: number;
  pages?: number;
  reason?: string;
}

export interface ChatReply {
  answer: string;
  context_used: string;
  stats: ChatStats;
  images_used: UsedImage[];
}

export interface ContextImage {
  name: string;
  kind: string;
  title: string;
  width: number;
  height: number;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

const base = "/api/sessions";
const CODE_EXTS =
  ".py .js .jsx .ts .tsx .mjs .cjs .java .go .rs .rb .php .cs .c .h .cc .cpp .hpp .kt .swift .scala .sh .bash .sql " +
  ".html .css .scss .vue .svelte .md .mdx .json .yml .yaml .toml .ini .cfg .xml .gradle .proto .graphql";

const SKIP_DIR = /(^|\/)(\.git|node_modules|venv|\.venv|__pycache__|dist|build|\.next|target|\.idea|graphify-out|code-review-graph)(\/|$)/;
const NAMES = new Set(["Dockerfile", "Makefile", "requirements.txt", "go.mod", "Gemfile", ".env.example"]);
const LOCKS = /(^|\/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock)$|\.(min\.js|min\.css|map)$/;
const EXTS = new Set(CODE_EXTS.split(" "));

/** Only real code/config/doc files are sent (mirrors backend is_code_file). */
export function wantFile(rel: string, size: number): boolean {
  if (SKIP_DIR.test(rel) || LOCKS.test(rel) || size > 1_000_000) return false;
  const base = rel.split("/").pop() as string;
  const ext = base.includes(".") ? "." + base.split(".").pop()!.toLowerCase() : "";
  return NAMES.has(base) || EXTS.has(ext);
}

export interface GraphInfo {
  folder: string;
  path: string | null;
  generated: boolean;
  source: string | null;
  nodes: number;
  edges: number;
  has_html: boolean;
  files: { path: string; size: number }[];
}

export const api = {
  createFromUrl: (repo_url: string) =>
    fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_url }),
    }).then((r) => json<{ session_id: string }>(r)),

  createFromLocal: (path: string) =>
    fetch(`${base}/local`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    }).then((r) => json<{ session_id: string }>(r)),

  createFromFolder: (files: FileList) => {
    const form = new FormData();
    let sent = 0;
    Array.from(files).forEach((f) => {
      const rel = (f as any).webkitRelativePath || f.name;
      if (wantFile(rel, f.size)) {
        form.append("files", f, rel);
        sent++;
      }
    });
    if (sent === 0) return Promise.reject(new Error("No source code files found in that folder."));
    return fetch(`${base}/upload`, { method: "POST", body: form }).then((r) =>
      json<{ session_id: string }>(r),
    );
  },

  createFromFiles: (files: { file: File; rel: string }[]) => {
    const form = new FormData();
    files.forEach(({ file, rel }) => form.append("files", file, rel));
    return fetch(`${base}/upload`, { method: "POST", body: form }).then((r) =>
      json<{ session_id: string }>(r),
    );
  },

  graph: (id: string) => fetch(`${base}/${id}/graph`).then((r) => json<GraphInfo>(r)),
  graphHtmlUrl: (id: string) => `${base}/${id}/graph.html`,
  graphFiles: (id: string) =>
    fetch(`${base}/${id}/graph-files`).then((r) =>
      json<{ folder: string; files: { path: string; size: number }[]; gitignore: string }>(r),
    ),
  graphFileUrl: (id: string, path: string) => `${base}/${id}/graph-file?path=${encodeURIComponent(path)}`,

  status: (id: string) => fetch(`${base}/${id}`).then((r) => json<SessionStatus>(r)),
  tree: (id: string) => fetch(`${base}/${id}/tree`).then((r) => json<TreeNode[]>(r)),
  file: (id: string, path: string) =>
    fetch(`${base}/${id}/file?path=${encodeURIComponent(path)}`).then((r) =>
      json<{ path: string; content: string }>(r),
    ),
  context: (id: string) =>
    fetch(`${base}/${id}/context`).then((r) =>
      json<{ images: ContextImage[]; stats: Stats }>(r),
    ),
  contextImageUrl: (id: string, name: string) =>
    `${base}/${id}/context/image?name=${encodeURIComponent(name)}`,
  chat: (id: string, message: string, open_file: string | null) =>
    fetch(`${base}/${id}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, open_file }),
    }).then((r) => json<ChatReply>(r)),
};
