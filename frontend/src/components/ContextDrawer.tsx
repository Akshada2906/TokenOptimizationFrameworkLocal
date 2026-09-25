import { api, ContextImage } from "../api";

export default function ContextDrawer({
  sessionId,
  images,
  onClose,
}: {
  sessionId: string;
  images: ContextImage[];
  onClose: () => void;
}) {
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <strong>What the AI sees</strong>
          <button className="secondary small" onClick={onClose}>
            Close
          </button>
        </div>
        <p className="muted">
          These PixelPrompt images are the assistant's grounding context for structural questions.
        </p>
        {images.map((img) => (
          <figure key={img.name}>
            <img src={api.contextImageUrl(sessionId, img.name)} alt={img.title} />
            <figcaption>
              {img.kind} · {img.width}×{img.height}
            </figcaption>
          </figure>
        ))}
      </aside>
    </div>
  );
}
