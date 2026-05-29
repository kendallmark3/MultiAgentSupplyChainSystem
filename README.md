# Autonomous Supply Chain: Vision × Vector × Agents

An end-to-end agentic supply chain system — combining computer vision, semantic vector search, agent-to-agent orchestration, and real-world integrations to automate physical inventory management.

**Live Demo (GCP):** https://visual-commerce-demo-693699778723.us-central1.run.app/

---

## The Problem We're Solving

Most warehouse inventory systems rely on humans to physically count stock, identify shortages, and place reorders. This is slow, error-prone, and doesn't scale.

This system replaces that entire workflow: upload a photo of a shelf, and the system autonomously counts what's there, finds the best-matched supplier, calculates shipping cost and ETA, and confirms the order via email, calendar, and a live spreadsheet — no human required.

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
        │       sentence-transformers (local) → embedding generation, zero cost
        │       ChromaDB (embedded) → cosine vector search, zero cost, no server
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

## Why ChromaDB Replaced AlloyDB

The original system used **AlloyDB + Vertex AI text-embedding-005** for vector search. AlloyDB is a powerful managed database, but it costs ~$130–160/month whether you run one query or ten thousand. For a POC proving the concept to a client, that's budget you cannot justify.

We replaced it with:

- **ChromaDB** — open-source, embedded, persistent vector database. Runs inside the supplier agent container. No server. No cloud account. No cost.
- **sentence-transformers `all-MiniLM-L6-v2`** — open-source embedding model. Runs locally. Downloads ~80MB once on first start, then cached. No API calls, no cost.

The supplier agent's public API (`get_embedding`, `find_supplier`) is identical — nothing else in the system changed. The vector search behavior and confidence scoring work the same way. The only difference is the bill.

**If you win the client and need to scale:** the upgrade path from ChromaDB → managed vector store (RDS Aurora pgvector, OpenSearch Serverless, or Bedrock Knowledge Base) is a single-file change in `inventory.py`. The rest of the system stays the same.

---

## POC Cost: GCP vs AWS AgentCore

This is the number that matters for a POC conversation with a client.

| | GCP (current live site) | AWS AgentCore + ChromaDB |
|---|---|---|
| Vector database | AlloyDB: **~$145/month** (always on) | ChromaDB: **$0** (embedded) |
| Embeddings | Vertex AI: ~$0.01/month | sentence-transformers: **$0** (local) |
| Vision model | Gemini 3 Flash: ~$2–3/month | Claude 3.5 Sonnet: ~$2/month |
| Compute | Cloud Run: ~$2–5/month | AgentCore Runtime: ~$1–3/month |
| **Total (~100 runs/mo)** | **~$150–175/month** | **~$3–6/month** |

The POC runs on AWS for under **$6/month**. The GCP live demo costs **$150+ per month** for the same workload — almost entirely AlloyDB instance uptime.

When the client commits and you need to scale, you swap ChromaDB for a managed service. That conversation is much easier to have after you've proven the system works.

---

## Agents

| Agent | Port | Technology | Responsibility |
|---|---|---|---|
| Vision Agent | 8081 | Gemini 3 Flash + Code Execution | Counts items deterministically from image, returns bounding boxes and semantic query |
| Supplier Agent | 8082 | ChromaDB + sentence-transformers (local) | Finds best-matched part and supplier via local vector similarity search |
| Logistics Agent | 8083 | Zone-based shipping calculator | Calculates shipping cost, carrier, and ETA from supplier location to destination |
| Control Tower | 8080 | FastAPI + WebSocket | Orchestrates all agents via A2A, streams results live to UI |

---

## MCP Integrations

After an order is confirmed, the Control Tower triggers three real-world integrations via Google APIs — no manual steps.

```
Order confirmed by Control Tower
        │
        ├──▶ send_gmail_email
        │       Sends an HTML order confirmation to the supplier
        │
        ├──▶ create_calendar_event
        │       Creates a delivery date event on Google Calendar
        │
        └──▶ append_google_sheet_row
                Appends a row to the order log spreadsheet
```

| Tool | Service | What it does |
|---|---|---|
| `send_gmail_email` | Gmail API | Sends HTML order confirmation email |
| `create_calendar_event` | Google Calendar API | Creates a delivery date event |
| `append_google_sheet_row` | Google Sheets API | Appends order details as a new row |

---

## Security & Guardrails

**Vision Agent:**
- Image size capped at 10MB; unsupported MIME types rejected before any model call
- Prompt injection detection — 11 known patterns blocked (`ignore previous`, `act as`, `jailbreak`, etc.)
- Queries sanitized and truncated to 500 characters before reaching Gemini

