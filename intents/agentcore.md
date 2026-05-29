# Migrating to Amazon Bedrock AgentCore — POC Strategy & Cost Guide

## The Situation

This system was built on Google Cloud Platform: Gemini models via Vertex AI for vision, AlloyDB AI for vector search, and Google Cloud Run for hosting. It works well as a demo.

**The problem:** the live GCP site costs ~$150/month — almost entirely AlloyDB instance uptime. That's the bill whether you run one test or a thousand. For a POC where you haven't closed the client yet, that's money you're burning to keep a demo alive.

**What we did:** replaced AlloyDB with ChromaDB (free, embedded, open-source) and Vertex AI embeddings with sentence-transformers (free, local). The system runs identically. The supplier agent still does cosine vector search and returns the same confidence scores. The web interface looks the same. The monthly cost dropped from ~$150 to under $6.

**What this document covers:**
1. Why move from GCP → AWS AgentCore (not just "Bedrock direct")
2. The real monthly cost — with the new numbers after ChromaDB
3. Step-by-step migration path
4. POC → production upgrade path: when and how to scale the database

---

## The Cost Case (This Is the Obvious Choice)

### Before (GCP + AlloyDB)

| Service | Monthly cost | Notes |
|---|---|---|
| AlloyDB instance | ~$130–160/month | Always on. Billed by uptime, not usage. |
| Cloud Run (4 services) | ~$2–5/month | Scale to zero |
| Gemini 3 Flash (Vision) | ~$2–3/month | ~100 runs |
| Vertex AI Embeddings | ~$0.01/month | ~100 queries |
| **Total** | **~$135–170/month** | |

### After (AWS AgentCore + ChromaDB)

| Service | Monthly cost | Notes |
|---|---|---|
| ChromaDB | **$0** | Embedded in-process, no server |
| sentence-transformers | **$0** | Local model, no API calls |
| Claude 3.5 Sonnet (Vision) | ~$2/month | ~100 runs |
| Claude 3 Haiku (Logistics) | ~$0.10/month | Deterministic, rarely called |
| AgentCore Runtime (4 agents) | ~$1–3/month | Scale to zero |
| **Total** | **~$3–6/month** | |

**97% cost reduction for the same POC functionality.**

The GCP site costs ~$150/month. The AWS site costs ~$5/month. The only thing that changed is the vector database — and the client cannot tell the difference in the demo.

### Why the Numbers Changed So Dramatically

The original AlloyDB-to-OpenSearch-Serverless comparison showed both platforms at ~$150–180/month. That analysis was honest at the time — both have always-on managed database costs.

What changed: we replaced the managed vector database entirely. ChromaDB runs embedded in the supplier agent container. No separate database instance. No always-on cost. OpenSearch Serverless has a minimum spend of ~$175/month just like AlloyDB did. ChromaDB has none.

This is the move that makes AWS the obvious choice for the POC: combine AgentCore Runtime (scale-to-zero compute) with ChromaDB (zero-cost vector store) and you're paying only for the model calls you actually make.

---

## Why AgentCore Over Bedrock Direct

"Bedrock direct" means swapping `google.genai` for `boto3.client('bedrock-runtime')` and managing everything else yourself — your own agent loop, retry logic, memory, tool routing, scaling, observability, IAM. You traded one cloud's primitives for another's but kept all the operational complexity.

AgentCore absorbs that complexity:

| Concern | Bedrock Direct | AgentCore |
|---|---|---|
| Agent execution loop | You write and maintain it | Managed |
| Memory (session + long-term) | DIY | AgentCore Memory |
| Tool routing | Hardcoded in orchestration | AgentCore Gateway (MCP-compatible) |
| Code execution sandbox | Your container | AgentCore Code Interpreter |
| Agent discovery | Custom A2A implementation | Gateway — IAM-secured, auto-registered |
| Scaling | Your ECS/Lambda config | Runtime — scales to zero |
| IAM / Auth | Manual session management | Native IAM roles per agent |
| Observability | CloudWatch + custom logging | Built-in traces, model invocation logs |

