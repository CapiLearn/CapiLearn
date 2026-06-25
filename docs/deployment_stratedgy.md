# Historical Deployment Breakout

This is a historical planning note, not the current final Render handoff source
of truth.

Current Render note: the validated topology is a separate Render backend
service, a separate Render frontend static site, and Render Postgres. Do not run
automatic ingestion during backend startup or frontend build; pgvector ingestion
is manual-only after environment and migration confirmation.

Step 1:
Where does your system run?
AWS

What are you deploying? Code only? Code + model? Code + model + index?
Code & index

Who's the audience?
Future FCF students

Step 2:
Primary Stratedgy
Canary & Shadow

Step 3:
What change, if it went wrong, would most hurt your demo?
LLM issues like latency, new verison, change in call structure

How does your strategy protect against that specific failure?
Fallback to older LLM model with known outcomes.

Is it still fails, what happens in the next 5 minutes?

During Deployment Testing
Switch traffic to pervious verison.

After Roll-out
Spin up previous verison and push traffic to that verison. 
