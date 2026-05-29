# Project intent file — read by Claude Code at session start

## Project
Name: MultiAgentSupplyChainSystem
Stack: Python · FastAPI · Gemini 3 Flash · Prophet · AlloyDB · Cloud Run · Alpine.js

## What This System Does
Upload a warehouse shelf photo → 4 AI agents collaborate:
1. Vision Agent — counts items using Gemini 3 Flash + code execution
2. Supplier Agent — finds best matching part via AlloyDB ScaNN vector search
3. Reorder Agent — uses Prophet ML to predict days-to-stockout vs lead time
4. Logistics Agent — calculates shipping cost, carrier, ETA
Then: Gmail + Google Calendar + Google Sheets confirmation via MCP

## Current Sprint Goal
Intent: Add a forecast dashboard showing Prophet charts and CRITICAL/LOW/OK status for all 52 inventory items in real time

## Context
- Live demo: https://visual-commerce-demo-693699778723.us-central1.run.app
- Control tower runs on port 8080, agents on 8081/8082/8083
- Agent URLs must be set as Cloud Run env vars after every deploy
- Prophet usage data: agents/reorder-agent/data/usage_history.json (52 items)
- Reorder agent: agents/reorder-agent/forecaster.py
- Frontend: frontend/static/app.js + index.html (Alpine.js)
- Deploy: sh deploy/deploy.sh then update env vars with gcloud

## Patterns
- All agents use A2A protocol — discoverable via /.well-known/agent-card.json
- WebSocket events drive the UI — add new events in app.py, handle in app.js
- Reorder decision: days_until_stockout < lead_time_days → CRITICAL → order
- After every deploy: gcloud run services update visual-commerce-demo --region us-central1 --update-env-vars VISION_AGENT_URL=...,SUPPLIER_AGENT_URL=...,LOGISTICS_AGENT_URL=...

## Last Session (May 9)
Built: Prophet reorder agent — predicts stockout, gates order pipeline, UI card live
Commit: feat: reorder assessment card live in UI with Prophet ML

## Next Saturday Prep
- [ ] Write intent Friday night and update this file
- [ ] Pull latest main before 10 AM
- [ ] Verify app runs: curl https://visual-commerce-demo-693699778723.us-central1.run.app/api/health
- [ ] Join voice channel at 10 AM sharp
