# Migrating to Amazon Bedrock AgentCore — Enterprise Implementation Guide

## Why This Migration

This system currently runs on Google Cloud Platform: Gemini models via Vertex AI, AlloyDB for vector search, and Google Cloud Run for hosting. It works. But it is wired directly to GCP primitives — the agents talk to Vertex AI SDK, AlloyDB Connector, and FastMCP in ways that tie every scaling, security, and observability decision to custom code you have to maintain.

**Bedrock direct** (the naive AWS swap) means calling `boto3.client('bedrock-runtime').invoke_model(...)` in place of the Gemini SDK. You still own the agent loop, memory management, tool routing, retry logic, IAM integration, observability hooks, and deployment packaging. You traded one cloud's primitives for another's, but kept all the operational complexity.

**AgentCore** is the managed runtime layer that absorbs that complexity. AWS runs the agent loop, handles memory persistence, routes tool calls, enforces IAM, emits traces to CloudWatch, and auto-scales the containers. You write agent logic. AWS runs the infrastructure.

### Why you should move to AgentCore over Bedrock direct

| Concern | Bedrock Direct | AgentCore |
|---|---|---|
| Agent execution loop | You write and maintain it | Managed by AWS |
| Memory (session + long-term) | DIY (Redis, AlloyDB, DynamoDB) | AgentCore Memory — semantic + episodic, built-in |
| Tool routing | Hardcoded in orchestration code | AgentCore Gateway — MCP-compatible, declarative |
| Code execution sandbox | Gemini Code Execution (GCP) | AgentCore Code Interpreter — AWS-managed sandbox |
| Agent discovery | A2A protocol (custom cards, HTTP) | AgentCore Gateway — IAM-secured, auto-registered |
| Scaling | Cloud Run concurrency config | AgentCore Runtime — scales to zero, auto-provisions |
| IAM / Auth | Manual boto3 session management | Native AWS IAM roles per agent, no credential code |
| Observability | CloudWatch + custom logging | Built-in traces, spans, model invocation logs |
| Compliance | You configure encryption, audit | SOC 2, HIPAA, FedRAMP inherited from managed service |
| Multi-agent orchestration | HTTP calls between FastAPI services | AgentCore Supervisor — declarative agent graph |

**Bottom line:** For a production supply chain system, AgentCore removes the undifferentiated heavy lifting. The agents in this system (vision, supplier, logistics, control tower) map directly onto AgentCore's primitives: Code Interpreter for vision counting, Knowledge Base for supplier vector search, managed tools for MCP integrations, and the Supervisor for the control tower orchestration.

---

## Architecture: Current vs Target

### Current (GCP)
```
User uploads image
        │
        ▼
Control Tower (FastAPI :8080) — WebSocket + PIL
        │  A2A HTTP (/.well-known/agent-card.json)
        ├──▶ Vision Agent (:8081) — Vertex AI Gemini 3 Flash + Code Execution
        ├──▶ Supplier Agent (:8082) — AlloyDB ScaNN + Vertex AI text-embedding-005
        ├──▶ Logistics Agent (:8083) — deterministic zone calculator
        └──▶ MCP Server — FastMCP → Gmail / Calendar / Sheets
```

### Target (AWS AgentCore)
```
User uploads image
        │
        ▼
Control Tower — AgentCore Runtime (Supervisor agent)
        │  AgentCore Gateway (IAM-secured, MCP-compatible)
        ├──▶ Vision Agent — AgentCore Runtime + Code Interpreter
        │       Model: Claude 3.5 Sonnet / Amazon Nova Pro
        ├──▶ Supplier Agent — AgentCore Runtime + Knowledge Base
        │       Embeddings: Titan Embeddings v2
        │       Vector store: OpenSearch Serverless
        ├──▶ Logistics Agent — AgentCore Runtime (stateless)
        │       Model: Claude 3 Haiku (fast, low-cost)
        └──▶ AgentCore Tools — MCP Gateway
                Gmail / Calendar / Sheets via Lambda tool adapters
```

**What stays the same:** The local run interface is identical — `sh run.sh` starts all four services on the same ports (8080–8083). The frontend UI, WebSocket protocol, and A2A discovery cards are preserved. Only the model backends and deployment target change.

---

## Prerequisites

