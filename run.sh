#!/bin/bash
# Autonomous Supply Chain - Master Run Script
# Starts all services: Vision Agent, Supplier Agent, Control Tower
# Usage: sh run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Starting Autonomous Supply Chain Services"
echo "============================================="
echo ""

# ============================================================================
# Load Environment Configuration
# ============================================================================

if [ -f "$SCRIPT_DIR/.env" ]; then
    echo "📄 Loading environment from .env..."
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
    echo "✅ Configuration loaded"
    echo ""
fi

# ============================================================================
# Validate Prerequisites
# ============================================================================

# Vertex AI config for Vision Agent
if [ -z "$GOOGLE_CLOUD_PROJECT" ]; then
    PROJECT=$(gcloud config get-value project 2>/dev/null)
    if [ -z "$PROJECT" ]; then
        echo "❌ GOOGLE_CLOUD_PROJECT not set"
        echo "   Run: gcloud config set project YOUR_PROJECT_ID"
        exit 1
    fi
    export GOOGLE_CLOUD_PROJECT="$PROJECT"
fi

if [ -z "$GOOGLE_CLOUD_LOCATION" ]; then
    export GOOGLE_CLOUD_LOCATION="global"
fi

export GOOGLE_GENAI_USE_VERTEXAI="True"

echo "✅ Vertex AI configured for Vision Agent"

# ChromaDB — local vector store, no server or credentials needed
CHROMA_DB_PATH="${CHROMA_DB_PATH:-$SCRIPT_DIR/database/chroma_db}"
export CHROMA_DB_PATH
echo "✅ ChromaDB configured: $CHROMA_DB_PATH"

# Auto-seed ChromaDB on first run if collection is missing
if [ ! -d "$CHROMA_DB_PATH" ]; then
    echo ""
    echo "First run: seeding ChromaDB inventory..."
    cd "$SCRIPT_DIR/database"
    pip install -q chromadb sentence-transformers python-dotenv
    python3 seed.py
    cd "$SCRIPT_DIR"
    echo ""
fi

echo "✅ Environment configured"
echo ""

# ============================================================================
# Pre-flight Tests
# ============================================================================

echo "🔍 Running pre-flight checks (report saved to tests/reports/)..."
echo ""

if ! sh "$SCRIPT_DIR/tests/run_tests.sh" preflight; then
    echo ""
    echo "❌ Pre-flight checks failed. Fix the issues above before starting services."
    echo "   Details: open tests/reports/latest.html"
    exit 1
fi

echo "✅ All pre-flight checks passed"
echo ""

mkdir -p logs

# ============================================================================
# Setup Cleanup Handler
# ============================================================================

cleanup() {
    echo ""
    echo "🛑 Shutting down all services..."

    if [ ! -z "$VISION_PID" ] && kill -0 $VISION_PID 2>/dev/null; then
        kill $VISION_PID 2>/dev/null || true
        echo "   Stopped Vision Agent"
    fi

    if [ ! -z "$SUPPLIER_PID" ] && kill -0 $SUPPLIER_PID 2>/dev/null; then
        kill $SUPPLIER_PID 2>/dev/null || true
        echo "   Stopped Supplier Agent"
    fi

    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null || true
        echo "   Stopped Control Tower"
    fi

    echo ""
    echo "✅ All services stopped"
    exit 0
}

trap cleanup SIGINT SIGTERM

# ============================================================================
# Start Vision Agent
# ============================================================================

echo "👁️  Step 1/3: Starting Vision Agent (Vertex AI mode)..."

cd "$SCRIPT_DIR/agents/vision-agent"

echo "   Installing dependencies..."
pip install -q -r requirements.txt

python3 -m uvicorn main:app --host 0.0.0.0 --port 8081 > "$SCRIPT_DIR/logs/vision-agent.log" 2>&1 &
VISION_PID=$!

RETRY_COUNT=0
MAX_RETRIES=20
VISION_HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    if curl -f -s http://localhost:8081/health > /dev/null 2>&1; then
        VISION_HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ "$VISION_HEALTHY" = true ]; then
    echo "✅ Vision Agent running on port 8081 (PID: $VISION_PID)"
