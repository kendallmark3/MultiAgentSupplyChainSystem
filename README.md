![Python](https://img.shields.io/badge/Python-3.9+-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-green)
![Tests](https://img.shields.io/badge/Tests-7%20passing-brightgreen)
![Agents](https://img.shields.io/badge/Agents-4-orange)
![Cloud](https://img.shields.io/badge/Cloud-GCP-blue)

# Autonomous Supply Chain: Vision × Vector × Agents

An end-to-end **enterprise-grade agentic supply chain system** — combining computer vision, semantic vector search, governance, observability, logistics, and real-world MCP integrations to automate physical inventory management.

**Live Demo (GCP):** https://visual-commerce-demo-693699778723.us-central1.run.app/

---

## The Problem

Traditional warehouse inventory systems depend on humans to:
- Physically count items on shelves
- Manually look up supplier catalogs by SKU
- Decide when and what to reorder
- Calculate shipping costs and ETAs manually
- Send order confirmations and update spreadsheets

This is slow, error-prone, and unscalable. This system eliminates all of it.

---

## The Solution

Upload a photo of a warehouse shelf. Four specialized agents collaborate to:

1. **Count** what's on the shelf using deterministic computer vision
2. **Find** the best-matched supplier part via semantic vector search
3. **Calculate** shipping cost, carrier, and ETA
4. **Confirm** the order via Gmail, Google Calendar, and Google Sheets

No human in the loop. No manual SKU lookup. No guessing.

---

## Business Impact

| Problem | Without This System | With This System |
|---|---|---|
| Inventory counting | Manual, hours of labor, error-prone | Automated in seconds via vision AI |
| Stockout detection | Discovered after the fact | Detected proactively from shelf image |
| Supplier matching | Manual SKU lookup, catalog search | Semantic search across millions of parts |
| Shipping calculation | Manual carrier lookup, calls | Automated zone-based cost + ETA |
| Audit compliance | No trace of decisions | Full audit log per request and agent |
| Large order risk | No controls or approval gates | Human approval enforced automatically |
| Order confirmation | Manual emails, calendar entries | Automated via Gmail, Calendar, Sheets |

**KPIs this system improves:**
- Reduces inventory counting time from hours to seconds
- Eliminates manual supplier lookup entirely
- Automates shipping calculation and carrier selection
- Enforces compliance automatically with zero human overhead
- Provides full decision audit trail for enterprise governance
- Flags high-risk orders before they execute

---

## Enterprise Architecture

```
User uploads image
        │
        ▼
Governance Layer (agents/governance.py)
        Validates input, blocks prompt injection,
        enforces policies, logs every request
        │
        ▼
Control Tower (8080)  ← WebSocket + FastAPI + Observability
        Assigns workflow ID, traces all agents
        │
        │  A2A Protocol (agent discovery via /.well-known/agent-card.json)
        │
        ├──▶ Vision Agent (8081)
        │       Gemini 3 Flash + Code Execution → deterministic item count
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

The original system used **AlloyDB + Vertex AI text-embedding-005** for vector search. AlloyDB is production-grade — but it costs ~$130–160/month whether you run one query or ten thousand. For a POC proving the concept to a client, that's budget you cannot justify before closing the deal.

We replaced it with:

- **ChromaDB** — open-source, embedded, persistent vector database. Runs inside the supplier agent process. No server. No cloud account. No cost.
- **sentence-transformers `all-MiniLM-L6-v2`** — open-source embedding model. Runs locally. Downloads ~80MB once on first start, then cached. No API calls.

The supplier agent's public API (`get_embedding`, `find_supplier`) is identical — nothing else in the system changed.

**When you win the client and need to scale:** upgrade from ChromaDB → managed vector store (RDS Aurora pgvector, OpenSearch Serverless, or Bedrock Knowledge Base) is a single-file change in `inventory.py`.

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

When the client commits and you need to scale, you swap ChromaDB for a managed service. See [intents/agentcore.md](intents/agentcore.md) for the full migration guide.

---

## Agents

| Agent | Port | Technology | Responsibility |
|---|---|---|---|
| Vision Agent | 8081 | Gemini 3 Flash + Code Execution | Counts items deterministically from image, returns bounding boxes and semantic query |
| Supplier Agent | 8082 | ChromaDB + sentence-transformers (local) | Finds best-matched part and supplier via local vector similarity search |
| Logistics Agent | 8083 | Zone-based shipping calculator | Calculates shipping cost, carrier, and ETA from supplier location to destination |
| Control Tower | 8080 | FastAPI + WebSocket | Orchestrates all agents via A2A, streams results live to UI |

---

## MCP Integrations (post-order)

After an order is confirmed, the Control Tower triggers three real-world integrations via Google APIs — no manual steps.

- **Gmail** — sends an HTML order confirmation email
- **Google Calendar** — creates a delivery date event on the primary calendar
- **Google Sheets** — appends an order log row (order ID, part, supplier, cost, carrier, ETA, origin)

---

## Enterprise Features

### Governance Layer
Every request is validated before any agent runs:
- Image type and size validation (jpeg, png, webp only, max 5MB)
- Prompt injection detection — 11 known patterns blocked
- High-risk order flagging — quantities over 1000 require human approval
- Full audit logging with unique request IDs and timestamps

### Observability and Audit Trail
Every agent execution is fully traceable:
- Per-agent execution tracing (start time, duration, status)
- Workflow-level tracking across all agents via workflow ID
- Structured audit logs written to file for compliance
- Complete decision history retrievable by workflow ID
- Success and failure capture with full error context

### Security and Guardrails

**Vision Agent:**
- Image size capped at 10MB; unsupported MIME types rejected before any model call
- Prompt injection detection — 11 known injection patterns blocked (`ignore previous`, `act as`, `jailbreak`, etc.)
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
| Governance | Custom Python layer | Enterprise policy enforcement before agent execution |
| Observability | Structured logging + tracing | Full audit trail across every workflow |
| Vision | Gemini 3 Flash + Code Execution | Deterministic counting, not hallucination |
| Query Gen | Gemini 2.5 Flash Lite | Fast structured output with Pydantic models |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Free, local, no API key — downloads once and caches |
| Vector DB | ChromaDB (embedded) | Free, open-source, persistent, no server — runs in-process |
| Backend | FastAPI + WebSocket | Async-native, real-time event streaming to UI |
| Agent Protocol | A2A | Plug-and-play agent discovery and composability |
| MCP | FastMCP | Standardized tool protocol for Gmail, Calendar, Sheets |
| Integrations | Gmail, Google Calendar, Google Sheets | Real-world order confirmation and logging |

---

## Repository Structure

```
MultiAgentSupplyChainSystem/
├── run.sh                            # Launches all four services (auto-seeds ChromaDB on first run)
├── setup.sh                          # GCP environment setup (Vision Agent only)
├── .env.example                      # Config template
│
├── agents/
│   ├── governance.py                 # Input validation, prompt injection protection, policy enforcement
│   ├── observability.py              # Per-agent tracing, audit logging
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
├── tests/
│   ├── test_governance.py            # 4 governance tests
│   ├── test_observability.py         # 3 observability tests
│   └── test_supply_chain.py          # 97 pipeline tests — fully offline
│
└── deploy/
    ├── deploy.sh                     # GCP Cloud Run deployment
    └── cleanup.sh                    # Tears down GCP resources
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
git clone https://github.com/kendallmark3/MultiAgentSupplyChainSystem.git
cd MultiAgentSupplyChainSystem

# Copy and fill in environment config
cp .env.example .env
# Edit .env — only GOOGLE_CLOUD_PROJECT required to start

# Launch all services
# First run: auto-seeds ChromaDB with 20 inventory items (~80MB model download)
sh run.sh
```

Open **http://localhost:8080** for the Control Tower.

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

### Deploy to GCP Cloud Run

```bash
sh deploy/deploy.sh
```

---

## Running Tests

```bash
# Governance layer tests (4 tests)
python tests/test_governance.py

# Observability tests (3 tests)
python tests/test_observability.py

# Full pipeline tests — no API keys or credentials needed (97 tests)
pip install pytest
pytest tests/test_supply_chain.py -v
```

Expected output:
```
🔒 Running Governance Layer Tests...
✅ test_valid_request PASSED
✅ test_prompt_injection_blocked PASSED
✅ test_high_quantity_blocked PASSED
✅ test_invalid_image_type PASSED
✅ All governance tests passed!

🔍 Running Observability Tests...
✅ test_successful_agent_trace PASSED
✅ test_failed_agent_trace PASSED
✅ test_full_workflow_trace PASSED
✅ All observability tests passed!
```

---

## Branch Workflow

```
main
 └── dev
      └── feature/your-feature-name
```

- All changes are developed on feature branches
- Feature branches are merged into dev via pull request
- Dev is merged into main after review
- No direct pushes to main

---

## Design Decisions

**Why ChromaDB over AlloyDB for the POC?**
AlloyDB costs ~$130–160/month for the instance alone, billed by uptime not by usage. For a POC with 100 manual test runs per month, you're paying $150 to run the equivalent of $0.50 in actual queries. ChromaDB runs embedded in the supplier agent — same cosine vector search, same confidence scoring, zero cost. When the POC converts to production and volume justifies a managed service, the upgrade is a single-file swap.

**Why a governance layer?**
Enterprises cannot allow agents to run unchecked. Every request must be validated, policy-enforced, and logged before any agent executes.

**Why observability?**
Decisions without audit trails are liabilities. Every agent action is traceable by workflow ID for compliance, debugging, and enterprise reporting.

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

---

## License
Apache-2.0
