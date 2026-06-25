import assert from "node:assert/strict";
import process from "node:process";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

async function renderCitedMarkdownMessage(t, props) {
  const server = await createServer({
    appType: "custom",
    logLevel: "error",
    root: process.cwd(),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());

  const { default: CitedMarkdownMessage } = await server.ssrLoadModule(
    "/src/components/CitedMarkdownMessage.jsx"
  );

  return renderToStaticMarkup(
    React.createElement(CitedMarkdownMessage, props)
  );
}

async function renderMarkdownMessage(t, props) {
  const server = await createServer({
    appType: "custom",
    logLevel: "error",
    root: process.cwd(),
    server: { middlewareMode: true },
  });
  t.after(() => server.close());

  const { default: MarkdownMessage } = await server.ssrLoadModule(
    "/src/components/MarkdownMessage.jsx"
  );

  return renderToStaticMarkup(React.createElement(MarkdownMessage, props));
}

test("renders normal markdown with search highlighting without citation props", async (t) => {
  const html = await renderMarkdownMessage(t, {
    content: "Read [docs](https://example.com) and use `term` with **term**.",
    searchTerm: "term",
  });

  assert.match(html, /<a href="https:\/\/example\.com">docs<\/a>/);
  assert.match(
    html,
    /<code><mark class="message-search-highlight">term<\/mark><\/code>/
  );
  assert.match(
    html,
    /<strong><mark class="message-search-highlight">term<\/mark><\/strong>/
  );
  assert.doesNotMatch(html, /citation-chip/);
});

test("renders API citations with footer citation chips", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "This is **important** [1] context.",
    citations: [
      {
        citationId: "1",
        sourcePath: "state.md",
        heading: "State",
        chunkText: "State belongs to a component.",
      },
    ],
  });

  assert.match(html, /<strong>important<\/strong>/);
  assert.equal(html.match(/class="citation-chip"/g)?.length, 1);
  assert.match(html, /\[1\]/);
  assert.match(html, /state\.md/);
  assert.match(html, /State belongs to a component\./);
  assert.match(
    html,
    /<p>This is <strong>important<\/strong> \[1\] context\.<\/p><div class="citation-list"/
  );
  assert.match(html, /<span class="citation-list-label">citations:<\/span>/);
  assert.match(html, /<div class="citation-list-items">/);
  assert.ok(
    html.indexOf("</p><div class=\"citation-list\"") <
      html.indexOf("citation-chip-wrapper")
  );
  assert.doesNotMatch(html, /citation:1/);
  assert.ok(html.indexOf("This is") < html.indexOf("[1]"));
  assert.ok(html.indexOf("[1]") < html.indexOf("context."));
});

test("preserves markdown structure across citation markers", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "- This is **important [1] context**\n- Second item",
    citations: [{ citationId: "1", chunkText: "Known source." }],
  });

  assert.match(html, /<ul>/);
  assert.match(html, /<li>This is <strong>important \[1\] context<\/strong><\/li>/);
  assert.match(html, /<div class="citation-chip-wrapper">/);
  assert.match(html, /<li>Second item<\/li>/);
  assert.doesNotMatch(html, /citation:/);
});

test("renders citation hover previews as markdown and skips raw html", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "See [1].",
    citations: [
      {
        citationId: "1",
        sourcePath: "src/content/7/en/part7a.md",
        heading: "useCallback",
        chunkText:
          "---\nmainImage: hero.svg\n---\n<div class=\"content\">\n\n### useCallback\n\n- Read [React.memo](https://react.dev/reference/react/memo)\n- Compare [part6d](../6/en/part6d.md) and [Part 6](/en/part6)\n- A function listed as a dependency of <i>useEffect</i> or <i>useMemo</i>\n\n```js\nconst value = useMemo(() => compute(), [])\n```\n\n</div>",
      },
    ],
  });

  assert.match(html, /class="citation-hover-preview"/);
  assert.match(html, /part7a\.md/);
  assert.doesNotMatch(html, /src\/content\/7\/en\/part7a\.md/);
  assert.match(html, /<h3>useCallback<\/h3>/);
  assert.match(
    html,
    /<a href="https:\/\/react\.dev\/reference\/react\/memo">React\.memo<\/a>/
  );
  assert.match(html, /Compare part6d and Part 6/);
  assert.doesNotMatch(html, /href="\.\.\/6\/en\/part6d\.md"/);
  assert.doesNotMatch(html, /href="\/en\/part6"/);
  assert.match(html, /useEffect/);
  assert.match(html, /<code class="language-js">/);
  assert.doesNotMatch(html, /mainImage: hero\.svg/);
  assert.doesNotMatch(html, /&lt;i&gt;useEffect&lt;\/i&gt;/);
  assert.doesNotMatch(html, /&lt;div class=&quot;content&quot;&gt;/);
});