For a POC, "Bedrock direct" means you're still writing infrastructure code. AgentCore means you write agent logic and AWS runs the rest.

---

## Architecture: Current vs Target

### Current (GCP, live today)
```
User uploads image
        │
        ▼
Control Tower (FastAPI :8080) — WebSocket
        │  A2A HTTP discovery
        ├──▶ Vision Agent (:8081) — Gemini 3 Flash + Code Execution
        ├──▶ Supplier Agent (:8082) — ChromaDB + sentence-transformers (LOCAL)
        ├──▶ Logistics Agent (:8083) — deterministic zone calculator
        └──▶ MCP Server — Gmail / Calendar / Sheets
```

### Target (AWS AgentCore)
```
User uploads image
        │
        ▼
Control Tower — AgentCore Runtime (Supervisor)
        │  AgentCore Gateway (IAM-secured, MCP-compatible)
        ├──▶ Vision Agent — AgentCore Runtime + Code Interpreter
        │       Model: Claude 3.5 Sonnet
        ├──▶ Supplier Agent — AgentCore Runtime
        │       ChromaDB embedded (POC) OR Bedrock Knowledge Base (production)
        ├──▶ Logistics Agent — AgentCore Runtime (stateless, no model)
        └──▶ AgentCore Tools — Gmail / Calendar / Sheets MCP adapters
```

**What stays the same across both:** local run interface (`sh run.sh`), same ports (8080–8083), same frontend UI, same WebSocket event types, same A2A discovery cards.

---

## Prerequisites

### AWS
- AWS account with Bedrock model access enabled
- AWS CLI v2 configured: `aws configure`
- IAM user/role with: `bedrock:*`, `agentcore:*`, `iam:PassRole`
- AgentCore CLI: `pip install amazon-bedrock-agentcore-cli`

### Bedrock model access
Go to **AWS Console → Bedrock → Model access** and enable:
- `anthropic.claude-3-5-sonnet-20241022-v2:0` (Vision Agent)
- `anthropic.claude-3-haiku-20240307-v1:0` (Logistics Agent)

### Python
- Python 3.11+
- Existing dependencies already installed via `sh run.sh`

---

## Step-by-Step Migration

### Step 1 — Set up your AWS environment

```bash
cp agentcore/.env.aws.example .env.aws
# Fill in: AWS_REGION, AWS_ACCOUNT_ID, AGENTCORE_RUNTIME_ROLE_ARN
set -a && source .env.aws && set +a
```

### Step 2 — Install AgentCore dependencies

```bash
pip install -r agentcore/requirements.txt
```

### Step 3 — Verify the supplier agent locally

ChromaDB is already running locally. Confirm it works:

```bash
python agents/supplier-agent/inventory.py
```

No AWS credentials needed for this step — ChromaDB runs fully local.

### Step 4 — Test Vision Agent locally (Claude replaces Gemini)

```bash
cd agentcore/agents/vision-agent
python agentcore_handler.py --image ../../../test-images/preview.webp
```

### Step 5 — Test Supplier Agent locally (ChromaDB, unchanged)

```bash
cd agentcore/agents/supplier-agent
python agentcore_handler.py --query "cardboard shipping boxes warehouse"
```

### Step 6 — Test Logistics Agent locally

```bash
cd agentcore/agents/logistics-agent
python agentcore_handler.py --supplier "Acme Industrial" --destination "New York, NY"
```

### Step 7 — Run full system locally

```bash
sh run.sh
```

Open http://localhost:8080 — identical to today.

### Step 8 — Deploy to AWS

```bash
sh agentcore/deploy/deploy-agentcore.sh
```

7 steps automated: IAM roles, four agent deployments, Gateway creation, agent registration.

### Step 9 — Verify

```bash
curl https://<your-endpoint>/api/health
pytest tests/test_supply_chain.py -v  # 97 tests, fully offline
```