**Supplier Agent:**
- Query length capped at 300 characters
- Character allowlist enforced (alphanumeric + common punctuation only)
- Disallowed characters stripped rather than rejected; empty result raises explicit error
- Internal stack traces never returned to caller — generic error message surfaced instead
- Confidence scores computed from ChromaDB cosine distance, not hardcoded

**Infrastructure:**
- All secrets loaded from `.env` / environment, excluded from Git
- Each agent runs as an isolated service on a separate port; Control Tower is the only user-facing entry point
- CORS restricted to configured allowed origins only

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Vision | Gemini 3 Flash + Code Execution | Deterministic counting — model writes and runs Python, not guesses |
| Query Gen | Gemini 2.5 Flash Lite | Fast structured output with Pydantic models |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Free, local, no API key — downloads once and caches |
| Vector DB | ChromaDB (embedded) | Free, open-source, persistent, no server — runs in-process |
| Backend | FastAPI + WebSocket | Async-native, real-time event streaming to UI |
| Agent Protocol | A2A | Plug-and-play agent discovery and composability |
| MCP | FastMCP | Standardized tool protocol for Gmail, Calendar, Sheets |
| Integrations | Gmail, Google Calendar, Google Sheets APIs | Real-world order confirmation and logging |

---

## Repository Structure

```
MultiAgentSupplyChainSystem/
├── run.sh                            # Launches all four services (auto-seeds ChromaDB on first run)
├── setup.sh                          # GCP environment setup (Vision Agent only)
├── .env.example                      # Config template
│
├── agents/
│   ├── vision-agent/
│   │   ├── agent.py                  # Gemini 3 Flash vision + bounding box logic
│   │   ├── agent_executor.py         # A2A server executor
│   │   └── main.py                   # FastAPI entrypoint (:8081)
│   ├── supplier-agent/
│   │   ├── inventory.py              # ChromaDB + sentence-transformers vector search
│   │   ├── agent_executor.py         # A2A executor + input guardrails
│   │   └── main.py                   # FastAPI entrypoint (:8082)
│   └── logistics-agent/
│       ├── shipping.py               # Zone-based shipping cost + ETA calculator
│       ├── agent_executor.py         # A2A executor
│       └── main.py                   # FastAPI entrypoint (:8083)
│
├── frontend/
│   ├── app.py                        # Control Tower: orchestration + WebSocket + MCP integrations
│   ├── mcp_server.py                 # FastMCP server — Gmail, Calendar, Sheets tools
│   └── static/                       # UI (index.html, app.js, styles.css)
│
├── database/
│   ├── seed.py                       # Populates ChromaDB with 20 inventory items
│   ├── seed_data.sql                 # Schema reference + 20 inventory items (SQL archive)
│   └── chroma_db/                    # ChromaDB persistent storage (auto-created on first run)
│
├── agentcore/                        # AWS AgentCore migration layer
│   ├── agents/                       # AgentCore Runtime handlers (same A2A interface)
│   ├── config/agents.yaml            # Agent + tool definitions for Gateway
│   ├── deploy/deploy-agentcore.sh    # AWS deployment script
│   └── setup/provision_knowledge_base.py  # Optional: Bedrock KB for production scale
│
├── intents/
│   └── agentcore.md                  # Migration guide: why, how, and POC cost breakdown
│
├── deploy/
│   ├── deploy.sh                     # GCP Cloud Run deployment
│   └── cleanup.sh                    # Tears down GCP resources
│
└── tests/
    └── test_supply_chain.py          # 97 tests — run completely offline, no credentials needed
```

---

## Getting Started

### Prerequisites

- Python 3.9+
- Google Cloud Project with billing enabled (for Vision Agent — Gemini/Vertex AI)
- `gcloud` CLI configured

No database server, no cloud vector store, no AlloyDB account needed.

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID (Vision Agent) |
| `GOOGLE_CLOUD_LOCATION` | No | Vertex AI region (default: `global`) |
| `CHROMA_DB_PATH` | No | Path for ChromaDB storage (default: `database/chroma_db`) |
| `EMBEDDING_MODEL` | No | sentence-transformers model (default: `all-MiniLM-L6-v2`) |
| `OAUTH_CLIENT_ID` | Yes (MCP) | Google OAuth client ID for Gmail/Calendar/Sheets |
| `OAUTH_CLIENT_SECRET` | Yes (MCP) | Google OAuth client secret |
| `OAUTH_REFRESH_TOKEN` | Yes (MCP) | OAuth refresh token |

### Run Locally

