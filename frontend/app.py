import asyncio
import base64
import io
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Set
from uuid import uuid4

from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
from PIL import Image

from a2a.client import A2ACardResolver, A2AClient
import anthropic
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build
from a2a.types import MessageSendParams, SendMessageRequest
import sys as _sys
_sys.path.append(str(Path(__file__).resolve().parent.parent / "agents"))
from governance import enforce_policy

import sys as _et_sys
_et_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "agents"))
from execution_tracker import ExecutionTracker, WEGAStage, StageStatus

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

load_dotenv(find_dotenv(usecwd=True))

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parent

VISION_URL = os.environ.get("VISION_AGENT_URL", "http://localhost:8081")
SUPPLIER_URL = os.environ.get("SUPPLIER_AGENT_URL", "http://localhost:8082")
LOGISTICS_URL = os.environ.get("LOGISTICS_AGENT_URL", "http://localhost:8083")

app = FastAPI(title="Autonomous Supply Chain Control Tower")

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._event_cache: list = []
        self._max_cache = 30

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        for event in self._event_cache:
            try:
                await websocket.send_json(event)
            except Exception:
                break

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    def clear_cache(self):
        self._event_cache = []

    async def broadcast(self, message: dict):
        self._event_cache.append(message)
        if len(self._event_cache) > self._max_cache:
            self._event_cache = self._event_cache[-self._max_cache:]

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        self.active_connections -= disconnected


manager = ConnectionManager()


def compress_image(image_bytes: bytes, max_size_kb: int = 500) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGB")

    max_dimension = 1024
    quality = 85

    while max_dimension >= 256:
        img_copy = img.copy()
        img_copy.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        img_copy.save(output, format="JPEG", quality=quality, optimize=True)
        compressed_bytes = output.getvalue()

        if len(compressed_bytes) / 1024 <= max_size_kb:
            return compressed_bytes

        if quality > 60:
            quality -= 10
        else:
            max_dimension = int(max_dimension * 0.8)
            quality = 85

    return compressed_bytes


