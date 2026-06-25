import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { highlightMarkdownChildren } from "./markdownHighlighting";

function shouldSkipTextRenderingElement(child) {
  const tagName = child.props?.node?.tagName;

  return (
    child.type === "a" ||
    child.type === "code" ||
    tagName === "a" ||
    tagName === "code"
  );
}

/**
 * Renders assistant message content as GitHub-flavored Markdown.
 *
 * When a search term is provided, visible rendered text is highlighted while
 * preserving Markdown structure.
 *
 * @param {Object} props - Component props.
 * @param {string} props.content - Markdown content to render.
 * @param {string} [props.searchTerm] - Optional search term to highlight.
 * @returns {JSX.Element} Rendered Markdown message.
 */
function MarkdownMessage({ content = "", searchTerm = "" }) {
  const renderHighlightedChildren = (children) =>
    highlightMarkdownChildren(
      children,
      searchTerm,
      shouldSkipTextRenderingElement
    );
  const defaultComponents = {
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
    h4({ children }) {
      return <h4>{renderHighlightedChildren(children)}</h4>;
    },
    h5({ children }) {
      return <h5>{renderHighlightedChildren(children)}</h5>;
    },
    h6({ children }) {
      return <h6>{renderHighlightedChildren(children)}</h6>;
    },
    td({ children }) {
      return <td>{renderHighlightedChildren(children)}</td>;
    },
    th({ children }) {
      return <th>{renderHighlightedChildren(children)}</th>;
    },
    strong({ children }) {
      return <strong>{renderHighlightedChildren(children)}</strong>;
    },
    em({ children }) {
      return <em>{renderHighlightedChildren(children)}</em>;
    },
    a({ children, href, title }) {
      const safeHref = defaultUrlTransform(href);

      return (
        <a href={safeHref} title={title}>
          {renderHighlightedChildren(children)}
        </a>
      );
    },
    code({ children, className }) {
      return (
        <code className={className}>
          {renderHighlightedChildren(children)}
        </code>
      );
    },
  };

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={defaultComponents}
    >
      {typeof content === "string" ? content : ""}
    </ReactMarkdown>
  );
}

export default MarkdownMessage;
