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

function MarkdownMessage({ content }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownMessage;