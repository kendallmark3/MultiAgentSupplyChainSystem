"""
ChromaDB seed script — populates the local vector store with inventory data.
Replaces the AlloyDB seed script. No cloud credentials or server required.

Run once before starting the supplier agent:
    python database/seed.py

The supplier agent also auto-seeds on first start if the collection is empty,
so this script is optional — useful for pre-warming or resetting the database.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent
CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", str(SCRIPT_DIR / "chroma_db"))
COLLECTION_NAME = "inventory"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

INVENTORY_ITEMS = [
    ("Cardboard Shipping Box Large", "Packaging Solutions Inc", "Heavy-duty corrugated cardboard shipping container, 24x18x12 inches", 250),
    ("Warehouse Storage Container", "Industrial Supply Co", "Stackable plastic storage bin with snap-lock lid, blue", 180),
    ("Product Shipping Boxes", "Acme Packaging", "Medium corrugated boxes for warehouse storage, 18x14x10 inches", 320),
    ("Industrial Widget X-9", "Acme Corp", "Heavy-duty industrial coupling for pneumatic systems", 50),
    ("Precision Bolt M4", "Global Fasteners Inc", "Stainless steel M4 allen bolt, 20mm length, grade A2-70", 200),
    ("Hexagonal Nut M6", "Metro Supply Co", "Galvanized steel hex nut M6, DIN 934 standard", 150),
    ("Phillips Head Screw 3x20", "Acme Corp", "Zinc-plated Phillips head wood screw, 3mm x 20mm", 500),
    ("Wooden Dowel 10mm", "Craft Materials Ltd", "Hardwood birch dowel rod, 10mm diameter x 300mm length", 80),
    ("Rubber Gasket Small", "SealTech Industries", "Buna-N rubber gasket, 25mm OD x 15mm ID, oil resistant", 120),
    ("Spring Tension 5kg", "Mechanical Parts Co", "Stainless steel compression spring, 5kg load capacity", 60),
    ("Bearing 6204", "Bearings Direct", "Deep groove ball bearing 6204-2RS, 20x47x14mm sealed", 45),
    ("Warehouse Shelf Boxes", "Storage Systems Ltd", "Standardized warehouse inventory boxes, corrugated, bulk pack", 400),
    ("Inventory Container Units", "Supply Chain Pros", "Modular stackable storage units for warehouse racking", 95),
    ("Aluminum Extrusion Bar", "MetalWorks International", "T-slot aluminum extrusion 20x20mm profile, 1 meter length", 110),
    ("Cable Tie Pack 200mm", "ElectroParts Depot", "Nylon cable ties, 200mm x 4.8mm, UV resistant black, pack of 100", 600),
    ("Hydraulic Hose 1/2 inch", "FluidPower Systems", "High-pressure hydraulic hose, 1/2 inch ID, 3000 PSI rated", 35),
    ("Safety Goggles Clear", "WorkSafe Equipment Co", "ANSI Z87.1 rated clear safety goggles, anti-fog coating", 275),
    ("Packing Tape Industrial", "Packaging Solutions Inc", "Heavy-duty polypropylene packing tape, 48mm x 100m, clear", 450),
    ("Stainless Steel Sheet 1mm", "MetalWorks International", "304 stainless steel sheet, 1mm thickness, 300x300mm", 70),
    ("Silicone Sealant Tube", "SealTech Industries", "Industrial-grade RTV silicone sealant, 300ml cartridge, grey", 190),
]


def main():
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install chromadb sentence-transformers")
        sys.exit(1)

    print(f"ChromaDB path: {CHROMA_DB_PATH}")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print()

    Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    # Delete existing collection to allow clean re-seed
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"Dropped existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"Created collection: {COLLECTION_NAME}")

    print(f"Loading embedding model ({EMBEDDING_MODEL})...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("Model loaded")
    print()

    texts = [f"{name}. {desc}" for name, _, desc, _ in INVENTORY_ITEMS]
    ids = [f"item_{i}" for i in range(len(INVENTORY_ITEMS))]
    metadatas = [
        {
            "part_name": name,
            "supplier_name": supplier,
            "description": desc,
            "stock_level": stock,
        }
        for name, supplier, desc, stock in INVENTORY_ITEMS
    ]

    print(f"Generating embeddings for {len(texts)} items...")
    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    count = collection.count()
    print()
    print(f"Seed complete. {count} items in ChromaDB collection.")
    print()

    # Quick verification search
    test_query = "cardboard shipping boxes"
    test_embedding = model.encode(test_query).tolist()
    results = collection.query(
        query_embeddings=[test_embedding],
        n_results=1,
        include=["metadatas", "distances"],
    )
    if results["ids"] and results["ids"][0]:
        meta = results["metadatas"][0][0]
        dist = results["distances"][0][0]
        similarity = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
        print(f"Verification search: '{test_query}'")
        print(f"  Top match: {meta['part_name']} ({meta['supplier_name']})")
        print(f"  Confidence: {similarity * 100:.1f}%")
    print()
    print("Ready. Start the system with: sh run.sh")


if __name__ == "__main__":
    main()
