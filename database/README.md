# Database

Local vector store for the Supplier Agent. Uses **ChromaDB** (embedded, persistent) with **sentence-transformers** embeddings.

No server. No cloud account. No cost.

---

## What Changed and Why

The original database was **AlloyDB AI** on Google Cloud — a managed PostgreSQL instance with ScaNN vector search and `ai.embedding()` SQL functions backed by Vertex AI.

**AlloyDB cost: ~$130–160/month** (billed by uptime, not queries).
**ChromaDB cost: $0** (embedded in-process, persists to a local directory).

For a POC, this difference is the deciding factor. The same 20-item inventory, the same cosine vector search, the same confidence scores — for zero cost. When you need to scale to millions of parts with SLA guarantees, the migration path is documented in [intents/agentcore.md](../intents/agentcore.md).

---

## Contents

| File | Purpose |
|---|---|
| `seed.py` | Seeds ChromaDB with 20 inventory items + local embeddings |
| `seed_data.sql` | Original SQL schema — kept as reference and for production migration |
| `chroma_db/` | ChromaDB persistent storage (auto-created on first seed) |
| `requirements.txt` | `chromadb`, `sentence-transformers` |

---

## How the Vector Store Works

```
20 inventory items (part name + description)
        │
        ▼
sentence-transformers all-MiniLM-L6-v2 (local, free)
        │  generates 384-dim embeddings
        ▼
ChromaDB collection "inventory"
        │  stored in database/chroma_db/
        │  cosine distance metric (same range as AlloyDB ScaNN: 0–2)
        ▼
Query: "cardboard shipping boxes"
        │  embed with same model → cosine search
        ▼
Result: ("Cardboard Shipping Box Large", "Packaging Solutions Inc", 0.08)
```

---

## Seeding

### Automatic (recommended)

`sh run.sh` seeds ChromaDB automatically on first run if `database/chroma_db/` does not exist. No manual step needed.

### Manual

```bash
pip install chromadb sentence-transformers
python database/seed.py
```

Output:

```
Loading embedding model (all-MiniLM-L6-v2)...
Model loaded

Generating embeddings for 20 items...
100%|████████████████████████████████| 20/20 [00:02<00:00]

Seed complete. 20 items in ChromaDB collection.

Verification search: 'cardboard shipping boxes'
  Top match: Cardboard Shipping Box Large (Packaging Solutions Inc)
  Confidence: 95.9%

Ready. Start the system with: sh run.sh
```

The model (~80MB) downloads once and caches in `~/.cache/`. Re-seeding is instant after that.

---

## Inventory Items (20)

The same 20 items from the original `seed_data.sql`:

| Part | Supplier |
|---|---|
| Cardboard Shipping Box Large | Packaging Solutions Inc |
| Warehouse Storage Container | Industrial Supply Co |
| Product Shipping Boxes | Acme Packaging |
| Industrial Widget X-9 | Acme Corp |
| Precision Bolt M4 | Global Fasteners Inc |
| Hexagonal Nut M6 | Metro Supply Co |
| Phillips Head Screw 3x20 | Acme Corp |
| Wooden Dowel 10mm | Craft Materials Ltd |
| Rubber Gasket Small | SealTech Industries |
| Spring Tension 5kg | Mechanical Parts Co |
| Bearing 6204 | Bearings Direct |
| Warehouse Shelf Boxes | Storage Systems Ltd |
| Inventory Container Units | Supply Chain Pros |
| Aluminum Extrusion Bar | MetalWorks International |
| Cable Tie Pack 200mm | ElectroParts Depot |
| Hydraulic Hose 1/2 inch | FluidPower Systems |
| Safety Goggles Clear | WorkSafe Equipment Co |
| Packing Tape Industrial | Packaging Solutions Inc |
| Stainless Steel Sheet 1mm | MetalWorks International |
| Silicone Sealant Tube | SealTech Industries |

---

## Production Upgrade Path

When the POC converts to production and volume demands a managed service, the upgrade is a single-file change in `agents/supplier-agent/inventory.py`:

| Scale | Recommended store | Change required |
|---|---|---|
| POC / dev | ChromaDB (current) | None |
| Small production | PostgreSQL + pgvector | Swap ChromaDB client for psycopg2 + pgvector |
| Mid-scale AWS | Amazon Aurora + pgvector | Same as above, different connection string |
| Large-scale AWS | Bedrock Knowledge Base | Use `agentcore/agents/supplier-agent/agentcore_handler.py` |
| Large-scale GCP | AlloyDB + ScaNN | Restore original `inventory.py` from git history |

The A2A interface, agent_executor.py, and everything above the supplier agent are untouched in all cases.

---

## Troubleshooting

**Collection empty / no results**
```bash
python database/seed.py
```

**Wrong ChromaDB path**
Set `CHROMA_DB_PATH` in your `.env` file. The default resolves relative to the repo root.

**Reset to clean state**
```bash
rm -rf database/chroma_db
python database/seed.py
```

---

## References

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [sentence-transformers all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [Original SQL schema](seed_data.sql)