### AWS
- AWS account with Bedrock model access enabled (Claude 3.5 Sonnet, Titan Embeddings v2)
- AWS CLI v2 configured: `aws configure`
- IAM user or role with: `bedrock:*`, `s3:*`, `opensearchserverless:*`, `agentcore:*`, `iam:PassRole`
- AgentCore CLI: `pip install amazon-bedrock-agentcore-cli`

### Python
- Python 3.11+ (AgentCore Runtime requires 3.11)
- Existing project dependencies still installed

### Models to enable in Bedrock console
Go to **AWS Console → Bedrock → Model access** and request access to:
- `anthropic.claude-3-5-sonnet-20241022-v2:0` (Vision Agent)
- `anthropic.claude-3-haiku-20240307-v1:0` (Logistics Agent)
- `amazon.titan-embed-text-v2:0` (Supplier Agent embeddings)

---

## Step-by-Step Migration

### Step 1 — Set up your AWS environment file

Copy and fill in `agentcore/.env.aws.example` → `.env.aws`:

```bash
cp agentcore/.env.aws.example .env.aws
# Edit .env.aws with your AWS account values
```

Source it before running locally:
```bash
set -a && source .env.aws && set +a
```

Key values needed:
- `AWS_REGION` — where your Bedrock models are enabled (e.g. `us-east-1`)
- `AWS_ACCOUNT_ID` — your 12-digit account ID
- `BEDROCK_KNOWLEDGE_BASE_ID` — created in Step 3
- OAuth tokens for Gmail/Calendar/Sheets (same as before, stored in AWS Secrets Manager in production)

---

### Step 2 — Install AgentCore dependencies

```bash
pip install -r agentcore/requirements.txt
```

This installs:
- `amazon-bedrock-agentcore` — Runtime SDK
- `amazon-bedrock-agentcore-cli` — Deployment CLI
- `boto3` >= 1.34 — AWS SDK
- `anthropic` — Claude SDK (direct calls during local dev)

---

### Step 3 — Provision the Supplier Agent Knowledge Base

This replaces AlloyDB + ScaNN. Run once to set up:

```bash
python agentcore/setup/provision_knowledge_base.py
```

What it does:
1. Creates an OpenSearch Serverless collection named `supply-chain-parts`
2. Creates a Bedrock Knowledge Base pointing at that collection
3. Seeds it from `database/seed_data.sql` (converts rows → documents)
4. Prints `BEDROCK_KNOWLEDGE_BASE_ID` — add this to `.env.aws`

**Why OpenSearch Serverless over AlloyDB ScaNN:** No instance to manage or patch, scales to zero when idle, native Bedrock Knowledge Base integration means embedding generation and retrieval are handled by the service — you query with plain text and get ranked results back.

---

### Step 4 — Test Vision Agent locally (Claude + Code Interpreter)

The Vision Agent swaps Gemini 3 Flash for Claude 3.5 Sonnet with AgentCore Code Interpreter:

```bash
cd agentcore/agents/vision-agent
python agentcore_handler.py --local --image ../../test-images/preview.webp
```

Expected output matches the current format: `item_count`, `item_type`, `bounding_boxes`, `search_query`.

**Why Code Interpreter over Gemini Code Execution:** AgentCore Code Interpreter runs in an AWS-managed sandbox with IAM isolation. The model writes Python to count boxes, the sandbox executes it, and the result is deterministic — same guarantee as Gemini Code Execution but inside your AWS security perimeter.

---

### Step 5 — Test Supplier Agent locally (Bedrock Knowledge Base)

```bash
cd agentcore/agents/supplier-agent
python agentcore_handler.py --local --query "cardboard shipping boxes warehouse"
```

The handler calls `boto3.client('bedrock-agent-runtime').retrieve_and_generate()` against your Knowledge Base. No embedding code to maintain — the service handles Titan v2 embedding + ScaNN retrieval.

---

### Step 6 — Test Logistics Agent locally

No model change needed — Logistics is deterministic zone math. The AgentCore handler is a thin wrapper that keeps the same `shipping.py` logic and exposes it via AgentCore Runtime instead of FastAPI:

```bash
cd agentcore/agents/logistics-agent
python agentcore_handler.py --local --supplier "Acme Industrial" --destination "New York, NY"
```

