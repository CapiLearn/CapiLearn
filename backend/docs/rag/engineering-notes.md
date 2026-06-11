# RAG Engineering Notes

## Chunker Rollout Process

Chunker changes affect IDs, embeddings, retrieval logs, database volume, and
evaluation baselines. Use this sequence for future chunker versions:

1. Update `CHUNKER_VERSION` deliberately whenever output semantics change.
2. Run focused unit tests for parsing, offsets, hashes, IDs, and persistence.
3. Run ingestion with `--dry-run --fail-fast` before loading the embedding
   model or writing to PostgreSQL.
4. Run the dry preparation twice and compare ordered chunk IDs and hashes.
5. Record chunk count, type distribution, tiny chunks, oversized chunks,
   fallback reasons, and fence diagnostics.
6. Apply migrations before ingestion and confirm `alembic current` matches the
   single reported head.
7. Capture database null counts before ingestion when rollout-safe nullable
   columns were added.
8. Run full ingestion with `--fail-fast`.
9. Query the database after ingestion for nulls, uniqueness, valid offsets,
   hash lengths, chunker versions, and column/JSON consistency.
10. Run the full backend test suite and scoped Ruff checks before accepting the
    new metrics.

Do not infer successful population from model or repository tests alone. The
PR 2 verification used a real migration, embedding run, transactional
replacement, and SQL checks against the configured PostgreSQL database.

## Schema Rollout Notes

- Add new derived chunk columns as nullable when existing rows cannot be safely
  backfilled in the migration.
- Require new ingestion code to populate those fields immediately.
- Re-ingest through `replace_document_index()` to replace chunks and embeddings
  atomically for each document.
- Distinguish intentional nullable values from persistence failures. For
  example, a null `section_heading` is valid only when `heading_path` is empty.
- Keep database constraints for `(document_id, chunk_index)` and
  `(chunk_id, embedding_model)` even when service validation catches duplicate
  values earlier.
- Do not use destructive volume resets as a normal migration step. They are
  appropriate only for explicitly disposable local databases with unrecoverable
  stale migration state.

## Chunk Quality Review Notes

- Compare new results to the previous chunker version, not only to a target
  count. A higher chunk count can be correct when code blocks and Markdown
  structures are preserved.
- Separate preferred size from hard safety limits. PR 2 prefers 1,000-character
  chunks but allows complete fenced code up to 4,000 characters.
- Audit small chunks by type. Small complete code blocks and tables are
  meaningful and should not be treated as failed tiny-chunk merges.
- Character fallback should be measured and reserved for genuinely unbreakable
  text.
- Synthetic code fences or repeated table headers must set
  `rendered_content_differs` and related diagnostics because rendered chunk
  text is not an exact source slice.
- Source offsets remain relative to the original normalized source. Validate
  `char_start >= 0` and `char_end > char_start` after ingestion.

## Determinism Notes

Chunk IDs depend on source identity, chunker version, heading path, content
hash, and same-hash occurrence. Consequently:

- Identical source and configuration must reproduce IDs and ordering.
- Changing `CHUNKER_VERSION` intentionally creates a new identity generation.
- Repeated identical chunks in one document remain distinct through occurrence
  numbering.
- File renames change source identity and therefore chunk IDs.

Run corpus-level determinism checks in addition to unit tests because parser
ordering issues may only appear in real Markdown.

## Operational Notes

- Start PostgreSQL and wait for its health check before running Alembic or
  ingestion.
- `RAG_BACKEND` is selected at application startup; changing it requires a
  backend restart.
- Keep Chroma metadata scalar-compatible and retain the Chroma path as the
  current rollback option.
- Retrieval health and downstream LLM health are separate. Successful
  ingestion and retrieval can be verified through table counts and RAG events
  even if generation later fails for provider credentials or billing.
- The SentenceTransformer API currently emits a deprecation warning for
  `get_sentence_embedding_dimension()`; migrate to `get_embedding_dimension()`
  in a separately scoped maintenance change.

