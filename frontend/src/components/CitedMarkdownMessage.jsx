import { useId } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import MarkdownMessage from "./MarkdownMessage";
import "../styles/CitedMarkdownMessage.css";

const FRONTMATTER_PATTERN = /^---\n[\s\S]*?\n---\s*\n?/;

function prepareCitationPreview(content) {
  if (typeof content !== "string") {
    return "";
  }

  return content.replace(FRONTMATTER_PATTERN, "").trim();
}

function isWebsiteLink(href) {
  try {
    const url = new URL(href);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function citationSourceFileName(sourcePath) {
  return (
    sourcePath.replace(/\\/g, "/").replace(/\/+$/, "").split("/").pop()?.trim() ||
    ""
  );
}

function isRenderableCitation(citation) {
  return (
    citation &&
    typeof citation.citationId === "string" &&
    citation.citationId.trim()
  );
}

const citationPreviewComponents = {
  a({ children, href, title }) {
    const safeHref = defaultUrlTransform(href);

    if (!isWebsiteLink(safeHref)) {
      return <>{children}</>;
    }

    return (
      <a href={safeHref} title={title}>
        {children}
      </a>
    );
  },
};

/**
 * CitedMarkdownMessage renders assistant answers with backend-provided RAG
 * citation metadata.
 *
 * The message body remains normal Markdown, while citation chips expose source
 * file and chunk previews so reviewers can verify answer grounding from the UI.
 */
function CitationPreviewMarkdown({ content = "" }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      components={citationPreviewComponents}
    >
      {typeof content === "string" ? content : ""}
    </ReactMarkdown>
  );
}

function CitationChip({ citation }) {
  const reactId = useId();
  const citationId = citation.citationId;
  const sourcePath =
    typeof citation.sourcePath === "string" ? citation.sourcePath : "";
  const heading = typeof citation.heading === "string" ? citation.heading : "";
  const chunkText =
    typeof citation.chunkText === "string" ? citation.chunkText : "";
  const tooltipId = `${reactId}-citation-tooltip`;
  const sourceFileName = citationSourceFileName(sourcePath);
  const hasTooltip = Boolean(sourceFileName || heading || chunkText);
  const previewContent = prepareCitationPreview(chunkText);

  return (
    <div className="citation-chip-wrapper">
      <button
        aria-describedby={hasTooltip ? tooltipId : undefined}
        aria-label={`Citation ${citationId}`}
        className="citation-chip"
        type="button"
      >
        [{citationId}]
      </button>

      {hasTooltip && (
        <div className="citation-hover-card" id={tooltipId} role="tooltip">
          {sourceFileName && (
            <div className="citation-hover-source">{sourceFileName}</div>
          )}
          {heading && (
            <strong className="citation-hover-heading">{heading}</strong>
          )}
          {previewContent && (
            <div className="citation-hover-preview">
              <CitationPreviewMarkdown content={previewContent} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CitedMarkdownMessage({ content = "", citations = [], searchTerm = "" }) {
  const renderedCitations = Array.isArray(citations)
    ? citations.filter(isRenderableCitation)
    : [];

  return (
    <>
      <MarkdownMessage content={content} searchTerm={searchTerm} />

      {renderedCitations.length > 0 && (
        <div className="citation-list" aria-label="Citations">
          <span className="citation-list-label">citations:</span>
          <div className="citation-list-items">
            {renderedCitations.map((citation, index) => (
              <CitationChip
                citation={citation}
                key={`citation-footer-${citation.citationId}-${index}`}
              />
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export default CitedMarkdownMessage;
