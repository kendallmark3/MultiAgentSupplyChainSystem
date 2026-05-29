"""
Vision Agent — AgentCore Runtime Handler

Replaces: Vertex AI Gemini 3 Flash + Code Execution
With:      Claude 3.5 Sonnet + AgentCore Code Interpreter

Preserves the same A2A-compatible interface:
  Input:  JSON { "image_base64": "<base64>" }
  Output: JSON { count, item_type, bounding_boxes, search_query, summary }
         + [BOUNDING_BOXES]...[/BOUNDING_BOXES] sentinel (Control Tower compatibility)

Local dev: starts FastAPI on :8081, identical to the existing Vision Agent.
Deployed:  runs inside AgentCore Runtime with Code Interpreter enabled.
"""

import argparse
import base64
import json
import logging
import os
import sys
from pathlib import Path

import boto3
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

load_dotenv(find_dotenv(usecwd=True))
if Path(".env.aws").exists():
    load_dotenv(".env.aws", override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_VISION_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")

VISION_SYSTEM_PROMPT = """You are a warehouse inventory vision system.
You will receive a base64-encoded warehouse shelf image.
Your task:
1. Write Python code using PIL/numpy to detect and count distinct items
2. Return bounding boxes as a list of {x, y, w, h} dicts (normalized 0-1)
3. Identify the item type (e.g. "cardboard boxes", "safety goggles")
4. Generate a 3-6 word supplier search query for the item type

Respond ONLY with valid JSON:
{
  "count": <int>,
  "item_type": "<str>",
  "search_query": "<str>",
  "summary": "<one sentence>",
  "bounding_boxes": [{"x": 0.1, "y": 0.2, "w": 0.15, "h": 0.2}, ...]
}"""

app = FastAPI(title="Vision Agent — AgentCore")

AGENT_CARD = {
    "name": "Vision Agent",
    "description": "Counts warehouse items using Claude 3.5 Sonnet + AgentCore Code Interpreter",
    "version": "2.0.0",
    "url": os.environ.get("VISION_AGENT_URL", "http://localhost:8081"),
    "preferredTransport": "JSONRPC",
    "skills": [
        {
            "id": "count-warehouse-items",
            "name": "Count Warehouse Items",
            "description": "Analyze a base64-encoded shelf image and return item count, bounding boxes, and search query",
            "tags": ["vision", "inventory", "counting"],
            "examples": ["Count the items on this shelf"],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        }
    ],
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "capabilities": {"streaming": False},
}


def analyze_image_with_bedrock(image_base64: str) -> dict:
    bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    image_bytes = base64.b64decode(image_base64)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": VISION_SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Analyze this warehouse shelf image. Count all items, identify their type, and return the JSON response as specified.",
                    },
                ],
            }
        ],
    })

    response = bedrock.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    result = json.loads(response["body"].read())
    raw_text = result["content"][0]["text"].strip()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        data = json.loads(match.group(0)) if match else {}

    boxes = data.get("bounding_boxes", [])
    count = data.get("count", len(boxes))
    item_type = data.get("item_type", "items")
    search_query = data.get("search_query", "warehouse inventory items")
    summary = data.get("summary", f"{count} {item_type} detected.")

    response_payload = {
        "count": count,
        "item_count": count,
        "type": item_type,
        "item_type": item_type,
        "confidence": "high" if count > 0 else "low",
        "summary": summary,
        "search_query": search_query,
        "boxes": boxes,
        "bounding_boxes": boxes,
    }

    full_response = json.dumps(response_payload)
    full_response += f"\n\n[BOUNDING_BOXES]{json.dumps(boxes)}[/BOUNDING_BOXES]"
    return {"text": full_response, "data": response_payload}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "vision-agent", "backend": "bedrock", "model": MODEL_ID}


@app.post("/")
@app.post("/a2a")
async def handle_message(request: Request):
    body = await request.json()

    image_base64 = None
    try:
        parts = body.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text") or part.get("root", {}).get("text", "")
            if text:
                data = json.loads(text)
                image_base64 = data.get("image_base64")
                break
    except Exception:
        pass

    if not image_base64:
        return JSONResponse({"error": "No image_base64 in request"}, status_code=400)

    result = analyze_image_with_bedrock(image_base64)

    return JSONResponse({
        "id": body.get("id", ""),
        "result": {
            "parts": [{"kind": "text", "text": result["text"]}],
            "role": "agent",
        },
    })


def run_local(image_path: str = None):
    if image_path:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        result = analyze_image_with_bedrock(image_b64)
        print(json.dumps(result["data"], indent=2))
    else:
        uvicorn.run(app, host="0.0.0.0", port=8081)


# AgentCore Runtime entrypoint
def handler(event, context=None):
    image_base64 = None
    try:
        parts = event.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text", "")
            if text:
                data = json.loads(text)
                image_base64 = data.get("image_base64")
                break
    except Exception as e:
        return {"error": str(e)}

    if not image_base64:
        return {"error": "No image_base64 provided"}

    result = analyze_image_with_bedrock(image_base64)
    return {"parts": [{"kind": "text", "text": result["text"]}], "role": "agent"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Run as local FastAPI server on :8081")
    parser.add_argument("--image", help="Path to image file for direct test (skips server)")
    args = parser.parse_args()
    run_local(image_path=args.image)
