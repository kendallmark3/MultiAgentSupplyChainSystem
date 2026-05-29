# Autonomous Supply Chain: Vision × Vector × Agents

An end-to-end **agentic supply chain system** — combining computer vision, semantic vector search, agent-to-agent orchestration, and real-world integrations to automate physical inventory management.

---

## Problem Statement

Most warehouse inventory systems rely on humans to physically count stock, identify shortages, and place reorders. This is slow, error-prone, and doesn't scale. This system replaces that entire workflow: upload a photo of a shelf, and the system autonomously counts what's there, finds the best-matched supplier, calculates shipping cost and ETA, and confirms the order via email, calendar, and a live spreadsheet — no human required.

---

## What It Does

Upload a photo of a warehouse shelf. Four specialized agents collaborate to:

1. **Count** what's on the shelf using deterministic computer vision
2. **Find** the best-matched supplier part via semantic vector search
3. **Calculate** shipping cost, carrier, and ETA
4. **Confirm** the order via Gmail, Google Calendar, and Google Sheets

---

## Architecture

```
User uploads image
        │
        ▼
Control Tower (8080)  ← WebSocket + FastAPI + PIL image compression
        │
        │  A2A Protocol (agent discovery via /.well-known/agent-card.json)
        │
        ├──▶ Vision Agent (8081)
        │       Gemini 3 Flash + Code Execution → deterministic item count + bounding boxes
        │       Gemini 2.5 Flash Lite → structured semantic search query
        │
        ├──▶ Supplier Agent (8082)
        │       sentence-transformers (local) → embedding generation, no API cost
        │       ChromaDB (embedded) → cosine vector search, no server, no cost
        │
        ├──▶ Logistics Agent (8083)
        │       Supplier location lookup → zone-based shipping calculation
        │       Returns: cost, carrier (FedEx/UPS), ETA, origin → destination
        │
        └──▶ MCP Integrations (post-order)
                Gmail → HTML order confirmation email
                Google Calendar → delivery date event
                Google Sheets → order log row appended
```

All agents expose `/.well-known/agent-card.json` following the **A2A Protocol** — discoverable and composable without hard-coded wiring.

---

## Agents

| Agent | Port | Technology | Responsibility |
|---|---|---|---|
| Vision Agent | 8081 | Gemini 3 Flash + Code Execution | Counts items deterministically from image, returns bounding boxes and semantic query |
| Supplier Agent | 8082 | ChromaDB + sentence-transformers (local) | Finds best-matched part and supplier via local vector similarity search — no cloud DB |
| Logistics Agent | 8083 | Zone-based shipping calculator | Calculates shipping cost, carrier, and ETA from supplier location to destination |
| Control Tower | 8080 | FastAPI + WebSocket | Orchestrates all agents via A2A, streams results live to UI |

---

## Why ChromaDB Replaced AlloyDB

The original system used AlloyDB AI + ScaNN for vector search. AlloyDB is a premium managed database — excellent for production at scale, expensive at POC scale.

**AlloyDB cost:** ~$130–160/month regardless of query volume (billed by uptime).
**ChromaDB cost:** $0. Runs embedded in the supplier agent process.

For a POC proving the concept to a client, ChromaDB delivers the same semantic search result for free. When the client commits and volume demands a managed service, the upgrade path is a single-file change in `inventory.py`.

---

## Security & Guardrails

**Vision Agent:**
- Image size capped at 10MB; unsupported MIME types rejected before any model call
- Prompt injection detection — 11 known injection patterns blocked
- Queries sanitized and truncated to 500 characters before reaching Gemini

**Supplier Agent:**
- Query length capped at 300 characters
- Character allowlist enforced (alphanumeric + common punctuation only)
- Disallowed characters stripped rather than rejected; empty result raises explicit error
- Internal stack traces never returned to caller — generic error message surfaced instead
- Confidence scores computed from ChromaDB cosine distance, not hardcoded

**Infrastructure:**
- All secrets loaded from `.env` / environment, excluded from Git
- Each agent runs as an isolated service; Control Tower is the only user-facing entry point
- CORS restricted to configured allowed origins only

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Vision | Gemini 3 Flash + Code Execution | Deterministic counting — model writes and runs Python, not guesses |
| Query Gen | Gemini 2.5 Flash Lite | Fast structured output with Pydantic models |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Free, local, no API key — 80MB download once, then cached |
| Vector DB | ChromaDB (embedded) | Free, open-source, persistent, no server, no cost |
| Backend | FastAPI + WebSocket | Async-native, real-time event streaming to UI |
| Agent Protocol | A2A | Plug-and-play agent discovery and composability |
| MCP | FastMCP | Standardized tool protocol for Gmail, Calendar, Sheets |
