/** Plain-text rendering of untrusted text; long passages collapse behind a native disclosure. */
export function LongText({ text, max = 240, quote = false }: { text: string; max?: number; quote?: boolean }) {
  const Wrap = quote ? "q" : "span";
  if (text.length <= max) return <Wrap className="whitespace-pre-wrap">{text}</Wrap>;
  return (
    <details className="group">
      <summary className="cursor-pointer list-none">
        <Wrap className="whitespace-pre-wrap">{text.slice(0, max).trimEnd()}…</Wrap>{" "}
        <span className="text-xs font-medium not-italic text-primary group-open:hidden">Show full text</span>
      </summary>
      <Wrap className="mt-1 block whitespace-pre-wrap">{text}</Wrap>
    </details>
  );
}
