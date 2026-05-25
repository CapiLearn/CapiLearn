import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function MarkdownMessage({ content }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]}>
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownMessage;