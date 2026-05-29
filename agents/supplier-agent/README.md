# Supplier Agent

Autonomous inventory search agent using **ChromaDB** with cosine vector search for semantic part matching.

No server. No cloud account. No cost.

---

## What Changed and Why

The original implementation used **AlloyDB AI + ScaNN + Vertex AI text-embedding-005**. That stack is production-grade and fast at scale — but AlloyDB costs ~$130–160/month just for the instance, billed by uptime, not by query volume.

For a POC running 100 manual test runs per month, you were paying $150 to run $0.50 worth of queries.

**The replacement:**

| Before | After |
|---|---|
| AlloyDB Python Connector | ChromaDB (embedded, no server) |
| Vertex AI text-embedding-005 (768-dim) | sentence-transformers `all-MiniLM-L6-v2` (384-dim) |
| GCP credentials required | No credentials required |
| ~$130–160/month | $0/month |

The public API is identical — `get_embedding()` and `find_supplier()` have the same signatures. Nothing else in the system changed.

**Production upgrade path:** When volume demands a managed service, swap the `inventory.py` internals for pgvector on RDS, OpenSearch Serverless, or Bedrock Knowledge Base. One file. The agents, A2A cards, and orchestration are untouched.

---

## How It Works

```
Query text: "cardboard shipping boxes warehouse"
        │
        ▼
sentence-transformers (local, ~80MB model)
        │  generates 384-dimensional embedding vector
        ▼
ChromaDB cosine search
        │  compares against 20 pre-seeded inventory embeddings
        │  persisted in database/chroma_db/
        ▼
Returns: ("Cardboard Shipping Box Large", "Packaging Solutions Inc", 0.08)
                 part_name                    supplier_name           distance
        │
        ▼
Confidence: 96.0%   (1 - distance/2 × 100)
```

ChromaDB uses the same cosine distance metric as AlloyDB ScaNN — distance range [0, 2], where 0 is identical and 2 is opposite. The `compute_confidence` function in `agent_executor.py` is unchanged.

---

## Files

- [inventory.py](inventory.py) — ChromaDB + sentence-transformers vector search (replaces AlloyDB)
- [agent_executor.py](agent_executor.py) — A2A protocol bridge + input guardrails (unchanged)
- [main.py](main.py) — FastAPI server (port 8082)
- [requirements.txt](requirements.txt) — `chromadb`, `sentence-transformers`

---

## Running

### Via master script (recommended)

```bash
cd ../..
sh run.sh
```

On first run, `run.sh` automatically seeds ChromaDB with 20 inventory items. Subsequent starts are instant.

### Manually

```bash
pip install -r requirements.txt
# No other environment variables needed for the supplier agent
uvicorn main:app --host 0.0.0.0 --port 8082
```

The agent auto-seeds ChromaDB if the collection is empty.

### Standalone test

```bash
python inventory.py
```

Output:
```json
{
  "part": "Cardboard Shipping Box Large",
  "supplier": "Packaging Solutions Inc",
  "distance": 0.0812,
  "match_confidence": "95.9%"
}
```

---

## Request / Response Format

Send via A2A protocol:

```json
{ "query": "cardboard shipping boxes warehouse" }
```

Response:

```json
{
  "part": "Cardboard Shipping Box Large",
  "supplier": "Packaging Solutions Inc",
  "match_confidence": "95.9%"
}
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `CHROMA_DB_PATH` | No | Path to ChromaDB storage (default: `database/chroma_db` from repo root) |
| `EMBEDDING_MODEL` | No | sentence-transformers model (default: `all-MiniLM-L6-v2`) |

No GCP credentials. No database password. No API key.

---

## Seeding the Database

ChromaDB is seeded automatically on first run. To manually re-seed (or reset to a clean state):

```bash
python ../../database/seed.py
```

This re-generates embeddings for all 20 inventory items and rebuilds the collection from scratch.

---

## Troubleshooting

**Slow startup on first run**
The `all-MiniLM-L6-v2` model (~80MB) downloads once and caches in `~/.cache/torch/sentence_transformers/`. Every subsequent start is instant.

**Empty collection / no results**
```bash
python ../../database/seed.py
```

**ChromaDB path not found**
Set `CHROMA_DB_PATH` explicitly in your `.env`, or let it default — `inventory.py` creates the directory automatically.

---

## References

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [sentence-transformers: all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [A2A Protocol](https://google.github.io/A2A/)
