import { api, wantFile } from "./api";

/** Chrome/Edge folder picker with write access (lets us save code-review-graph/ into the user's folder). */
export const canPickFolder = () => typeof (window as any).showDirectoryPicker === "function";

export async function pickProjectFolder(): Promise<{ dir: any; files: { file: File; rel: string }[] }> {
  const dir = await (window as any).showDirectoryPicker({ mode: "readwrite" });
  const files: { file: File; rel: string }[] = [];

  async function walk(handle: any, prefix: string) {
    for await (const [name, child] of handle.entries()) {
      const rel = `${prefix}${name}`;
      if (child.kind === "directory") {
        if (!/^(\.git|node_modules|venv|\.venv|__pycache__|dist|build|\.next|target|\.idea|graphify-out|code-review-graph)$/.test(name))
          await walk(child, `${rel}/`);
      } else {
        const file: File = await child.getFile();
        if (wantFile(`${dir.name}/${rel}`, file.size)) files.push({ file, rel: `${dir.name}/${rel}` });
      }
    }
  }
  await walk(dir, "");
  return { dir, files };
}

/** Write the generated graph into <picked folder>/code-review-graph/. Returns the number of files saved. */
export async function saveGraphInto(dir: any, sessionId: string): Promise<number> {
  const { folder, files, gitignore } = await api.graphFiles(sessionId);
  if (!files.length) return 0; // the repo already had its own graph
  const root = await dir.getDirectoryHandle(folder, { create: true });
  for (const f of files) {
    const parts = f.path.split("/");
    let d = root;
    for (const part of parts.slice(0, -1)) d = await d.getDirectoryHandle(part, { create: true });
    const fh = await d.getFileHandle(parts[parts.length - 1], { create: true });
    const w = await fh.createWritable();
    await w.write(await (await fetch(api.graphFileUrl(sessionId, f.path))).blob());
    await w.close();
  }
  await ensureGitignore(dir, folder, gitignore);
  return files.length;
}

/** Append code-review-graph/ to the project's .gitignore if it is not listed yet. */
async function ensureGitignore(dir: any, folder: string, block: string) {
  const fh = await dir.getFileHandle(".gitignore", { create: true });
  const current: string = await (await fh.getFile()).text();
  if (current.split("\n").some((l) => l.trim().replace(/\/$/, "").replace(/^\//, "") === folder)) return;
  const w = await fh.createWritable();
  await w.write(current + (current && !current.endsWith("\n") ? "\n" : "") + (current ? "\n" : "") + block);
  await w.close();
}