test("renders repeated citation markers with shared citation metadata", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "First [1] second [1].",
    citations: [
      {
        citationId: "1",
        heading: "State",
        chunkText: "State belongs to a component.",
      },
    ],
  });

  assert.equal(html.match(/aria-label="Citation 1"/g)?.length, 1);
  assert.equal(html.match(/\[1\]/g)?.length, 3);
});

test("keeps unknown plain citation markers as text while rendering API citations", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Known [1] and unknown [9].",
    citations: [{ citationId: "1", chunkText: "Known source." }],
  });

  assert.equal(html.match(/class="citation-chip"/g)?.length, 1);
  assert.match(html, /unknown \[9\]\./);
});

test("markdown links containing citation-like text do not create citation chips", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Read [docs [1]](https://example.com).",
    citations: [],
  });

  assert.match(html, /<a href="https:\/\/example\.com">docs \[1\]<\/a>/);
  assert.doesNotMatch(html, /citation-chip/);
  assert.doesNotMatch(html, /citation-list/);
});

test("code spans containing citation-like text do not create citation chips", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Use `[1]` literally.",
    citations: [],
  });

  assert.match(html, /<code>\[1\]<\/code>/);
  assert.doesNotMatch(html, /citation-chip/);
  assert.doesNotMatch(html, /citation-list/);
});

test("renders API citation chips even when markers only appear in links or code", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Use `[1]` literally and read [docs [1]](https://example.com).",
    citations: [{ citationId: "1", chunkText: "Backend source." }],
  });

  assert.equal(html.match(/class="citation-chip"/g)?.length, 1);
  assert.match(html, /<code>\[1\]<\/code>/);
  assert.match(html, /<a href="https:\/\/example\.com">docs \[1\]<\/a>/);
  assert.match(html, /Backend source\./);
});

test("legacy citation links do not control citation chips", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Legacy [1](citation:1).",
    citations: [],
  });

  assert.match(html, /Legacy <a href="">1<\/a>\./);
  assert.doesNotMatch(html, /citation-chip/);
  assert.doesNotMatch(html, /citation-list/);
  assert.doesNotMatch(html, /citation:1/);
});

test("renders backend citation metadata even without matching content marker", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Unknown [1].",
    citations: [{ citationId: "2", chunkText: "Other source." }],
  });

  assert.match(html, /Unknown \[1\]\./);
  assert.match(html, /aria-label="Citation 2"/);
  assert.match(html, /Other source\./);
});

test("keeps legacy citation markers as literal markdown text without API citations", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Legacy [[cite:1]] stays literal.",
    citations: [],
  });

  assert.match(html, /Legacy \[\[cite:1\]\] stays literal\./);
  assert.doesNotMatch(html, /citation-chip/);
  assert.doesNotMatch(html, /citation-list/);
  assert.doesNotMatch(html, /aria-label="Citation 1"/);
});

test("keeps normal markdown links working beside citation markers", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content:
      "Read [docs](https://example.com) and avoid [bad](javascript:alert(1)) [1].",
    citations: [{ citationId: "1", chunkText: "Known source." }],
  });

  assert.match(html, /<a href="https:\/\/example\.com">docs<\/a>/);
  assert.match(html, /<a href="">bad<\/a>/);
  assert.match(html, /class="citation-chip"/);
  assert.doesNotMatch(html, /javascript:alert/);
});

test("keeps search highlighting for normal rendered markdown text", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Search **term** [1].",
    citations: [{ citationId: "1", chunkText: "Known source." }],
    searchTerm: "term",
  });

  assert.match(
    html,
    /<strong><mark class="message-search-highlight">term<\/mark><\/strong>/
  );
  assert.match(html, /class="citation-chip"/);
  assert.match(html, /<p>Search <strong><mark class="message-search-highlight">term<\/mark><\/strong> \[1\]\.<\/p>/);
});

test("drops malformed citation objects without crashing", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Malformed payload [1].",
    citations: [
      null,
      { sourcePath: "missing-id.md", chunkText: "Missing id" },
      {
        citation_id: "2",
        source_path: "snake-case.md",
        chunk_text: "Snake case is not part of the API.",
      },
      { citationId: "", chunkText: "Empty id" },
      { citationId: "1", sourcePath: 7, heading: null, chunkText: "Known source." },
    ],
  });

  assert.equal(html.match(/class="citation-chip"/g)?.length, 1);
  assert.match(html, /aria-label="Citation 1"/);
  assert.match(html, /Known source\./);
  assert.doesNotMatch(html, /missing-id\.md/);
  assert.doesNotMatch(html, /snake-case\.md/);
});

test("drops malformed citation preview text without crashing", async (t) => {
  const html = await renderCitedMarkdownMessage(t, {
    content: "Malformed preview [1].",
    citations: [
      {
        citationId: "1",
        sourcePath: "source.md",
        heading: "Source",
        chunkText: { nested: "not markdown" },
      },
    ],
  });

  assert.match(html, /aria-label="Citation 1"/);
  assert.match(html, /source\.md/);
  assert.match(html, /Source/);
  assert.doesNotMatch(html, /not markdown/);
});