else
    echo "⚠️  Vision Agent started but health check failed after ${MAX_RETRIES}s"
    echo "   Check logs/vision-agent.log for details"
fi

cd "$SCRIPT_DIR"
echo ""

# ============================================================================
# Start Supplier Agent
# ============================================================================

echo "🧠 Step 2/3: Starting Supplier Agent..."

cd "$SCRIPT_DIR/agents/supplier-agent"

echo "   Installing dependencies..."
pip install -q -r requirements.txt

python3 -m uvicorn main:app --host 0.0.0.0 --port 8082 > "$SCRIPT_DIR/logs/supplier-agent.log" 2>&1 &
SUPPLIER_PID=$!

RETRY_COUNT=0
MAX_RETRIES=20
SUPPLIER_HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    if curl -f -s http://localhost:8082/health > /dev/null 2>&1; then
        SUPPLIER_HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ "$SUPPLIER_HEALTHY" = true ]; then
    echo "✅ Supplier Agent running on port 8082 (PID: $SUPPLIER_PID)"
else
    echo "⚠️  Supplier Agent started but health check failed after ${MAX_RETRIES}s"
    echo "   Check logs/supplier-agent.log for details"
fi

cd "$SCRIPT_DIR"
echo ""

# ── Challenge 3: Start Logistics Agent ──────────────────────────────────────
echo "🚚 Starting Logistics Agent on port 8083..."

cd "$SCRIPT_DIR/agents/logistics-agent"

echo "   Installing dependencies..."
pip install -q -r requirements.txt

python3 -m uvicorn main:app --host 0.0.0.0 --port 8083 > "$SCRIPT_DIR/logs/logistics-agent.log" 2>&1 &
LOGISTICS_PID=$!

RETRY_COUNT=0
MAX_RETRIES=20
LOGISTICS_HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    if curl -f -s http://localhost:8083/health > /dev/null 2>&1; then
        LOGISTICS_HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ "$LOGISTICS_HEALTHY" = true ]; then
    echo "✅ Logistics Agent running on port 8083 (PID: $LOGISTICS_PID)"
else
    echo "⚠️  Logistics Agent started but health check failed after ${MAX_RETRIES}s"
    echo "   Check logs/logistics-agent.log for details"
fi

cd "$SCRIPT_DIR"
echo ""

# ============================================================================
# Start Control Tower (Frontend)
# ============================================================================

echo "🎨 Step 3/3: Starting Control Tower..."

cd "$SCRIPT_DIR/frontend"

echo "   Installing dependencies..."
pip install -q -r requirements.txt

python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!

RETRY_COUNT=0
MAX_RETRIES=20
FRONTEND_HEALTHY=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 1
    if curl -f -s http://localhost:8080/api/health > /dev/null 2>&1; then
        FRONTEND_HEALTHY=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ "$FRONTEND_HEALTHY" = true ]; then
    echo "✅ Control Tower running on port 8080 (PID: $FRONTEND_PID)"
else
    echo "⚠️  Control Tower started but health check failed after ${MAX_RETRIES}s"
    echo "   Check logs/frontend.log for details"
fi

cd "$SCRIPT_DIR"
echo ""

# ============================================================================
# All Services Running
# ============================================================================

mkdir -p "$SCRIPT_DIR/logs"

echo "╔════════════════════════════════════════════════╗"
echo "║  ✅ All Services Running!                      ║"
echo "╠════════════════════════════════════════════════╣"
echo "║  🌐 Control Tower: http://localhost:8080       ║"
echo "║  👁️  Vision Agent:  http://localhost:8081       ║"
echo "║  🧠 Supplier Agent: http://localhost:8082       ║"
echo "║  🚚 Logistics Agent: http://localhost:8083      ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "📋 Service PIDs:"
echo "   Vision:    $VISION_PID"
echo "   Supplier:  $SUPPLIER_PID"
echo "   Logistics: $LOGISTICS_PID"
echo "   Frontend:  $FRONTEND_PID"
echo ""
echo "📄 Logs available at:"
echo "   logs/vision-agent.log"
echo "   logs/supplier-agent.log"
echo "   logs/logistics-agent.log"
echo "   logs/frontend.log"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

wait