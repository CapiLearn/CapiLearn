import { Children, cloneElement, createElement, isValidElement } from "react";

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
    part.toLowerCase() === normalizedSearchTerm.toLowerCase()
      ? createElement(
          "mark",
          {
            className: "message-search-highlight",
            key: `${part}-${index}`,
          },
          part
        )
      : part
  );
}

export function renderHighlightedText(text, searchTerm, key) {
  const normalizedSearchTerm = searchTerm.trim();

  if (!normalizedSearchTerm || typeof text !== "string") {
    return text;
  }

  return createElement(HighlightedText, { key, text, searchTerm });
}

export function highlightMarkdownChildren(
  children,
  searchTerm,
  shouldSkipElement = () => false
) {
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      return renderHighlightedText(child, searchTerm);
    }

    if (isValidElement(child)) {
      if (shouldSkipElement(child)) {
        return child;
      }

      return cloneElement(
        child,
        undefined,
        highlightMarkdownChildren(
          child.props.children,
          searchTerm,
          shouldSkipElement
        )
      );
    }

    return child;
  });
}