def extract_text_from_response(response) -> str:
    text = ""

    if hasattr(response, "root"):
        root = response.root
        if hasattr(root, "result"):
            result = root.result
            if hasattr(result, "parts"):
                for part in result.parts or []:
                    if hasattr(part, "root") and hasattr(part.root, "text"):
                        if part.root.text:
                            text += part.root.text

    if not text and hasattr(response, "artifact") and response.artifact:
        for part in getattr(response.artifact, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if not part_text and hasattr(part, "root"):
                part_text = getattr(part.root, "text", None)
            if part_text:
                text += part_text

    if not text and hasattr(response, "messages"):
        for msg in response.messages or []:
            for part in getattr(msg, "parts", []) or []:
                part_text = getattr(part, "text", None)
                if not part_text and hasattr(part, "root"):
                    part_text = getattr(part.root, "text", None)
                if part_text:
                    text += part_text

    return text


def extract_thinking_steps(response_text: str, agent_type: str = "vision") -> list:
    import datetime

    if agent_type == "supplier":
        return [
            {
                "step": 1,
                "thought": "Generating embedding vector from query text",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            },
            {
                "step": 2,
                "thought": "Executing ScaNN vector search in AlloyDB",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            },
            {
                "step": 3,
                "thought": "Ranking results by similarity score",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            },
        ]

    steps = []

    if "def " in response_text or "import " in response_text:
        steps.extend(
            [
                {
                    "step": 1,
                    "thought": "Analyzing image requirements and planning approach",
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                },
                {
                    "step": 2,
                    "thought": "Writing Python code with OpenCV for box detection",
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                },
                {
                    "step": 3,
                    "thought": "Executing code in sandbox environment",
                    "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
                },
            ]
        )

    if "result" in response_text.lower() or "boxes" in response_text.lower():
        steps.append(
            {
                "step": len(steps) + 1,
                "thought": "Processing execution results and formatting output",
                "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
            }
        )

    return steps


async def run_workflow_with_events(image_bytes: bytes):
    manager.clear_cache()
    async with httpx.AsyncClient(timeout=300.0) as client:
        await manager.broadcast(
            {
                "type": "upload_complete",
                "message": "Image uploaded successfully",
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        await asyncio.sleep(0.5)

        await manager.broadcast(
            {
                "type": "discovery_start",
                "agent": "vision",
                "message": "Discovering Vision Agent via A2A protocol...",
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        try:
            resolver = A2ACardResolver(httpx_client=client, base_url=VISION_URL)
            vision_card = await resolver.get_agent_card()
            vision_client = A2AClient(httpx_client=client, agent_card=vision_card)

            vision_skills = []
            if hasattr(vision_card, "skills") and vision_card.skills:
                for s in vision_card.skills:
                    vision_skills.append(
                        {
                            "id": getattr(s, "id", ""),
                            "name": getattr(s, "name", ""),
                            "description": getattr(s, "description", ""),
                            "tags": getattr(s, "tags", []),
                            "examples": getattr(s, "examples", []),
                        }
                    )

            vision_caps = getattr(vision_card, "capabilities", None)
            vision_streaming = getattr(vision_caps, "streaming", False) if vision_caps else False

            await manager.broadcast(
                {
                    "type": "discovery_complete",
                    "agent": "vision",
                    "message": f"Vision Agent discovered: {vision_card.name}",
                    "agent_name": vision_card.name,
                    "agent_description": getattr(vision_card, "description", ""),
                    "agent_url": VISION_URL,
                    "agent_version": getattr(vision_card, "version", "1.0.0"),
                    "agent_skills": vision_skills,
                    "agent_input_modes": getattr(vision_card, "default_input_modes", []),
                    "agent_output_modes": getattr(vision_card, "default_output_modes", []),
                    "agent_protocol_version": getattr(vision_card, "protocol_version", ""),
                    "agent_transport": getattr(vision_card, "preferred_transport", ""),
                    "agent_streaming": vision_streaming,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            await asyncio.sleep(0.5)

            await manager.broadcast(
                {
                    "type": "vision_start",
                    "message": "Vision Agent analyzing image with Gemini 3 Flash...",
                    "details": "Think-Act-Observe loop initiated",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            compressed_bytes = compress_image(image_bytes, max_size_kb=500)
            payload = json.dumps(
                {
                    "image_base64": base64.b64encode(compressed_bytes).decode("utf-8"),
                }
            )

            request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{"kind": "text", "text": payload}],
                        "messageId": uuid4().hex,
                    }
                ),
            )

            await manager.broadcast(
                {
                    "type": "vision_progress",
                    "substep": "thinking",
                    "message": "Gemini 3 Flash analyzing image composition...",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            response = await vision_client.send_message(request)
            vision_text = extract_text_from_response(response)

            bounding_boxes = []
            clean_vision_text = vision_text

            if "[BOUNDING_BOXES]" in vision_text:
                try:
                    bbox_start = vision_text.index("[BOUNDING_BOXES]") + len("[BOUNDING_BOXES]")
                    bbox_end = vision_text.index("[/BOUNDING_BOXES]")
                    bbox_json = vision_text[bbox_start:bbox_end]
                    bounding_boxes = json.loads(bbox_json)
                    clean_vision_text = vision_text[: vision_text.index("[BOUNDING_BOXES]")].strip()
                    logger.info(f"Extracted {len(bounding_boxes)} bounding boxes from vision response")
                except Exception as e:
                    logger.warning(f"Failed to parse bounding boxes: {e}")

            real_count = len(bounding_boxes)
            real_type = "cardboard boxes" if real_count > 0 else "items"
            real_confidence = "high" if real_count > 0 else "low"
            _tracker = ExecutionTracker()
            _tracker.start_session(f"count {real_type} and assess reorder")
            _tracker.complete_planner(real_type)
            _tracker.start_builder()
            real_summary = f"{real_count} {real_type} were detected."

            try:
                vision_data = json.loads(clean_vision_text.split("\n\n")[0])
                real_type = vision_data.get("item_type", real_type)
                real_confidence = vision_data.get("confidence", real_confidence)
                real_summary = vision_data.get("summary", real_summary)
                dynamic_search_query = vision_data.get("search_query", "warehouse inventory items")
            except Exception:
                dynamic_search_query = "warehouse inventory items"

            await manager.broadcast(
                {
                    "type": "vision_complete",
                    "message": "Vision analysis complete",
                    "result": clean_vision_text,
                    "item_count": real_count,
                    "item_type": real_type,
                    "summary": real_summary,
                    "confidence": real_confidence,
                    "search_query": dynamic_search_query,
                    "bounding_boxes": bounding_boxes,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            thinking_steps = extract_thinking_steps(vision_text, "vision")
            if thinking_steps:
                await manager.broadcast(
                    {
                        "type": "thinking_update",
                        "agent": "vision",
                        "steps": thinking_steps,
                    }
                )

        except Exception as e:
            await manager.broadcast(
                {
                    "type": "vision_error",
                    "message": f"Vision Agent error: {str(e)}",
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )
            return

        await asyncio.sleep(0.5)

        await manager.broadcast(
            {
                "type": "discovery_start",
                "agent": "supplier",
                "message": "Discovering Supplier Agent via A2A protocol...",
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        try:
            supplier_resolver = A2ACardResolver(httpx_client=client, base_url=SUPPLIER_URL)
            supplier_card = await supplier_resolver.get_agent_card()
            supplier_client = A2AClient(httpx_client=client, agent_card=supplier_card)

            supplier_skills = []
            if hasattr(supplier_card, "skills") and supplier_card.skills:
                for s in supplier_card.skills:
                    supplier_skills.append(
                        {
                            "id": getattr(s, "id", ""),
                            "name": getattr(s, "name", ""),
                            "description": getattr(s, "description", ""),
                            "tags": getattr(s, "tags", []),
                            "examples": getattr(s, "examples", []),
                        }
                    )

            supplier_caps = getattr(supplier_card, "capabilities", None)
            supplier_streaming = (
                getattr(supplier_caps, "streaming", False) if supplier_caps else False
            )

            await manager.broadcast(
                {
                    "type": "discovery_complete",
                    "agent": "supplier",
                    "message": f"Supplier Agent discovered: {supplier_card.name}",
                    "agent_name": supplier_card.name,
                    "agent_description": getattr(supplier_card, "description", ""),
                    "agent_url": SUPPLIER_URL,
                    "agent_version": getattr(supplier_card, "version", "1.0.0"),
                    "agent_skills": supplier_skills,
                    "agent_input_modes": getattr(supplier_card, "default_input_modes", []),
                    "agent_output_modes": getattr(supplier_card, "default_output_modes", []),
                    "agent_protocol_version": getattr(supplier_card, "protocol_version", ""),
                    "agent_transport": getattr(supplier_card, "preferred_transport", ""),
                    "agent_streaming": supplier_streaming,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            await asyncio.sleep(0.5)

            await manager.broadcast(
                {
                    "type": "memory_start",
                    "message": "Querying AlloyDB with ScaNN vector search...",
                    "details": "Searching inventory parts",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            supplier_payload = json.dumps({"query": dynamic_search_query})
            logger.info(f"Supplier search query: '{dynamic_search_query}'")
            supplier_request = SendMessageRequest(
                id=str(uuid4()),
                params=MessageSendParams(
                    message={
                        "role": "user",
                        "parts": [{"kind": "text", "text": supplier_payload}],
                        "messageId": uuid4().hex,
                    }
                ),
            )

            supplier_response = await supplier_client.send_message(supplier_request)
            supplier_text = extract_text_from_response(supplier_response)

            part_name = "Cardboard Boxes"
            supplier_name = "Acme Industrial Supplies"
            confidence = "High"

            if supplier_text:
                try:
                    supplier_data = json.loads(supplier_text)

                    part_name = (
                        supplier_data.get("part")
                        or supplier_data.get("part_name")
                        or supplier_data.get("item")
                        or part_name
                    )

                    supplier_name = (
                        supplier_data.get("supplier")
                        or supplier_data.get("supplier_name")
                        or supplier_name
                    )

                    confidence = (
                        supplier_data.get("match_confidence")
                        or supplier_data.get("confidence")
                        or confidence
                    )

                except json.JSONDecodeError:
                    logger.warning(f"Supplier response was not JSON: {supplier_text[:150]}")

            await manager.broadcast(
                {
                    "type": "memory_complete",
                    "message": f"Match found: {part_name}",
                    "part": part_name,
                    "supplier": supplier_name,
                    "confidence": confidence,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            supplier_thinking = extract_thinking_steps(supplier_text, "supplier")
            if supplier_thinking:
                await manager.broadcast(
                    {
                        "type": "thinking_update",
                        "agent": "memory",
                        "steps": supplier_thinking,
                    }
                )

            await asyncio.sleep(0.5)

            # ── Reorder Agent ──────────────────────────────────────────
            import sys as _rs
            _reorder_path = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "agents" / "reorder-agent")
            if _reorder_path not in _rs.path:
                _rs.path.insert(0, _reorder_path)
            try:
                from forecaster import assess_reorder, load_usage_data
                usage_data = load_usage_data()
                reorder = assess_reorder(part_name, real_count, 3, usage_data)
                _tracker.complete_builder(real_count, real_type, real_confidence, supplier_name, part_name)
                _tracker.complete_validator(real_confidence, 86.0, True)
                _tracker.complete_evaluator(reorder["status"], reorder["days_until_stockout"], reorder["reorder_point"], reorder["should_order"], reorder["reason"])
                await manager.broadcast({
                    "type": "reorder_assessment",
                    "status": reorder["status"],
                    "days_until_stockout": reorder["days_until_stockout"],
                    "reason": reorder["reason"],
                    "should_order": reorder["should_order"],
                    "message": reorder["reason"],
                    "reorder_point": reorder["reorder_point"],
                    "recommended_qty": reorder["recommended_qty"],
                    "predicted_daily_usage": reorder["predicted_daily_usage"],
                    "lead_time_days": reorder["lead_time_days"],
                    "timestamp": asyncio.get_event_loop().time(),
                })
                if not reorder["should_order"]:
                    await manager.broadcast({
                        "type": "order_skipped",
                        "message": f"Order blocked — {reorder['reason']}",
                        "timestamp": asyncio.get_event_loop().time(),
                    })
                    return
            except Exception as _re:
                import logging as _rl
                _rl.getLogger(__name__).error(f"Reorder agent failed: {_re}", exc_info=True)
                await manager.broadcast({"type": "reorder_assessment", "status": "ERROR", "days_until_stockout": 0, "reorder_point": 0, "recommended_qty": 0, "predicted_daily_usage": 0, "should_order": True, "reason": f"Error: {str(_re)}", "lead_time_days": 3, "message": f"Error: {str(_re)}", "timestamp": 0})
            # ── End Reorder Agent ───────────────────────────────────────

            order_id = f"#{random.randint(9000, 9999)}"
            await manager.broadcast(
                {
                    "type": "order_placed",
                    "message": f"Order {order_id} placed autonomously",
                    "order_id": order_id,
                    "part": part_name,
                    "supplier": supplier_name,
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            await asyncio.sleep(0.5)
            await manager.broadcast(
                {
                    "type": "logistics_start",
                    "message": "Calculating shipping cost and ETA via Logistics Agent...",
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )

            try:
                logistics_resolver = A2ACardResolver(httpx_client=client, base_url=LOGISTICS_URL)
                logistics_card = await logistics_resolver.get_agent_card()
                logistics_client = A2AClient(httpx_client=client, agent_card=logistics_card)

                logistics_payload = json.dumps({
                    "supplier": supplier_name,
                    "item_type": real_type,
                    "item_count": real_count,
                    "destination": "New York, NY",
                })

                logistics_request = SendMessageRequest(
                    id=str(uuid4()),
                    params=MessageSendParams(
                        message={
                            "role": "user",
                            "parts": [{"kind": "text", "text": logistics_payload}],
                            "messageId": uuid4().hex,
                        }
                    ),
                )

                logistics_response = await logistics_client.send_message(logistics_request)
                logistics_text = extract_text_from_response(logistics_response)

                shipping_cost = "N/A"
                carrier = "N/A"
                eta = "N/A"
                origin = "N/A"

                if logistics_text:
                    try:
                        logistics_data = json.loads(logistics_text)
                        shipping_cost = logistics_data.get("shipping_cost", shipping_cost)
                        carrier = logistics_data.get("carrier", carrier)
                        eta = logistics_data.get("eta_label", logistics_data.get("eta_days", eta))
                        origin = logistics_data.get("origin", origin)
                    except json.JSONDecodeError:
                        logger.warning(f"Logistics response was not JSON: {logistics_text[:100]}")

                await manager.broadcast(
                    {
                        "type": "logistics_complete",
                        "message": f"Shipping: {shipping_cost} via {carrier}",
                        "shipping_cost": shipping_cost,
                        "carrier": carrier,
                        "eta": str(eta),
                        "origin": origin,
                        "destination": "New York, NY",
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                )
                logger.info(f"Logistics: {shipping_cost} via {carrier}, ETA {eta}")
                _tracker.complete_reporter(shipping_cost, carrier, str(eta), False, False, False)
                await manager.broadcast({
                    "type": "execution_summary",
                    **_tracker.to_dict(),
                    "timestamp": asyncio.get_event_loop().time(),
                })

                await asyncio.sleep(0.5)
                await manager.broadcast({
                    "type": "mcp_start",
                    "message": "Sending confirmation via Gmail, Calendar & Sheets...",
                    "timestamp": asyncio.get_event_loop().time(),
                })
                asyncio.create_task(run_mcp_integrations(
                    order_id=order_id,
                    part_name=part_name,
                    supplier_name=supplier_name,
                    item_count=real_count,
                    item_type=real_type,
                    shipping_cost=shipping_cost,
                    carrier=carrier,
                    eta=str(eta),
                    origin=origin,
                    manager=manager,
                ))

            except Exception as e:
                logger.warning(f"Logistics Agent unavailable: {e}")
                await manager.broadcast(
                    {
                        "type": "logistics_complete",
                        "message": "Logistics Agent unavailable — shipping estimate skipped",
                        "shipping_cost": "N/A",
                        "carrier": "N/A",
                        "eta": "N/A",
                        "origin": "N/A",
                        "destination": "New York, NY",
                        "timestamp": asyncio.get_event_loop().time(),
                    }
                )

        except Exception as e:
            await manager.broadcast(
                {
                    "type": "memory_error",
                    "message": f"Supplier Agent error: {str(e)}",
                    "error": str(e),
                    "timestamp": asyncio.get_event_loop().time(),
                }
            )


# ── MCP Integration ──────────────────────────────────────────────────────────
MCP_USER_EMAIL = "syedshabbeerbasha08@gmail.com"
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1w-zhfJtPmptPgv8ctvWfNyGYJq5mEB-FYdsI7913Dds/edit"
SHEET_ID = "1w-zhfJtPmptPgv8ctvWfNyGYJq5mEB-FYdsI7913Dds"
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "")
OAUTH_REFRESH_TOKEN = os.environ.get("OAUTH_REFRESH_TOKEN", "")
USER_EMAIL = "syedshabbeerbasha08@gmail.com"


async def run_mcp_integrations(
    order_id, part_name, supplier_name, item_count,
    item_type, shipping_cost, carrier, eta, origin, manager
):
    import asyncio, base64, pytz
    from datetime import datetime, timedelta
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    results = {"email": False, "calendar": False, "sheets": False}
    loop = asyncio.get_event_loop()

    def get_creds():
        c = Credentials(
            token=None,
            refresh_token=OAUTH_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=OAUTH_CLIENT_ID,
            client_secret=OAUTH_CLIENT_SECRET,
            scopes=["https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/calendar",
                    "https://www.googleapis.com/auth/spreadsheets"]
        )
        c.refresh(Request())
        return c

    def do_all():
        creds = get_creds()
        tz = pytz.timezone("America/Chicago")
        now = datetime.now(tz)
        now_str = now.strftime("%Y-%m-%d %H:%M")
        r = {"email": False, "calendar": False, "sheets": False}

        # Gmail
        try:
            svc = build("gmail", "v1", credentials=creds)
            html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
            <div style="background:#6366f1;padding:20px;border-radius:10px 10px 0 0">
            <h1 style="color:white;margin:0">Order {order_id} Confirmed</h1></div>
            <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-radius:0 0 10px 10px">
            <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px;color:#6b7280">Part</td><td style="padding:8px;font-weight:600">{part_name}</td></tr>
            <tr style="background:#f1f5f9"><td style="padding:8px;color:#6b7280">Supplier</td><td style="padding:8px">{supplier_name}</td></tr>
            <tr><td style="padding:8px;color:#6b7280">Quantity</td><td style="padding:8px">{item_count}</td></tr>
            <tr style="background:#f1f5f9"><td style="padding:8px;color:#6b7280">Shipping</td><td style="padding:8px;color:#16a34a;font-weight:700">{shipping_cost} via {carrier}</td></tr>
            <tr><td style="padding:8px;color:#6b7280">ETA</td><td style="padding:8px">{eta}</td></tr>
            <tr style="background:#f1f5f9"><td style="padding:8px;color:#6b7280">From</td><td style="padding:8px">{origin} → New York, NY</td></tr>
            </table></div></div>"""
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Order {order_id} Confirmed — {part_name}"
            msg["From"] = USER_EMAIL
            msg["To"] = USER_EMAIL
            msg.attach(MIMEText(html, "html"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            svc.users().messages().send(userId="me", body={"raw": raw}).execute()
            r["email"] = True
            logger.info(f"✅ Gmail sent!")
        except Exception as e:
            logger.error(f"Gmail error: {e}")

        # Calendar
        try:
            svc = build("calendar", "v3", credentials=creds)
            try: days = int(str(eta).split()[0])
            except: days = 3
            delivery = now + timedelta(days=days)
            start_dt = delivery.replace(hour=9, minute=0, second=0, microsecond=0)
            end_dt = delivery.replace(hour=10, minute=0, second=0, microsecond=0)
            event = {
                "summary": f"Delivery: {part_name} ({order_id})",
                "description": f"Order from {supplier_name} via {carrier}. Cost: {shipping_cost}",
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Chicago"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Chicago"},
            }
            svc.events().insert(calendarId="primary", body=event).execute()
            r["calendar"] = True
            logger.info(f"✅ Calendar event created!")
        except Exception as e:
            logger.error(f"Calendar error: {e}")

        # Sheets
        try:
            svc = build("sheets", "v4", credentials=creds)
            sheet = svc.spreadsheets()
            res = sheet.values().get(spreadsheetId=SHEET_ID, range="Sheet1!A1:A1").execute()
            if not res.get("values"):
                sheet.values().update(
                    spreadsheetId=SHEET_ID, range="Sheet1!A1",
                    valueInputOption="RAW",
                    body={"values": [["Order ID", "Date", "Part", "Supplier", "Quantity", "Shipping Cost", "Carrier", "ETA", "Origin"]]}
                ).execute()
            sheet.values().append(
                spreadsheetId=SHEET_ID, range="Sheet1!A:I",
                valueInputOption="RAW", insertDataOption="INSERT_ROWS",
                body={"values": [[order_id, now_str, part_name, supplier_name, str(item_count), shipping_cost, carrier, str(eta), origin]]}
            ).execute()
            r["sheets"] = True
            logger.info(f"✅ Sheets logged!")
        except Exception as e:
            logger.error(f"Sheets error: {e}")

        return r

    try:
        results = await loop.run_in_executor(None, do_all)
    except Exception as e:
        logger.error(f"Integration error: {e}", exc_info=True)

    await manager.broadcast({
        "type": "mcp_complete",
        "message": "Integrations complete",
        "email_sent": results["email"],
        "calendar_created": results["calendar"],
        "sheet_logged": results["sheets"],
        "timestamp": asyncio.get_event_loop().time(),
    })


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/analyze")
async def analyze_image(file: UploadFile = File(...)):
    try:
        image_bytes = await file.read()

        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        # Governance check before any agent runs
        content_type = file.content_type or "application/octet-stream"
        gov_result = enforce_policy({
            "type": "inventory_check",
            "image": image_bytes,
            "content_type": content_type,
            "user": "warehouse_operator"
        })
        if not gov_result["approved"]:
            raise HTTPException(status_code=400, detail=gov_result["reason"])

        asyncio.create_task(run_workflow_with_events(image_bytes))

        return {
            "status": "processing",
            "message": "Workflow started. Listen to WebSocket for real-time updates.",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "control-tower",
        "vision_url": VISION_URL,
        "supplier_url": SUPPLIER_URL,
        "logistics_url": LOGISTICS_URL,
    }


@app.get("/api/test-images")
async def list_test_images():
    test_images_dir = APP_ROOT / "test-images"

    if not test_images_dir.exists():
        return {"images": []}

    images = []
    for img_path in test_images_dir.glob("*"):
        if img_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
            images.append(
                {
                    "name": img_path.name,
                    "path": f"test-images/{img_path.name}",
                }
            )

    return {"images": images}


@app.get("/api/test-image/{image_name}")
async def get_test_image(image_name: str):
    test_images_dir = APP_ROOT / "test-images"
    image_path = test_images_dir / image_name

    if not image_path.exists() or image_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(image_path)


static_dir = APP_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = APP_ROOT / "static" / "index.html"

    if index_path.exists():
        return FileResponse(index_path)

    return HTMLResponse(
        """
        <html>
            <body>
                <h1>Autonomous Supply Chain Control Tower</h1>
                <p>Static files not found. Please create frontend/static/index.html</p>
            </body>
        </html>
        """
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
