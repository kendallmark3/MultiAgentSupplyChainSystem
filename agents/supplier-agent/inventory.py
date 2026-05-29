"""
Supplier Agent: ChromaDB vector search for finding parts and suppliers.
Replaces AlloyDB + Vertex AI text-embedding-005 with fully local, free alternatives:
  - sentence-transformers (all-MiniLM-L6-v2) for embedding generation
  - ChromaDB (embedded mode) for persistent cosine vector search

No server required. No cloud credentials needed. Zero cost.
Data persists to database/chroma_db/ on first seed run.
"""
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Repo root is two levels up from agents/supplier-agent/
_REPO_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DB_PATH = os.environ.get(
    "CHROMA_DB_PATH",
    str(_REPO_ROOT / "database" / "chroma_db"),
)
COLLECTION_NAME = "inventory"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Inventory seed data — mirrors database/seed_data.sql
# Loaded here so inventory.py can auto-seed on first run without importing seed.py
_SEED_ITEMS = [
    ("Cardboard Shipping Box Large", "Packaging Solutions Inc", "Heavy-duty corrugated cardboard shipping container, 24x18x12 inches"),
    ("Warehouse Storage Container", "Industrial Supply Co", "Stackable plastic storage bin with snap-lock lid, blue"),
    ("Product Shipping Boxes", "Acme Packaging", "Medium corrugated boxes for warehouse storage, 18x14x10 inches"),
    ("Industrial Widget X-9", "Acme Corp", "Heavy-duty industrial coupling for pneumatic systems"),
    ("Precision Bolt M4", "Global Fasteners Inc", "Stainless steel M4 allen bolt, 20mm length, grade A2-70"),
    ("Hexagonal Nut M6", "Metro Supply Co", "Galvanized steel hex nut M6, DIN 934 standard"),
    ("Phillips Head Screw 3x20", "Acme Corp", "Zinc-plated Phillips head wood screw, 3mm x 20mm"),
    ("Wooden Dowel 10mm", "Craft Materials Ltd", "Hardwood birch dowel rod, 10mm diameter x 300mm length"),
    ("Rubber Gasket Small", "SealTech Industries", "Buna-N rubber gasket, 25mm OD x 15mm ID, oil resistant"),
    ("Spring Tension 5kg", "Mechanical Parts Co", "Stainless steel compression spring, 5kg load capacity"),
    ("Bearing 6204", "Bearings Direct", "Deep groove ball bearing 6204-2RS, 20x47x14mm sealed"),
    ("Warehouse Shelf Boxes", "Storage Systems Ltd", "Standardized warehouse inventory boxes, corrugated, bulk pack"),
    ("Inventory Container Units", "Supply Chain Pros", "Modular stackable storage units for warehouse racking"),
    ("Aluminum Extrusion Bar", "MetalWorks International", "T-slot aluminum extrusion 20x20mm profile, 1 meter length"),
    ("Cable Tie Pack 200mm", "ElectroParts Depot", "Nylon cable ties, 200mm x 4.8mm, UV resistant black, pack of 100"),
    ("Hydraulic Hose 1/2 inch", "FluidPower Systems", "High-pressure hydraulic hose, 1/2 inch ID, 3000 PSI rated"),
    ("Safety Goggles Clear", "WorkSafe Equipment Co", "ANSI Z87.1 rated clear safety goggles, anti-fog coating"),
    ("Packing Tape Industrial", "Packaging Solutions Inc", "Heavy-duty polypropylene packing tape, 48mm x 100m, clear"),
    ("Stainless Steel Sheet 1mm", "MetalWorks International", "304 stainless steel sheet, 1mm thickness, 300x300mm"),
    ("Silicone Sealant Tube", "SealTech Industries", "Industrial-grade RTV silicone sealant, 300ml cartridge, grey"),
]

_embedding_model = None
_chroma_client = None
_collection = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded")
    return _embedding_model


def _get_collection():
    global _chroma_client, _collection
    if _collection is not None:
        return _collection

    import chromadb

    Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    _collection = _chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    if _collection.count() == 0:
        logger.info("ChromaDB collection is empty — auto-seeding inventory...")
        _seed_collection(_collection)

    logger.info(f"ChromaDB collection ready: {_collection.count()} items at {CHROMA_DB_PATH}")
    return _collection


def _seed_collection(collection):
    """Populate ChromaDB with inventory items and their embeddings."""
    model = _get_embedding_model()

    texts = [f"{name}. {desc}" for name, _, desc in _SEED_ITEMS]
    ids = [f"item_{i}" for i in range(len(_SEED_ITEMS))]
    metadatas = [
        {"part_name": name, "supplier_name": supplier, "description": desc}
        for name, supplier, desc in _SEED_ITEMS
    ]

    logger.info(f"Generating embeddings for {len(texts)} inventory items...")
    embeddings = model.encode(texts, show_progress_bar=False).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    logger.info(f"Seeded {len(texts)} items into ChromaDB")


def get_embedding(text: str) -> list[float]:
    """
    Generate embedding for query text using sentence-transformers (local, free).
    Replaces Vertex AI text-embedding-005.
    """
    if not text or not isinstance(text, str):
        raise ValueError("text must be a non-empty string")

    model = _get_embedding_model()
    embedding = model.encode(text, show_progress_bar=False)
    logger.info(f"Generated embedding: {len(embedding)} dimensions")
    return embedding.tolist()


def find_supplier(embedding_vector: list[float]) -> tuple | None:
    """
    Find the nearest supplier for the given embedding using ChromaDB cosine search.
    Returns (part_name, supplier_name, distance) matching the original AlloyDB signature.
    ChromaDB cosine distance range: 0 (identical) to 2 (opposite) — same as ScaNN.
    """
    logger.info(f"Searching inventory with embedding (dimension: {len(embedding_vector)})")

    collection = _get_collection()
    results = collection.query(
        query_embeddings=[embedding_vector],
        n_results=1,
        include=["metadatas", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        logger.warning("ChromaDB query returned no results")
        return None

    metadata = results["metadatas"][0][0]
    distance = results["distances"][0][0]

    part_name = metadata["part_name"]
    supplier_name = metadata["supplier_name"]

    logger.info(f"Match: {part_name} from {supplier_name} (distance: {distance:.4f})")
    return (part_name, supplier_name, distance)


def find_supplier_by_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> tuple | None:
    """Image-based supplier search — not supported in the ChromaDB implementation.
    Returns None so agent_executor.py falls back to text search gracefully."""
    logger.info("Image-based supplier search not available in ChromaDB mode — falling back to text search")
    return None


def main():
    """Standalone verification: search for a test query."""
    test_query = "cardboard shipping boxes warehouse"
    print(f"Testing ChromaDB search with query: '{test_query}'")

    embedding = get_embedding(test_query)
    result = find_supplier(embedding)

    if result:
        part_name, supplier_name, distance = result
        similarity = max(0.0, min(1.0, 1.0 - (distance / 2.0)))
        output = {
            "part": part_name,
            "supplier": supplier_name,
            "distance": round(distance, 4),
            "match_confidence": f"{similarity * 100:.1f}%",
        }
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps({"error": "No matching supplier found"}))


if __name__ == "__main__":
    main()
