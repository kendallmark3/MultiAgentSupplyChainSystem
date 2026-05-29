"""
Supplier Agent — AgentCore Runtime Handler

Replaces: AlloyDB ScaNN + Vertex AI text-embedding-005
With:      Bedrock Knowledge Base (OpenSearch Serverless + Titan Embeddings v2)

Preserves the same A2A-compatible interface:
  Input:  JSON { "query": "<search text>" }
  Output: JSON { part, supplier, match_confidence, description, unit_cost }

Local dev: starts FastAPI on :8082, identical to the existing Supplier Agent.
Deployed:  runs inside AgentCore Runtime with Knowledge Base binding.
"""

import argparse
import json
import logging
import os
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
KNOWLEDGE_BASE_ID = os.environ.get("BEDROCK_KNOWLEDGE_BASE_ID", "")
LOGISTICS_MODEL_ID = os.environ.get("BEDROCK_LOGISTICS_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

MAX_QUERY_LENGTH = 300

app = FastAPI(title="Supplier Agent — AgentCore")

AGENT_CARD = {
    "name": "Supplier Agent",
    "description": "Finds best-matched supplier parts via Bedrock Knowledge Base semantic search (Titan Embeddings v2 + OpenSearch Serverless)",
    "version": "2.0.0",
    "url": os.environ.get("SUPPLIER_AGENT_URL", "http://localhost:8082"),
    "preferredTransport": "JSONRPC",
    "skills": [
        {
            "id": "find-supplier-part",
            "name": "Find Supplier Part",
            "description": "Semantic search over inventory parts to find the best-matched supplier",
            "tags": ["supplier", "vector-search", "inventory"],
            "inputModes": ["application/json"],
            "outputModes": ["application/json"],
        }
    ],
    "defaultInputModes": ["application/json"],
    "defaultOutputModes": ["application/json"],
    "capabilities": {"streaming": False},
}


def sanitize_query(query: str) -> str:
    import re
    query = re.sub(r"[^a-zA-Z0-9\s\-_.,()]", "", query)
    return query.strip()[:MAX_QUERY_LENGTH]


def search_knowledge_base(query: str) -> dict:
    if not KNOWLEDGE_BASE_ID:
        raise ValueError("BEDROCK_KNOWLEDGE_BASE_ID not set. Run agentcore/setup/provision_knowledge_base.py first.")

    clean_query = sanitize_query(query)
    if not clean_query:
        raise ValueError("Query is empty after sanitization.")

    bedrock_agent_rt = boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)

    response = bedrock_agent_rt.retrieve_and_generate(
        input={"text": clean_query},
        retrieveAndGenerateConfiguration={
            "type": "KNOWLEDGE_BASE",
            "knowledgeBaseConfiguration": {
                "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                "modelArn": f"arn:aws:bedrock:{AWS_REGION}::foundation-model/{LOGISTICS_MODEL_ID}",
                "retrievalConfiguration": {
                    "vectorSearchConfiguration": {
                        "numberOfResults": 1,
                    }
                },
                "generationConfiguration": {
                    "promptTemplate": {
                        "textPromptTemplate": (
                            "Given this warehouse inventory search query: '$query$'\n"
                            "Use the following inventory records to find the best match:\n"
                            "$search_results$\n"
                            "Return ONLY valid JSON: "
                            '{"part": "<part name>", "supplier": "<supplier name>", '
                            '"match_confidence": "<High|Medium|Low>", "description": "<brief description>", '
                            '"unit_cost": "<cost string>"}'
                        )
                    },
                    "inferenceConfig": {"textInferenceConfig": {"temperature": 0, "maxTokens": 512}},
                },
            },
        },
    )

    raw_text = response.get("output", {}).get("text", "{}")
    logger.info(f"Knowledge Base response: {raw_text[:200]}")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        data = json.loads(match.group(0)) if match else {}

    citations = response.get("citations", [])
    if citations:
        retrieved_refs = citations[0].get("retrievedReferences", [])
        if retrieved_refs:
            source_text = retrieved_refs[0].get("content", {}).get("text", "")
            logger.info(f"Top retrieved source: {source_text[:150]}")

    return {
        "part": data.get("part", "Unknown Part"),
        "supplier": data.get("supplier", "Unknown Supplier"),
        "match_confidence": data.get("match_confidence", "Low"),
        "description": data.get("description", ""),
        "unit_cost": data.get("unit_cost", "N/A"),
    }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return JSONResponse(AGENT_CARD)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "supplier-agent",
        "backend": "bedrock-knowledge-base",
        "knowledge_base_id": KNOWLEDGE_BASE_ID or "NOT SET",
    }


@app.post("/")
@app.post("/a2a")
async def handle_message(request: Request):
    body = await request.json()

    query = None
    try:
        parts = body.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text") or part.get("root", {}).get("text", "")
            if text:
                data = json.loads(text)
                query = data.get("query")
                break
    except Exception:
        pass

    if not query:
        return JSONResponse({"error": "No query in request"}, status_code=400)

    try:
        result = search_knowledge_base(query)
    except Exception as e:
        logger.error(f"Knowledge Base search failed: {e}", exc_info=True)
        return JSONResponse({"error": "Supplier search failed. Please try again."}, status_code=500)

    return JSONResponse({
        "id": body.get("id", ""),
        "result": {
            "parts": [{"kind": "text", "text": json.dumps(result)}],
            "role": "agent",
        },
    })


def run_local(query: str = None):
    if query:
        result = search_knowledge_base(query)
        print(json.dumps(result, indent=2))
    else:
        uvicorn.run(app, host="0.0.0.0", port=8082)


def handler(event, context=None):
    query = None
    try:
        parts = event.get("params", {}).get("message", {}).get("parts", [])
        for part in parts:
            text = part.get("text", "")
            if text:
                data = json.loads(text)
                query = data.get("query")
                break
    except Exception as e:
        return {"error": str(e)}

    if not query:
        return {"error": "No query provided"}

    try:
        result = search_knowledge_base(query)
        return {"parts": [{"kind": "text", "text": json.dumps(result)}], "role": "agent"}
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return {"error": "Supplier search failed."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--query", help="Search query for direct test")
    args = parser.parse_args()
    run_local(query=args.query)
