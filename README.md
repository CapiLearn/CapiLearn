# Project Name: CapiLearn

# Team Members:

    ## Elizabeth Howard
    ## Stephan Caamano
    ## Jose Diaz

# Description:

CapiLearn is an AI-powered learning assistant designed to help students think through problems instead of just receiving answers. Using conversational AI and retrieval-based support, the platform guides users with Socratic-style questioning, personalized explanations, and contextual academic support.
The goal is to create a more engaging and ethical homework help experience that strengthens understanding, reduces dependency on answer-copying, and gives students a space to learn interactively and confidently.

# Tech Stack

    - React.js
    - Vercel AI (ChatBot template) or LangChain (ChatBot template)
    - python
    - LLM
    - GuardRail LLM
    - RAG
    - Postgres DB with VectorDB extension

# Branches

    -  UI
    -  endpoints
    -  LLM
    -  RAG
    -  DB
    -  guardrails
        - pre
        - post 
    - ingestion
    
# Folder structure
 
    backend
    │   ├───DB
    │   ├───endpoints  
    │   ├───ingestion
    │   ├───LLM
    │   ├───RAG
    │   └───tests
    ├───data
    ├───docs
    frontend
        └───tests

    

# Setup and installation:

1. Create and activate a virtual environment

    ### Windows

    ```bash
        python -m venv venv
        venv\Scripts\activate
    ```

    ### Mac/Linux

    ```bash
        python3 -m venv venv
        source venv/bin/activate
    ```

2. Install requirements
    
    uv pip install -r requirements.txt

3. Run the application

    python main.py

# Architecture Diagram

    See ![design diagram](CapiLearn\docs\educational-ai-assistant-system-design-simplified.png) in docs folder.


# Ownership

    Jose - UI/UX, endpoints
    Stephan - LLM, guardrails
    Lizzy - RAG, ingestion
