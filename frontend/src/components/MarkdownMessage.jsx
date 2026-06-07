import { Children, cloneElement, isValidElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function HighlightedText({ text, searchTerm }) {
  const normalizedSearchTerm = searchTerm.trim();

  if (!normalizedSearchTerm) {
    return text;
  }

  const escapedSearchTerm = escapeRegExp(normalizedSearchTerm);
  const parts = String(text).split(new RegExp(`(${escapedSearchTerm})`, "gi"));

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
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      return <HighlightedText text={child} searchTerm={searchTerm} />;
    }

    if (isValidElement(child)) {
      return cloneElement(
        child,
        undefined,
        highlightChildren(child.props.children, searchTerm)
      );
    }

    return child;
  });
}

/**
 * Renders assistant message content as GitHub-flavored Markdown.
 *
 * LLM responses may include headings, bullet points, tables, inline code,
 * or code blocks. When a search term is provided, text inside rendered
 * Markdown elements is highlighted while preserving Markdown structure.
 *
 * @param {Object} props - Component props.
 * @param {string} props.content - Markdown text to render.
 * @param {string} [props.searchTerm] - Optional search term to highlight.
 * @returns {JSX.Element} Rendered markdown message content.
 */
function MarkdownMessage({ content, searchTerm = "" }) {
  const renderHighlightedChildren = (children) =>
    highlightChildren(children, searchTerm);

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p({ children }) {
          return <p>{renderHighlightedChildren(children)}</p>;
        },
        li({ children }) {
          return <li>{renderHighlightedChildren(children)}</li>;
        },
        h1({ children }) {
          return <h1>{renderHighlightedChildren(children)}</h1>;
        },
        h2({ children }) {
          return <h2>{renderHighlightedChildren(children)}</h2>;
        },
        h3({ children }) {
          return <h3>{renderHighlightedChildren(children)}</h3>;
        },
        td({ children }) {
          return <td>{renderHighlightedChildren(children)}</td>;
        },
        th({ children }) {
          return <th>{renderHighlightedChildren(children)}</th>;
        },
        code({ children, ...props }) {
          return <code {...props}>{renderHighlightedChildren(children)}</code>;
        },
        a({ children, ...props }) {
          return <a {...props}>{renderHighlightedChildren(children)}</a>;
        },
        strong({ children }) {
          return <strong>{renderHighlightedChildren(children)}</strong>;
        },
        em({ children }) {
          return <em>{renderHighlightedChildren(children)}</em>;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownMessage;