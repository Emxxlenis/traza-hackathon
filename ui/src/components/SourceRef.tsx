import { sourceLabel } from "../lib/plainLanguage";

interface SourceRefProps {
  id: string;
}

/**
 * A source reference: readable label first, technical id preserved as
 * secondary text. When there is no known label, the id stays as the main
 * (and only) text — it never disappears.
 */
export function SourceRef({ id }: SourceRefProps) {
  const { label, technical } = sourceLabel(id);
  if (label === technical) {
    return <code>{technical}</code>;
  }
  return (
    <>
      <span className="source-label">{label}</span>{" "}
      <span className="source-technical" title={technical}>
        {technical}
      </span>
    </>
  );
}
