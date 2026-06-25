# RAG Metrics (Historical Homework Assignment Snapshot)

This document records a dated homework/assignment verification snapshot from
older RAG work. It is not the current runtime configuration source of truth.
Use current architecture and runbook docs for final pgvector/OpenAI runtime
configuration.

## PR 2 Structure-Aware Chunking

**Verified:** June 10, 2026  
**Chunker version:** `markdown-structure-v3`  
**Historical embedding model:** `sentence-transformers/all-MiniLM-L6-v2`  
**Embedding dimensions:** 384

This section records older PR 2 verification data. The MiniLM /
sentence-transformers reference is historical and is not the current runtime
embedding configuration. The final runtime uses PostgreSQL pgvector with OpenAI
`text-embedding-3-small` embeddings and the persisted embedding contract:
`embedding_provider`, `embedding_model`, and `embedding_dimensions`.

### Ingestion Results

The full local Full Stack Open corpus was ingested through:

```bash
uv run python -m backend.ingestion.ingest_pgvector --fail-fast
```

The completed run reported:

| Metric | Result |
|---|---:|
| Files discovered | 350 |
| English documents indexed | 72 |
| Non-English files skipped | 278 |
| Empty files skipped | 0 |
| Preprocessing failures | 0 |
| Documents written | 72 |
| Chunks written | 4,274 |
| Embeddings written | 4,274 |
| Database failures | 0 |

The PR 1 `markdown-window-v2-contract` corpus contained 2,353 chunks. PR 2
increases the count because fenced code and other Markdown structures are kept
as coherent blocks instead of being cut by arbitrary character windows.

### Chunk Type Distribution

| Chunk type | Count |
|---|---:|
| Prose | 2,413 |
| Code | 1,281 |
| Mixed | 523 |
| List | 54 |
| Table | 3 |
| **Total** | **4,274** |

### Nullable Schema Population

The PR 1 migration intentionally introduced nullable chunk-contract columns so
it could be deployed before re-ingestion. After the PR 2 ingestion:

| Column | Null rows |
|---|---:|
| `content_hash` | 0 |
| `char_start` | 0 |
| `char_end` | 0 |
| `heading_path` | 0 |
| `chunk_type` | 0 |
| `chunker_version` | 0 |
| `section_heading` | 186 |

All 186 null `section_heading` values have an empty `heading_path`. They
represent source spans before any detected Markdown heading, not failed
persistence.

### Integrity Checks

- Negative `char_start` values: 0
- Ranges where `char_end <= char_start`: 0
- Content hashes not 64 characters long: 0
- Unique `(document_id, chunk_index)` pairs: 4,274
- Unique chunk IDs: 4,274
- Unique `(chunk_id, embedding_provider, embedding_model, embedding_dimensions)`
  identities: 4,274
- Column-to-JSON metadata mismatches for hash, offsets, version, and type: 0
- Distinct stored chunker versions after ingestion: one,
  `markdown-structure-v3`

### Dry-Run Quality Observations

The same corpus produced identical chunk order, hashes, and IDs across repeated
dry runs:

```text
chunks=4274
deterministic=True
```

Additional measurements:

| Metric | Result |
|---|---:|
| Average chunk length | 379.3 characters |
| Maximum chunk length | 3,384 characters |
| Chunks over the preferred 1,000-character size | 47 |
| Prose chunks under 120 characters | 72 |
| Code chunks with invalid source boundaries | 0 |

The 47 chunks over 1,000 characters are complete fenced-code blocks accepted
under the explicit oversized-code allowance. Code blocks over the configured
hard maximum are split by lines with balanced synthetic fences and diagnostics.

### Test Validation

```text
uv run pytest backend/tests
159 passed

Focused chunking, ingestion, repository, and service tests
40 passed

uv run ruff check ...
All checks passed

uv run ruff format --check ...
All checked files formatted

git diff --check
Passed
```

