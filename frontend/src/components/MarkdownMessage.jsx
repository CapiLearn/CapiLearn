import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Renders assistant message content as GitHub-flavored Markdown.
 *
 * LLM responses may include headings, bullet points, tables, inline code,
 * or code blocks. This component converts that markdown into React-rendered
 * HTML elements without manually injecting raw HTML.
 *
 * @param {Object} props - Component props.
 * @param {string} props.content - Markdown text to render.
 * @returns {JSX.Element} Rendered markdown message content.
 */

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function HighlightedText({ text, searchTerm }) {
  const normalizedSearchTerm = searchTerm.trim();

  if (!normalizedSearchTerm || typeof text !== "string") {
    return text;
  }

  const escapedSearchTerm = escapeRegExp(normalizedSearchTerm);
  const parts = text.split(new RegExp(`(${escapedSearchTerm})`, "gi"));

  return parts.map((part, index) =>
    part.toLowerCase() === normalizedSearchTerm.toLowerCase() ? (
      <mark className="message-search-highlight" key={`${part}-${index}`}>
        {part}
      </mark>
    ) : (
      part
    )
  );
}

function highlightChildren(children, searchTerm) {
  return Array.isArray(children)
    ? children.map((child, index) =>
        typeof child === "string" ? (
          <HighlightedText
            key={`${child}-${index}`}
            text={child}
            searchTerm={searchTerm}
          />
        ) : (
          child
        )
      )
    : typeof children === "string"
      ? <HighlightedText text={children} searchTerm={searchTerm} />
      : children;
}

function MarkdownMessage({ content, searchTerm = "" }) {

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p({ children }) {
          return <p>{highlightChildren(children, searchTerm)}</p>;
        },
        li({ children }) {
          return <li>{highlightChildren(children, searchTerm)}</li>;
        },
        h1({ children }) {
          return <h1>{highlightChildren(children, searchTerm)}</h1>;
        },
        h2({ children }) {
          return <h2>{highlightChildren(children, searchTerm)}</h2>;
        },
        h3({ children }) {
          return <h3>{highlightChildren(children, searchTerm)}</h3>;
        },
        td({ children }) {
          return <td>{highlightChildren(children, searchTerm)}</td>;
        },
        th({ children }) {
          return <th>{highlightChildren(children, searchTerm)}</th>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownMessage;