# Project intent file — read by Claude Code at session start

## Project
Name: MultiAgentSupplyChainSystem
Stack: Python · FastAPI · Gemini 3 Flash · ChromaDB · sentence-transformers · AWS AgentCore · Alpine.js

## What This System Does
Upload a warehouse shelf photo → 4 AI agents collaborate:
1. Vision Agent — counts items using Gemini 3 Flash + code execution
2. Supplier Agent — finds best matching part via ChromaDB cosine vector search (local, free)
3. Logistics Agent — calculates shipping cost, carrier, ETA
4. Control Tower — orchestrates all agents via A2A protocol, streams results via WebSocket
Then: Gmail + Google Calendar + Google Sheets confirmation via MCP

## Current Branch
Branch: feature/AgentCore
Origin: https://github.com/kendallmark3/MultiAgentSupplyChainSystem.git

## Architecture Notes
- AlloyDB replaced with ChromaDB + sentence-transformers (free, local, no server)
- Seed ChromaDB: python database/seed.py
- AgentCore migration layer in agentcore/ — deploy to AWS with sh agentcore/deploy/deploy-agentcore.sh
- Control tower runs on port 8080, agents on 8081/8082/8083
- Test report server on port 9090 — sh tests/run_tests.sh

## MCP Config (set in .env — never hardcode)
- MCP_USER_EMAIL — Gmail and Calendar confirmations go here
- GOOGLE_SHEET_ID — order log spreadsheet ID
- OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET / OAUTH_REFRESH_TOKEN

## Running Locally
sh run.sh            # auto-seeds ChromaDB, runs preflight tests, starts all 4 services
sh tests/run_tests.sh all   # full test suite + HTML report at http://localhost:9090

## Patterns
- All agents use A2A protocol — discoverable via /.well-known/agent-card.json
- WebSocket events drive the UI — add new events in app.py, handle in app.js
- Pre-flight tests run before every sh run.sh start
- Credentials always via os.environ.get() — never hardcoded
