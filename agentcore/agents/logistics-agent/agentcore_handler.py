"""
Logistics Agent — AgentCore Runtime Handler

No model change — logistics is deterministic zone math.
This is a thin AgentCore Runtime wrapper around the existing shipping.py logic.

Preserves the same A2A-compatible interface:
  Input:  JSON { "supplier": str, "item_type": str, "item_count": int, "destination": str }
  Output: JSON { shipping_cost, carrier, eta_label, eta_days, origin, destination, breakdown }

Local dev: starts FastAPI on :8083, identical to the existing Logistics Agent.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

load_dotenv(find_dotenv(usecwd=True))
if Path(".env.aws").exists():
    load_dotenv(".env.aws", override=True)

# Pull in existing shipping.py from agents/logistics-agent/
REPO_ROOT = Path(__file__).resolve().parents[4]
LOGISTICS_AGENT_DIR = REPO_ROOT / "agents" / "logistics-agent"
if str(LOGISTICS_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(LOGISTICS_AGENT_DIR))

from shipping import calculate_shipping, get_supplier_location  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Logistics Agent — AgentCore")

AGENT_CARD = {
    "name": "Logistics Agent",
    "description": "Calculates zone-based shipping cost, carrier, and ETA from supplier location to destination",
    "version": "2.0.0",
    "url": os.environ.get("LOGISTICS_AGENT_URL", "http://localhost:8083"),
    "preferredTransport": "JSONRPC",
    "skills": [
        {
            "id": "calculate-shipping",
            "name": "Calculate Shipping",
            "description": "Zone-based shipping cost, carrier (FedEx/UPS), and ETA calculation",
            "tags": ["logistics", "shipping"],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        }
    ],
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "capabilities": {"streaming": False},
}


def compute_shipping(supplier: str, item_type: str, item_count: int, destination: str) -> dict:
    origin = get_supplier_location(supplier)
    result = calculate_shipping(
        supplier_name=supplier,
        item_type=item_type,
        item_count=item_count,
        destination=destination,
    )
    result["origin"] = origin
    result["destination"] = destination
    return result


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "logistics-agent", "backend": "deterministic"}


@app.post("/")
@app.post("/a2a")
async def handle_message(request: Request):
    body = await request.json()

    payload = None
    try:
        parts = body.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text") or part.get("root", {}).get("text", "")
            if text:
                payload = json.loads(text)
                break
    except Exception:
        pass

    if not payload:
        return JSONResponse({"error": "No payload in request"}, status_code=400)

    try:
        result = compute_shipping(
            supplier=payload.get("supplier", "Unknown Supplier"),
            item_type=payload.get("item_type", "items"),
            item_count=int(payload.get("item_count", 1)),
            destination=payload.get("destination", "New York, NY"),
        )
    except Exception as e:
        logger.error(f"Shipping calculation failed: {e}", exc_info=True)
        return JSONResponse({"error": "Shipping calculation failed."}, status_code=500)

    return JSONResponse({
        "id": body.get("id", ""),
        "result": {
            "parts": [{"kind": "text", "text": json.dumps(result)}],
            "role": "agent",
        },
    })


def run_local(supplier: str = None, destination: str = "New York, NY"):
    if supplier:
        result = compute_shipping(supplier=supplier, item_type="boxes", item_count=10, destination=destination)
        print(json.dumps(result, indent=2))
    else:
        uvicorn.run(app, host="0.0.0.0", port=8083)


def handler(event, context=None):
    payload = None
    try:
        parts = event.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text", "")
            if text:
                payload = json.loads(text)
                break
    except Exception as e:
        return {"error": str(e)}

    if not payload:
        return {"error": "No payload provided"}

    try:
        result = compute_shipping(
            supplier=payload.get("supplier", "Unknown Supplier"),
            item_type=payload.get("item_type", "items"),
            item_count=int(payload.get("item_count", 1)),
            destination=payload.get("destination", "New York, NY"),
        )
        return {"parts": [{"kind": "text", "text": json.dumps(result)}], "role": "agent"}
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return {"error": "Shipping calculation failed."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--supplier", help="Supplier name for direct test")
    parser.add_argument("--destination", default="New York, NY")
    args = parser.parse_args()
    run_local(supplier=args.supplier, destination=args.destination)
