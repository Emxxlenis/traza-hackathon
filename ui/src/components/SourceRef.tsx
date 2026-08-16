import { sourceLabel } from "../lib/plainLanguage";
import { sourceIcon } from "../lib/sourceIcons";

interface SourceRefProps {
  id: string;
}

/**
 * A source reference: icon + readable label first, technical id preserved as
 * secondary text. When there is no known label, the id stays as the main
 * (and only) text — it never disappears.
 */
export function SourceRef({ id }: SourceRefProps) {
  const { label, technical } = sourceLabel(id);
  const Icon = sourceIcon(id);
  if (label === technical) {
    return <code>{technical}</code>;
  }
  return (
    <>
      <span className="source-label">
        <Icon className="source-icon" size={14} strokeWidth={2} aria-hidden="true" />
        {label}
      </span>{" "}
      <span className="source-technical" title={technical}>
        {technical}
      </span>
    </>
  );
}
