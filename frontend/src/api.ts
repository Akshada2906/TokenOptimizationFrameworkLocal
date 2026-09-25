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
}

export interface UsedImage {
  name: string;
  kind: string;
  title: string;
  width: number;
  height: number;
  source: "grounding" | "code" | "file";
  file?: string;
  page?: number;
  pages?: number;
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

export const api = {
  createFromUrl: (repo_url: string) =>
    fetch(base, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_url }),
    }).then((r) => json<{ session_id: string }>(r)),

  createFromFolder: (files: FileList) => {
    const form = new FormData();
    // Only send real code/config/doc files (mirrors backend is_code_file); skips dependency and build folders.
    const skipDir = /(^|\/)(\.git|node_modules|venv|\.venv|__pycache__|dist|build|\.next|target|\.idea)(\/|$)/;
    const exts = new Set(CODE_EXTS.split(" "));
    const names = new Set(["Dockerfile", "Makefile", "requirements.txt", "go.mod", "Gemfile", ".env.example"]);
    const lock = /(^|\/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock)$|\.(min\.js|min\.css|map)$/;
    let sent = 0;
    Array.from(files).forEach((f) => {
      const rel = (f as any).webkitRelativePath || f.name;
      const base = rel.split("/").pop() as string;
      const ext = base.includes(".") ? "." + base.split(".").pop()!.toLowerCase() : "";
      if (skipDir.test(rel) || lock.test(rel) || f.size > 1_000_000) return;
      if (names.has(base) || exts.has(ext)) {
        form.append("files", f, rel);
        sent++;
      }
    });
    if (sent === 0) return Promise.reject(new Error("No source code files found in that folder."));
    return fetch(`${base}/upload`, { method: "POST", body: form }).then((r) =>
      json<{ session_id: string }>(r),
    );
  },

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
