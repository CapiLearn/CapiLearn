### **Phase 2 Plan **

* What two major features you plan to build  
  * Authentication  
  * Streak tracker  
  * Conversation Search implemented  
* What improvement area you are targeting (performance, UX, or evaluation)  
  * UX refinement  
* Rough timeline across W37 to W40  
  * Week 37  
    * Authentication integrated and tested  
  * Week 38  
    * Streak tracker integrated and tested
    * Conversation Search implemented  
  * Week 39  
    * Deployment
  * Week 40  
    * Final UX refinement and illustration/animation integration   


Instructor Dashboard  
Metrics tracked:

- [ ] Number of student users  
- [ ] Question breakdown by topic/chapter  
- [ ] Number of total questions asked  
- [ ] Student activity overview: top topic, number of questions asked, current streak, last login  
- [ ] Pie graph of users active in last week verses total users

## Phase 2 Features 

## RAG Overhaul Completed

The original local Chroma RAG implementation was upgraded to a PostgreSQL and
pgvector-backed retrieval system while preserving Chroma as a rollback option.
The existing chat, guardrail, prompt-building, and LLM generation flow was not
rewritten.

Completed work:

- Added PostgreSQL tables for RAG documents, chunks, 384-dimensional
  embeddings, and retrieval logs.
- Enabled the pgvector extension and added an HNSW cosine-similarity index.
- Merged the Alembic migration branches into one head and verified migrations
  from a clean Docker volume.
- Added a pgvector repository and service behind the existing retrieval
  provider interface.
- Added repository ingestion that filters English course content, applies
  Markdown-aware chunking, and embeds chunks with
  `sentence-transformers/all-MiniLM-L6-v2`.
- Added runtime query embedding and asynchronous pgvector cosine-similarity
  search.
- Preserved the existing guardrail flow and `<retrieved_context>` prompt
  injection through `build_messages()`.
- Added structured retrieval events and optional database retrieval logs with
  chunk IDs, distances, and similarity scores.
- Documented pgvector as the preferred backend for this branch while retaining
  `RAG_BACKEND=chroma` for rollback.
- Added local setup, verification, and troubleshooting instructions.

Live verification results:

- PostgreSQL/pgvector started successfully with pgvector `0.8.2`.
- Alembic current and head both resolved to `20260606_0005`.
- Ingestion completed with zero failures.
- Stored 72 documents, 2,353 chunks, and 2,353 embeddings.
- A live chat request selected pgvector, embedded the query, retrieved five
  chunks, injected them into the prompt, completed OpenAI generation, and
  persisted the retrieval and response.
- Backend test suite passed with 116 tests, and Ruff checks passed.
- No frontend files were changed.

Remaining deployment requirements:

- Set `RAG_BACKEND=pgvector` before starting the backend.
- Run migrations and ingestion before serving chat traffic.
- Configure an active LLM API key with available API credits.
- Keep Chroma available as a temporary rollback path.
