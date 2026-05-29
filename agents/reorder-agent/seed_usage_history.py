from datetime import datetime, timedelta
import random
import json
from pathlib import Path

# Every item we track — stock levels, thresholds, usage patterns
INVENTORY = [
    {"part_name": "Bearing 6204", "supplier_name": "Bearings Direct", "stock_level": 45, "min_stock": 12, "lead_time_days": 4, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Cardboard Shipping Box Large", "supplier_name": "Packaging Solutions Inc", "stock_level": 250, "min_stock": 80, "lead_time_days": 2, "avg_daily_usage": 12, "usage_volatility": 0.3},
    {"part_name": "Cable Tie Pack 200mm", "supplier_name": "ElectroParts Depot", "stock_level": 600, "min_stock": 150, "lead_time_days": 2, "avg_daily_usage": 30, "usage_volatility": 0.15},
    {"part_name": "Hydraulic Hose 1/2 inch", "supplier_name": "FluidPower Systems", "stock_level": 35, "min_stock": 10, "lead_time_days": 4, "avg_daily_usage": 1, "usage_volatility": 0.5},
    {"part_name": "Safety Goggles Clear", "supplier_name": "WorkSafe Equipment Co", "stock_level": 275, "min_stock": 70, "lead_time_days": 4, "avg_daily_usage": 10, "usage_volatility": 0.2},
    {"part_name": "Precision Bolt M4", "supplier_name": "Global Fasteners Inc", "stock_level": 200, "min_stock": 60, "lead_time_days": 2, "avg_daily_usage": 18, "usage_volatility": 0.2},
    {"part_name": "Zip Lock Bag 30x40cm", "supplier_name": "Acme Packaging", "stock_level": 20, "min_stock": 250, "lead_time_days": 2, "avg_daily_usage": 50, "usage_volatility": 0.15},
    {"part_name": "Hard Hat Class E Yellow", "supplier_name": "WorkSafe Equipment Co", "stock_level": 60, "min_stock": 15, "lead_time_days": 3, "avg_daily_usage": 3, "usage_volatility": 0.2},
    {"part_name": "Proximity Sensor NPN", "supplier_name": "ElectroParts Depot", "stock_level": 55, "min_stock": 15, "lead_time_days": 4, "avg_daily_usage": 3, "usage_volatility": 0.35},
    {"part_name": "Machine Oil ISO 46 1L", "supplier_name": "FluidPower Systems", "stock_level": 80, "min_stock": 20, "lead_time_days": 3, "avg_daily_usage": 4, "usage_volatility": 0.2},
    # ── Fasteners & Hardware ─────────────────────────────────
    {"part_name": "Hexagonal Nut M6", "supplier_name": "Metro Supply Co", "stock_level": 150, "min_stock": 40, "lead_time_days": 3, "avg_daily_usage": 14, "usage_volatility": 0.2},
    {"part_name": "Phillips Head Screw 3x20", "supplier_name": "Acme Corp", "stock_level": 500, "min_stock": 120, "lead_time_days": 2, "avg_daily_usage": 25, "usage_volatility": 0.15},
    {"part_name": "Hex Key Set Metric", "supplier_name": "Global Fasteners Inc", "stock_level": 22, "min_stock": 6, "lead_time_days": 2, "avg_daily_usage": 1, "usage_volatility": 0.4},
    {"part_name": "O-Ring Kit Assorted", "supplier_name": "SealTech Industries", "stock_level": 35, "min_stock": 10, "lead_time_days": 3, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Spring Tension 5kg", "supplier_name": "Mechanical Parts Co", "stock_level": 60, "min_stock": 15, "lead_time_days": 3, "avg_daily_usage": 3, "usage_volatility": 0.4},

    # ── PPE & Safety ─────────────────────────────────────────
    {"part_name": "Cut Resistant Gloves L", "supplier_name": "WorkSafe Equipment Co", "stock_level": 140, "min_stock": 40, "lead_time_days": 3, "avg_daily_usage": 9, "usage_volatility": 0.25},
    {"part_name": "Hi-Vis Safety Vest XL", "supplier_name": "WorkSafe Equipment Co", "stock_level": 85, "min_stock": 20, "lead_time_days": 4, "avg_daily_usage": 4, "usage_volatility": 0.2},
    {"part_name": "Ear Protection 33dB", "supplier_name": "WorkSafe Equipment Co", "stock_level": 220, "min_stock": 60, "lead_time_days": 2, "avg_daily_usage": 11, "usage_volatility": 0.15},
    {"part_name": "Steel Toe Boot Size 10", "supplier_name": "WorkSafe Equipment Co", "stock_level": 30, "min_stock": 8, "lead_time_days": 5, "avg_daily_usage": 1, "usage_volatility": 0.5},
    {"part_name": "Rubber Gasket Small", "supplier_name": "SealTech Industries", "stock_level": 120, "min_stock": 35, "lead_time_days": 3, "avg_daily_usage": 7, "usage_volatility": 0.25},

    # ── Electronics & Sensors ─────────────────────────────────
    {"part_name": "Push Button Switch 22mm", "supplier_name": "ElectroParts Depot", "stock_level": 180, "min_stock": 50, "lead_time_days": 2, "avg_daily_usage": 8, "usage_volatility": 0.2},
    {"part_name": "Terminal Block 10A", "supplier_name": "ElectroParts Depot", "stock_level": 300, "min_stock": 80, "lead_time_days": 2, "avg_daily_usage": 16, "usage_volatility": 0.15},
    {"part_name": "Fuse 5A 250V", "supplier_name": "ElectroParts Depot", "stock_level": 500, "min_stock": 120, "lead_time_days": 2, "avg_daily_usage": 24, "usage_volatility": 0.2},
    {"part_name": "Temperature Sensor PT100", "supplier_name": "ElectroParts Depot", "stock_level": 25, "min_stock": 8, "lead_time_days": 5, "avg_daily_usage": 1, "usage_volatility": 0.4},
    {"part_name": "Cable Tie Pack 100mm", "supplier_name": "ElectroParts Depot", "stock_level": 400, "min_stock": 100, "lead_time_days": 2, "avg_daily_usage": 20, "usage_volatility": 0.15},

    # ── Chemicals & Lubricants ────────────────────────────────
    {"part_name": "Grease Cartridge EP2", "supplier_name": "FluidPower Systems", "stock_level": 60, "min_stock": 15, "lead_time_days": 3, "avg_daily_usage": 3, "usage_volatility": 0.25},
    {"part_name": "Anti-Seize Compound 500g", "supplier_name": "SealTech Industries", "stock_level": 40, "min_stock": 10, "lead_time_days": 3, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Parts Cleaner Spray 500ml", "supplier_name": "FluidPower Systems", "stock_level": 120, "min_stock": 30, "lead_time_days": 2, "avg_daily_usage": 7, "usage_volatility": 0.2},
    {"part_name": "Thread Locking Fluid 50ml", "supplier_name": "SealTech Industries", "stock_level": 90, "min_stock": 25, "lead_time_days": 3, "avg_daily_usage": 5, "usage_volatility": 0.25},
    {"part_name": "Silicone Sealant Tube", "supplier_name": "SealTech Industries", "stock_level": 190, "min_stock": 50, "lead_time_days": 3, "avg_daily_usage": 8, "usage_volatility": 0.25},

    # ── Raw Materials ─────────────────────────────────────────
    {"part_name": "Steel Rod 10mm 1m", "supplier_name": "MetalWorks International", "stock_level": 95, "min_stock": 25, "lead_time_days": 2, "avg_daily_usage": 5, "usage_volatility": 0.2},
    {"part_name": "Rubber Sheet 3mm 1x1m", "supplier_name": "SealTech Industries", "stock_level": 40, "min_stock": 10, "lead_time_days": 4, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Copper Tube 15mm 2m", "supplier_name": "MetalWorks International", "stock_level": 55, "min_stock": 15, "lead_time_days": 3, "avg_daily_usage": 3, "usage_volatility": 0.25},
    {"part_name": "Aluminum Extrusion Bar", "supplier_name": "MetalWorks International", "stock_level": 110, "min_stock": 30, "lead_time_days": 2, "avg_daily_usage": 5, "usage_volatility": 0.2},
    {"part_name": "Stainless Steel Sheet 1mm", "supplier_name": "MetalWorks International", "stock_level": 70, "min_stock": 20, "lead_time_days": 2, "avg_daily_usage": 3, "usage_volatility": 0.3},

    # ── Packaging & Shipping ──────────────────────────────────
    {"part_name": "Bubble Wrap Roll 50m", "supplier_name": "Packaging Solutions Inc", "stock_level": 35, "min_stock": 10, "lead_time_days": 2, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Stretch Wrap 500mm 300m", "supplier_name": "Packaging Solutions Inc", "stock_level": 60, "min_stock": 15, "lead_time_days": 2, "avg_daily_usage": 4, "usage_volatility": 0.2},
    {"part_name": "Desiccant Sachet 10g", "supplier_name": "Packaging Solutions Inc", "stock_level": 800, "min_stock": 200, "lead_time_days": 2, "avg_daily_usage": 40, "usage_volatility": 0.15},
    {"part_name": "Corner Protector Cardboard", "supplier_name": "Acme Packaging", "stock_level": 400, "min_stock": 100, "lead_time_days": 2, "avg_daily_usage": 20, "usage_volatility": 0.2},
    {"part_name": "Packing Tape Industrial", "supplier_name": "Packaging Solutions Inc", "stock_level": 450, "min_stock": 100, "lead_time_days": 2, "avg_daily_usage": 22, "usage_volatility": 0.15},
    {"part_name": "Foam Sheet 10mm 1x2m", "supplier_name": "Craft Materials Ltd", "stock_level": 50, "min_stock": 12, "lead_time_days": 3, "avg_daily_usage": 2, "usage_volatility": 0.3},
    {"part_name": "Warning Label Roll 250", "supplier_name": "Packaging Solutions Inc", "stock_level": 18, "min_stock": 5, "lead_time_days": 2, "avg_daily_usage": 1, "usage_volatility": 0.3},

    # ── Storage & Warehouse ───────────────────────────────────
    {"part_name": "Warehouse Storage Container", "supplier_name": "Industrial Supply Co", "stock_level": 180, "min_stock": 50, "lead_time_days": 2, "avg_daily_usage": 6, "usage_volatility": 0.2},
    {"part_name": "Inventory Container Units", "supplier_name": "Supply Chain Pros", "stock_level": 95, "min_stock": 25, "lead_time_days": 3, "avg_daily_usage": 5, "usage_volatility": 0.3},
    {"part_name": "Warehouse Shelf Boxes", "supplier_name": "Storage Systems Ltd", "stock_level": 400, "min_stock": 100, "lead_time_days": 3, "avg_daily_usage": 20, "usage_volatility": 0.2},
    {"part_name": "Wooden Dowel 10mm", "supplier_name": "Craft Materials Ltd", "stock_level": 80, "min_stock": 20, "lead_time_days": 3, "avg_daily_usage": 4, "usage_volatility": 0.3},
    {"part_name": "Nylon Rod 20mm 500mm", "supplier_name": "Craft Materials Ltd", "stock_level": 30, "min_stock": 8, "lead_time_days": 3, "avg_daily_usage": 1, "usage_volatility": 0.4},
    {"part_name": "Industrial Widget X-9", "supplier_name": "Acme Corp", "stock_level": 50, "min_stock": 15, "lead_time_days": 3, "avg_daily_usage": 2, "usage_volatility": 0.4},
    {"part_name": "Product Shipping Boxes", "supplier_name": "Acme Packaging", "stock_level": 320, "min_stock": 100, "lead_time_days": 2, "avg_daily_usage": 15, "usage_volatility": 0.35},
    {"part_name": "Foam Peanuts 1 cu ft", "supplier_name": "Packaging Solutions Inc", "stock_level": 45, "min_stock": 12, "lead_time_days": 2, "avg_daily_usage": 2, "usage_volatility": 0.35},
    {"part_name": "Wooden Pallet Standard", "supplier_name": "Craft Materials Ltd", "stock_level": 25, "min_stock": 8, "lead_time_days": 3, "avg_daily_usage": 1, "usage_volatility": 0.4},
    {"part_name": "Shrink Wrap Bags Large", "supplier_name": "Packaging Solutions Inc", "stock_level": 200, "min_stock": 50, "lead_time_days": 2, "avg_daily_usage": 10, "usage_volatility": 0.2},
]

def generate_history(item, days=30):
    """
    Fake 30 days of daily usage for one item.
    Weekdays use more stock. Weekends use less.
    ds = date (Prophet needs this name)
    y  = units used that day (Prophet needs this name)
    """
    random.seed(hash(item["part_name"]) % 10000)
    history = []
    today = datetime.today().date()
    start = today - timedelta(days=days)

    for i in range(days):
        date = start + timedelta(days=i)
        weekday = date.weekday()

        # Warehouse is busier Mon-Fri
        if weekday < 5:
            multiplier = random.uniform(0.9, 1.2)
        else:
            multiplier = random.uniform(0.2, 0.5)

        noise = random.uniform(1 - item["usage_volatility"], 1 + item["usage_volatility"])
        usage = max(0, round(item["avg_daily_usage"] * multiplier * noise))
        history.append({"ds": date.isoformat(), "y": usage})

    return history

def seed_all(days=30):
    print(f"Seeding {days}-day history for {len(INVENTORY)} items...\n")
    result = {}

    for item in INVENTORY:
        history = generate_history(item, days)
        avg = round(sum(r["y"] for r in history) / days, 1)
        result[item["part_name"]] = {**item, "history": history, "seeded_avg": avg}
        print(f"  ✓ {item['part_name']:<35} avg {avg} units/day")

    output = Path(__file__).parent / "data" / "usage_history.json"
    output.parent.mkdir(exist_ok=True)
    with open(output, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Saved to {output}")
    return result

if __name__ == "__main__":
    seed_all()