```bash
# Clone
git clone https://github.com/kendallmark3/MultiAgentSupplyChainSystem.git
cd MultiAgentSupplyChainSystem

# Copy and fill in environment config
cp .env.example .env
# Edit .env — only GOOGLE_CLOUD_PROJECT and Gemini key required to start

# Launch all services
# On first run: automatically seeds ChromaDB with 20 inventory items
sh run.sh
```

Open **http://localhost:8080** for the Control Tower.

The first run downloads the `all-MiniLM-L6-v2` model (~80MB) and seeds ChromaDB. Every run after that starts instantly from the local cache.

### Pre-seed the database (optional)

```bash
pip install chromadb sentence-transformers
python database/seed.py
```

### Deploy to AWS AgentCore

```bash
cp agentcore/.env.aws.example .env.aws
# Fill in AWS_REGION, AWS_ACCOUNT_ID, AGENTCORE_RUNTIME_ROLE_ARN
sh agentcore/deploy/deploy-agentcore.sh
```

See [intents/agentcore.md](intents/agentcore.md) for the full migration guide and cost breakdown.

### Deploy to GCP Cloud Run (original)

```bash
sh deploy/deploy.sh
```

---

## Running Tests

No API keys or cloud credentials needed — all 97 tests run completely offline.

```bash
pip install pytest
pytest tests/test_supply_chain.py -v
```

| Test Class | Count | What it covers |
|---|---|---|
| `TestValidateImageInput` | 11 | Valid types, empty bytes, 10MB size limit, bad MIME types |
| `TestSanitizeVisionQuery` | 13 | All 11 injection patterns, truncation, None/empty inputs |
| `TestExtractBoundingBoxes` | 6 | Valid JSON, missing block, malformed JSON, empty array |
| `TestSanitizeSupplierQuery` | 10 | SQL injection, XSS attempts, truncation, allowlist chars |
| `TestComputeConfidence` | 9 | Distance 0→100%, distance 2→0%, None handling, clamping |
| `TestEstimateWeight` | 8 | All item types, default fallback, case insensitivity |
| `TestGetSupplierLocation` | 6 | Exact match, fuzzy match, unknown supplier default |
| `TestCalculateShipping` | 15 | All zones, handling fees, breakdown totals, ETA labels |
| `TestMcpTools` | 6 | Gmail, Calendar, Sheets confirmation contracts |
| `TestEndToEndLogic` | 5 | Full pipeline: vision → sanitize → logistics |
| **Total** | **97** | |

---

## Design Decisions

**Why ChromaDB over AlloyDB for the POC?**
AlloyDB costs ~$130–160/month for the instance alone, billed by uptime not by usage. For a POC with 100 manual test runs per month, you're paying $150 to run the equivalent of $0.50 in actual queries. ChromaDB runs embedded in the supplier agent — same cosine vector search, same confidence scoring, zero cost. When the POC converts to production and volume justifies a managed service, the upgrade is a single-file swap.

**Why code execution for vision?**
Asking an LLM to count items and return a number is unreliable. Giving it a Python interpreter and asking it to write counting logic, then run it, produces deterministic, auditable results with exact bounding boxes per detected object.

**Why A2A Protocol?**
Hard-coding agent interactions couples the system too tightly. A2A lets each agent advertise its capabilities via a standard card, making the system composable — swap the supplier agent, add a pricing agent, or integrate a new logistics provider without touching orchestration code.

**Why a separate Logistics Agent?**
Shipping calculation is deterministic and domain-specific (zone maps, carrier rules, weight tables). Keeping it as a dedicated A2A agent rather than inline logic in the Control Tower keeps it independently testable and replaceable.

**Why MCP for integrations?**
MCP provides a standardized interface for connecting AI agents to external tools. Swap Gmail for Slack, or Sheets for Notion, without touching agent orchestration code.

---

## Troubleshooting

**Port conflicts**
```bash
lsof -ti:8080 | xargs kill -9
lsof -ti:8081 | xargs kill -9
lsof -ti:8082 | xargs kill -9
lsof -ti:8083 | xargs kill -9
```

**ChromaDB collection empty on first run**
`run.sh` auto-seeds on startup. To manually re-seed:
```bash
python database/seed.py
```

**Agent health checks**
```bash
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
curl http://localhost:8080/api/health
```

**sentence-transformers slow on first start**
The `all-MiniLM-L6-v2` model (~80MB) downloads once and caches in `~/.cache/`. Every subsequent start is instant.

**Vertex AI permission denied (Vision Agent)**
```bash
gcloud services enable aiplatform.googleapis.com
```

---

## References

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [sentence-transformers](https://www.sbert.net/)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [A2A Protocol](https://google.github.io/A2A/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [Gemini Code Execution](https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/code-execution-api)
