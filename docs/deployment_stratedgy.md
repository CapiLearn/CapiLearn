Deployment Breakout

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
