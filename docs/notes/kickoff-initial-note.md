# Initial Setup - Stephan

I created the initial scaffolding for our capstone project, with a backend/ for our fastapi backend, a frontend/ for a likely nextjs frontend app, and docs/ for documentation on our project. I added a ci check with ruff for the python code in the backend. I also added some agent skills for best practices with fastapi and nextjs.

wireframe/ contains a skeleton frontend that captures what our app could look like. It's not the actual frontend and many things could change. Our actual web app will be in frontend/.

## next steps
Here are some of the core components that we need:

### database
likely should be postgres (via docker container) with pgvector. We can store typical relational data as well as the vectors in postgres. If we used a dedicated vector store, we would need a separate database as well.

### Data ingestion, chunking, and embeddings
OCR engine- docling, marker, or an api based one, like mistral OCR. 
chunking- langchain text splitters, chonkie
embeddings- lots of different models available via SentenceTransformers. Microsoft harrier 0.6B is very competitive.

### RAG retrieval with ranking or filtering
we could do a vanilla RAG with pgvector + just vector search, or possibly hybrid search (tsvector, which uses BM25) with reranker.

Later we can consider more complex approaches like a cross encoder, although we may have to ask questions about latency

### Prompt design with guardrails (no direct answers)
Could use NeMo guardrails. It has lots of different options, so we could start with simple guardrails and then move on to LLM based verifier guardrails. How well they work is an empirical question, so we would need an evaluation dataset in the future.

### A user interface and interaction flow (frontend)
We could start with a frontend template that offers a chat ui out of the box, and then modify it. Some examples:

https://github.com/vercel/chatbot
https://github.com/langchain-ai/agent-chat-ui


This repo has several different full featured examples, but we could take some inspiration from it.

https://github.com/langchain-ai/langchain-nextjs-template

Once we agree on the frontend template, we can also set up typescript ci.

## Future steps, nice to haves

### datasets to evaluate RAG and guardrails
We need to create a set of adversarial questions (or even conversations) to see how well the guardrails hold up. Specifically:
- need to test the input guardrail for inappropriate prompts
- need to test output guardrail so that the LLM does not return the answer directly

### evaluation libraries
Once we have some data, we can evaluate our RAG system against certain metrics, like hallucination rates, usefulness, etc. Here are some libraries we could use:

https://deepeval.com/
https://github.com/langchain-ai/openevals 
https://docs.ragas.io/en/latest/

### LLMOps
This is for tracing LLM outputs:

https://github.com/langfuse/langfuse
Arize Phoenix, which has a self hosted version under ELv2

### topic modeling for categorization
- we could have an llm scan through the corpus of documents and create topic tags, possibly hierarchical, and then use it as a taxonomy for classifying user questions. The classification can use a lightweight LLM.

## Blockers/open questions
- we need to see the corpus of documents, so that we can test against it and evaluate our RAG model
- Are the documents allowed to be seen by the students? For example, if we want citations to source documents in our app, that would only make sense if we can show snippets to the students. Otherwise from the student perspective it's just a chatbot, while internally it's a RAG system
- Are there latency constraints? More aggressive guardrails and multiple llm calls can increase latency, which can hurt user experience. Also, if we have an output guardrail, we may not be able to stream the response.