---

## POC → Production: Scaling the Vector Store

ChromaDB is the right call for the POC. When the client commits and you need SLA guarantees, audit trails, and millions of parts, here is the upgrade path — one file to change each time.

| Stage | Vector store | Monthly cost | Change required |
|---|---|---|---|
| **POC (now)** | ChromaDB embedded | **$0** | Already done |
| Small production | PostgreSQL + pgvector (RDS) | ~$30–50/month | Swap client in `inventory.py` |
| Mid-scale AWS | Aurora Serverless v2 + pgvector | ~$5–20/month idle | Same swap, different DSN |
| Large-scale AWS | Bedrock Knowledge Base | ~$0.05/1K queries | Use `agentcore/agents/supplier-agent/agentcore_handler.py` |

The A2A interface, agent_executor.py, control tower, and frontend are untouched in all cases. The upgrade is always contained to `agents/supplier-agent/inventory.py`.

---

## File Structure

```
MultiAgentSupplyChainSystem/
├── run.sh                              # Unchanged — auto-seeds ChromaDB on first run
├── .env.aws                            # Your AWS config (gitignored)
│
├── agentcore/                          # AgentCore migration layer
│   ├── requirements.txt                # boto3, amazon-bedrock-agentcore, anthropic
│   ├── .env.aws.example                # AWS environment template
│   ├── config/agents.yaml              # Declarative agent + tool definitions
│   ├── setup/provision_knowledge_base.py  # Optional: Bedrock KB for production
│   ├── agents/
│   │   ├── vision-agent/agentcore_handler.py     # Claude 3.5 Sonnet + Code Interpreter
│   │   ├── supplier-agent/agentcore_handler.py   # ChromaDB (POC) or Bedrock KB (prod)
│   │   ├── logistics-agent/agentcore_handler.py  # Wraps existing shipping.py
│   │   └── control-tower/agentcore_handler.py    # Supervisor + WebSocket bridge
│   └── deploy/
│       ├── deploy-agentcore.sh         # Full AWS deployment (7 steps)
│       └── cleanup-agentcore.sh        # Teardown
│
└── intents/
    └── agentcore.md                    # This file
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `AWS_REGION` | Yes | Bedrock-enabled region (e.g. `us-east-1`) |
| `AWS_ACCOUNT_ID` | Yes | 12-digit AWS account ID |
| `BEDROCK_VISION_MODEL_ID` | No | Default: `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `BEDROCK_LOGISTICS_MODEL_ID` | No | Default: `anthropic.claude-3-haiku-20240307-v1:0` |
| `AGENTCORE_RUNTIME_ROLE_ARN` | Yes | IAM role ARN for AgentCore Runtime |
| `AGENTCORE_GATEWAY_ID` | Yes (post-deploy) | Output from first deploy |
| `CHROMA_DB_PATH` | No | Default: `database/chroma_db` |
| `OAUTH_CLIENT_ID` | Yes (MCP) | Google OAuth (same as before) |
| `OAUTH_CLIENT_SECRET` | Yes (MCP) | Google OAuth (same as before) |
| `OAUTH_REFRESH_TOKEN` | Yes (MCP) | Google OAuth (same as before) |

---

## Troubleshooting

**`NoRegionError` on boto3 calls**
```bash
export AWS_REGION=us-east-1
```

**`AccessDeniedException` on Bedrock model invocation**
Go to Bedrock console → Model access → request access for the model IDs above. Wait ~5 minutes.

**ChromaDB collection empty**
```bash
python database/seed.py
```

**Port conflicts**
```bash
lsof -ti:8080 | xargs kill -9 && lsof -ti:8081 | xargs kill -9
lsof -ti:8082 | xargs kill -9 && lsof -ti:8083 | xargs kill -9
```

---

## References

- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-runtime.html)
- [AgentCore Gateway](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-gateway.html)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [sentence-transformers](https://www.sbert.net/)
- [A2A Protocol](https://google.github.io/A2A/)
