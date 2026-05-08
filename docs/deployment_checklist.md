
### **Pre-deployment:**

* [ ] CI pipeline green on this commit 
* [ ] Evaluation tests pass on baseline prompt set
* [ ] Latency on demo prompts within budget 
* [ ] Env vars, secrets, model version, index version all pinned
* [ ] Git tag exists for rollback target

### **During deployment:**

* [ ] Deploy command ran without errors
* [ ] Health endpoint returns 200 with expected version
* [ ] Smoke test prompts produce sensible, cited answers
  
### **Post-deployment:**

* [ ] Latency ≤ baseline 5 min after deploy
* [ ] Team channel updated: "deployed vX.Y.Z at HH:MM"
* [ ] failure rate/retry rate < 5% for model API