---

### Step 7 — Test Control Tower locally (Supervisor)

The Control Tower becomes an AgentCore Supervisor that orchestrates the other three agents via AgentCore Gateway instead of raw A2A HTTP:

```bash
cd agentcore/agents/control-tower
python agentcore_handler.py --local
```

The WebSocket server still starts on `:8080`. The UI and real-time streaming behavior is unchanged.

---

### Step 8 — Run the full system locally (same as before)

```bash
sh run.sh
```

`run.sh` detects the `.env.aws` file and routes through the AgentCore handlers instead of the GCP handlers. All four services start on their original ports. Open `http://localhost:8080` — the interface is identical.

---

### Step 9 — Deploy to your AWS instance

```bash
sh agentcore/deploy/deploy-agentcore.sh
```

What this script does, in order:

1. **Packages each agent** into an AgentCore Runtime deployment bundle
2. **Creates IAM roles** — one per agent, least-privilege Bedrock + CloudWatch permissions
3. **Deploys Vision Agent** to AgentCore Runtime with Code Interpreter enabled
4. **Deploys Supplier Agent** to AgentCore Runtime with Knowledge Base binding
5. **Deploys Logistics Agent** to AgentCore Runtime (stateless, no model binding)
6. **Registers all agents** in AgentCore Gateway (replaces A2A card discovery)
7. **Deploys Control Tower** as AgentCore Supervisor agent with Gateway routing
8. **Configures AgentCore Tools** — MCP wrappers for Gmail, Calendar, Sheets
9. **Outputs the public endpoint URL** — your equivalent of the Cloud Run URL

Deployment targets your AWS account's assigned region. The EC2/ECS instance already associated with this local setup receives the AgentCore Runtime containers automatically via the IAM instance profile.

---

### Step 10 — Verify the deployment

```bash
# Health checks — same endpoints, new backends
curl https://<your-agentcore-endpoint>/api/health
curl https://<your-agentcore-endpoint>/api/health/vision
curl https://<your-agentcore-endpoint>/api/health/supplier
curl https://<your-agentcore-endpoint>/api/health/logistics

# Run the test suite — still fully offline, no AWS calls needed
pytest tests/test_supply_chain.py -v
```

---

## File Structure

The migration adds an `agentcore/` directory alongside the existing agent directories. Existing code is **not modified** — the AgentCore handlers are additive wrappers.

```
MultiAgentSupplyChainSystem/
├── run.sh                              # Unchanged — detects .env.aws, routes to AgentCore handlers
├── .env.aws                            # Your AWS config (gitignored)
│
├── agentcore/                          # AgentCore migration layer (all new)
│   ├── requirements.txt                # boto3, amazon-bedrock-agentcore, anthropic
│   ├── .env.aws.example                # AWS environment template
│   │
│   ├── config/
│   │   └── agents.yaml                 # AgentCore agent + tool definitions (declarative)
│   │
│   ├── setup/
│   │   └── provision_knowledge_base.py # One-time: creates OpenSearch + Bedrock KB
│   │
│   ├── agents/
│   │   ├── vision-agent/
│   │   │   └── agentcore_handler.py    # Claude 3.5 Sonnet + Code Interpreter
│   │   ├── supplier-agent/
│   │   │   └── agentcore_handler.py    # Bedrock Knowledge Base retrieval
│   │   ├── logistics-agent/
│   │   │   └── agentcore_handler.py    # Wraps existing shipping.py
│   │   └── control-tower/
│   │       └── agentcore_handler.py    # AgentCore Supervisor + WebSocket bridge
│   │
│   └── deploy/
│       ├── deploy-agentcore.sh         # Full AWS deployment
│       └── cleanup-agentcore.sh        # Tears down AgentCore resources
│
├── agents/                             # Existing agents — unchanged
│   ├── vision-agent/
│   ├── supplier-agent/
│   └── logistics-agent/
│
├── frontend/                           # Existing UI — unchanged
├── database/                           # Seed data reused by KB provisioning
└── intents/
    └── agentcore.md                    # This file
```

---

## Environment Variables Reference

### Local (`.env.aws`)

