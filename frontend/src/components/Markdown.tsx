import MarkdownIt from "markdown-it";
import { useMemo } from "react";

// Raw HTML in a document is shown as text, never run; images are not loaded (they could phone home); links open in a new tab.
const md = new MarkdownIt({ html: false, linkify: true, typographer: false, breaks: false });
md.disable("image");
const defaultLink = md.renderer.rules.link_open ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options));
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet("target", "_blank");
  tokens[idx].attrSet("rel", "noopener noreferrer nofollow");
  return defaultLink(tokens, idx, options, env, self);
};

export default function Markdown({ source }: { source: string }) {
  const html = useMemo(() => md.render(source), [source]);
  // The renderer escapes all HTML in the source (html: false), so this is safe to insert.
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />;
}
