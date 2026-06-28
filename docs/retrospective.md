# Retrospective

## What we planned at the Hackathon

At the Hackathon, our plan was to build a small but useful AI learning assistant. The core scope was a RAG chat experience grounded in course material, with guardrails to keep the assistant focused on learning.

We discussed several stretch ideas early, including an instructor dashboard for classroom analytics, conversation search, student activity tracking, and a more polished citation UI. At that point, those ideas were less concrete than the RAG and guardrail work. The MVP scope treated the instructor dashboard and other analytics features as out of scope because they depended on more careful schema design and possibly topic modeling of the corpus.

## What changed and why

The biggest change was that the project became more platform-like than we expected. To make the assistant usable across student, instructor, and admin flows, we had to spend significant time on authentication and role aware routing. Those pieces were necessary, but they also competed directly with time we expected to spend on learning features.

Our RAG implementation also changed. We started with Chroma because it was quick to prototype, but later moved retrieval data into PostgreSQL with pgvector. That was a better fit for the rest of the app because conversations, users, activity, and retrieval data could all live behind the same database and migration workflow. The tradeoff was refactor cost: replacing the early prototype took time away from features that were easier to demo.

The instructor dashboard changed from a stretch idea into a partial feature. We added protected instructor dashboard APIs and a frontend dashboard view, but the frontend still uses demo data in places instead of being fully wired to live analytics.

We also added some features later than planned, such as citations for retrieved chunks. Citations became important because a RAG answer is hard to trust if the user cannot see what course material supported it. Adding that feature improved the educational value of the app, but it also created extra work near the end of the project.

## What we would do differently

We would make the data model earlier and treat it as part of the MVP. It would have made it easier to create new features on top of the schemas.

We would also choose core infrastructure earlier and avoid prototype tools that we were not willing to keep. Chroma helped us move quickly at first, but switching to PostgreSQL and pgvector was expensive. In a future version, we would decide earlier whether the goal is speed of demo or long-term consistency, then plan around that decision.

Our estimates were too optimistic. Authentication, deployment, migrations, and role-based flows took longer than expected because they touched many parts of the system. We should have planned more buffer for integration work and been stricter about what counted as a stretch feature.

Finally, we should have gotten real user feedback earlier and adjusted the product based on what we learned. That would have helped us validate which features mattered most before spending too much time on assumptions.
