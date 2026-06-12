
### **Pre-deployment:**

* [ ] CI pipeline green on this commit 
* [ ] Evaluation tests pass on baseline prompt set
* [ ] Latency on demo prompts within budget 
* [ ] Env vars, secrets, model version, index version all pinned
* [ ] Before deploying or restarting this branch on Render, run `alembic upgrade head` against the target Render database. Migration `20260612_0009` must be applied before app code that reads `embedding_provider` or `embedding_dimensions` is live.
* [ ] Enable temporary beta Basic Auth by setting all three Render backend env vars together:
  * `BETA_AUTH_ENABLED=true`
  * `BETA_AUTH_USERNAME=<shared beta username>`
  * `BETA_AUTH_PASSWORD=<strong shared password>`
* [ ] Confirm `/health` remains public and backend/API, docs, admin, and model-spend routes require beta credentials.
* [ ] Do not place beta Basic Auth credentials in frontend JavaScript. A separately deployed static frontend may remain publicly loadable; this gate protects backend/API and model-spend traffic.
* [ ] Remove the temporary beta middleware before Clerk Bearer-token authentication is enabled end-to-end because both use the `Authorization` header.
* [ ] Git tag exists for rollback target

### **During deployment:**

* [ ] Deploy command ran without errors
* [ ] Health endpoint returns 200 with expected version
* [ ] Smoke test prompts produce sensible, cited answers
  
### **Post-deployment:**

* [ ] Latency ≤ baseline 5 min after deploy
* [ ] Team channel updated: "deployed vX.Y.Z at HH:MM"
* [ ] failure rate/retry rate < 5% for model API