| Variable | Required | Description |
|---|---|---|
| `AWS_REGION` | Yes | Bedrock-enabled region (e.g. `us-east-1`) |
| `AWS_ACCOUNT_ID` | Yes | Your 12-digit AWS account ID |
| `BEDROCK_VISION_MODEL_ID` | No | Default: `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `BEDROCK_LOGISTICS_MODEL_ID` | No | Default: `anthropic.claude-3-haiku-20240307-v1:0` |
| `BEDROCK_KNOWLEDGE_BASE_ID` | Yes | Output from `provision_knowledge_base.py` |
| `AGENTCORE_RUNTIME_ROLE_ARN` | Yes | IAM role ARN for AgentCore Runtime |
| `AGENTCORE_GATEWAY_ID` | Yes | Output from first deploy |
| `OAUTH_CLIENT_ID` | Yes (MCP) | Google OAuth — same as before |
| `OAUTH_CLIENT_SECRET` | Yes (MCP) | Google OAuth — same as before |
| `OAUTH_REFRESH_TOKEN` | Yes (MCP) | Google OAuth — same as before |
| `VISION_AGENT_URL` | No | Default: `http://localhost:8081` |
| `SUPPLIER_AGENT_URL` | No | Default: `http://localhost:8082` |
| `LOGISTICS_AGENT_URL` | No | Default: `http://localhost:8083` |

---

## Model Mapping

| Role | Current (GCP) | Target (AWS) |
|---|---|---|
| Vision counting | Gemini 3 Flash + Code Execution | Claude 3.5 Sonnet + AgentCore Code Interpreter |
| Query extraction | Gemini 2.5 Flash Lite | Claude 3 Haiku (structured output) |
| Embeddings | Vertex AI text-embedding-005 | Amazon Titan Embeddings v2 |
| Vector search | AlloyDB ScaNN | Bedrock Knowledge Base + OpenSearch Serverless |
| Logistics | No LLM (deterministic) | No LLM (deterministic) — unchanged |

---

## Cost Comparison (estimated per 1,000 runs)

| Layer | GCP Cost | AWS AgentCore Cost |
|---|---|---|
| Vision model | ~$3.00 (Gemini 3 Flash) | ~$4.50 (Claude 3.5 Sonnet) |
| Embeddings | ~$0.10 (text-embedding-005) | ~$0.10 (Titan v2) |
| Vector search | ~$5.00 (AlloyDB instance/hr) | ~$0.80 (OpenSearch Serverless) |
| Compute | ~$2.00 (Cloud Run) | ~$1.20 (AgentCore Runtime, scale-to-zero) |
| **Total** | **~$10.10** | **~$6.60** |

Primary saving: AlloyDB charges for instance uptime even at zero queries. OpenSearch Serverless charges per OCU consumed. For intermittent workloads, that's 6× cheaper.

---

## Troubleshooting

**`NoRegionError` on boto3 calls**
```bash
export AWS_REGION=us-east-1  # or set in .env.aws
```

**`AccessDeniedException` on Bedrock model invocation**
- Go to Bedrock console → Model access → request access for the specific model IDs above
- Wait up to 5 minutes for access to propagate

**Knowledge Base returns no results**
- Confirm `BEDROCK_KNOWLEDGE_BASE_ID` matches the ID printed by `provision_knowledge_base.py`
- Re-run the sync: `aws bedrock-agent start-ingestion-job --knowledge-base-id $BEDROCK_KNOWLEDGE_BASE_ID --data-source-id $DATA_SOURCE_ID`

**Port conflicts (same as before)**
```bash
lsof -ti:8080 | xargs kill -9
lsof -ti:8081 | xargs kill -9
lsof -ti:8082 | xargs kill -9
lsof -ti:8083 | xargs kill -9
```

**Agent health checks**
```bash
curl http://localhost:8081/health
curl http://localhost:8082/health
curl http://localhost:8083/health
curl http://localhost:8080/api/health
```

---

## References

- [Amazon Bedrock AgentCore Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore Runtime](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-runtime.html)
- [AgentCore Memory](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-memory.html)
- [AgentCore Gateway](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-gateway.html)
- [AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore-code-interpreter.html)
- [Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Amazon Bedrock AgentCore SDK (PyPI)](https://pypi.org/project/amazon-bedrock-agentcore/)
- [Claude on Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
- [A2A Protocol](https://google.github.io/A2A/)
