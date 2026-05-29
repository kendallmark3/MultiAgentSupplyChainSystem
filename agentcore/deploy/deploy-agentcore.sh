#!/bin/bash
# ============================================================================
# deploy-agentcore.sh — Deploy Autonomous Supply Chain to AWS AgentCore
#
# Usage: sh agentcore/deploy/deploy-agentcore.sh
#
# Prerequisites:
#   1. .env.aws filled in (copy from agentcore/.env.aws.example)
#   2. pip install amazon-bedrock-agentcore-cli
#   3. aws configure (or AWS_PROFILE set)
#   4. Bedrock model access enabled for Claude 3.5 Sonnet + Titan Embeddings v2
#   5. Knowledge Base provisioned: python agentcore/setup/provision_knowledge_base.py
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AGENTCORE_DIR="$REPO_ROOT/agentcore"

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Deploy Autonomous Supply Chain to AWS AgentCore      ║"
echo "║  Vision x Vector x Agents — AWS Edition               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# ── Load .env.aws ─────────────────────────────────────────────
if [ -f "$REPO_ROOT/.env.aws" ]; then
    echo "Loading .env.aws..."
    set -a
    source "$REPO_ROOT/.env.aws"
    set +a
    echo "Config loaded"
else
    echo "ERROR: .env.aws not found."
    echo "  cp agentcore/.env.aws.example .env.aws && fill it in"
    exit 1
fi

# ── Validate required vars ─────────────────────────────────────
MISSING=0
for VAR in AWS_REGION AWS_ACCOUNT_ID BEDROCK_KNOWLEDGE_BASE_ID AGENTCORE_RUNTIME_ROLE_ARN; do
    if [ -z "${!VAR}" ]; then
        echo "ERROR: $VAR not set in .env.aws"
        MISSING=1
    fi
done
[ "$MISSING" -eq 1 ] && exit 1

echo ""
echo "Deployment target:"
echo "  AWS Account:  $AWS_ACCOUNT_ID"
echo "  Region:       $AWS_REGION"
echo "  Knowledge Base: $BEDROCK_KNOWLEDGE_BASE_ID"
echo ""
read -p "Deploy now? (Y/n): " CONFIRM
[ "$CONFIRM" = "n" ] || [ "$CONFIRM" = "N" ] && { echo "Cancelled."; exit 0; }
echo ""

# ── Step 1: Create IAM roles if not present ────────────────────
echo "[1/7] Checking AgentCore IAM role..."
if aws iam get-role --role-name AgentCoreRuntimeRole >/dev/null 2>&1; then
    echo "      IAM role AgentCoreRuntimeRole already exists"
else
    echo "      Creating IAM role AgentCoreRuntimeRole..."
    aws iam create-role \
        --role-name AgentCoreRuntimeRole \
        --assume-role-policy-document '{
          "Version": "2012-10-17",
          "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "bedrock.amazonaws.com"},
            "Action": "sts:AssumeRole"
          }]
        }' \
        --region "$AWS_REGION" > /dev/null

    aws iam attach-role-policy \
        --role-name AgentCoreRuntimeRole \
        --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess

    aws iam attach-role-policy \
        --role-name AgentCoreRuntimeRole \
        --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess

    echo "      IAM role created"
fi
echo ""

# ── Step 2: Deploy Vision Agent ────────────────────────────────
echo "[2/7] Deploying Vision Agent..."
agentcore deploy \
    --name vision-agent \
    --handler "$AGENTCORE_DIR/agents/vision-agent/agentcore_handler.py:handler" \
    --role-arn "$AGENTCORE_RUNTIME_ROLE_ARN" \
    --region "$AWS_REGION" \
    --enable-code-interpreter \
    --memory 1024 \
    --timeout 120 \
    --env "AWS_REGION=$AWS_REGION" \
    --env "BEDROCK_VISION_MODEL_ID=${BEDROCK_VISION_MODEL_ID:-anthropic.claude-3-5-sonnet-20241022-v2:0}" \
    --source "$REPO_ROOT"

VISION_ARN=$(agentcore describe --name vision-agent --region "$AWS_REGION" --query "agentArn" --output text)
echo "      Vision Agent deployed: $VISION_ARN"
echo ""

# ── Step 3: Deploy Supplier Agent ──────────────────────────────
echo "[3/7] Deploying Supplier Agent..."
agentcore deploy \
    --name supplier-agent \
    --handler "$AGENTCORE_DIR/agents/supplier-agent/agentcore_handler.py:handler" \
    --role-arn "$AGENTCORE_RUNTIME_ROLE_ARN" \
    --region "$AWS_REGION" \
    --memory 512 \
    --timeout 30 \
    --env "AWS_REGION=$AWS_REGION" \
    --env "BEDROCK_KNOWLEDGE_BASE_ID=$BEDROCK_KNOWLEDGE_BASE_ID" \
    --env "BEDROCK_LOGISTICS_MODEL_ID=${BEDROCK_LOGISTICS_MODEL_ID:-anthropic.claude-3-haiku-20240307-v1:0}" \
    --source "$REPO_ROOT"

SUPPLIER_ARN=$(agentcore describe --name supplier-agent --region "$AWS_REGION" --query "agentArn" --output text)
echo "      Supplier Agent deployed: $SUPPLIER_ARN"
echo ""

# ── Step 4: Deploy Logistics Agent ─────────────────────────────
echo "[4/7] Deploying Logistics Agent..."
agentcore deploy \
    --name logistics-agent \
    --handler "$AGENTCORE_DIR/agents/logistics-agent/agentcore_handler.py:handler" \
    --role-arn "$AGENTCORE_RUNTIME_ROLE_ARN" \
    --region "$AWS_REGION" \
    --memory 256 \
    --timeout 10 \
    --env "AWS_REGION=$AWS_REGION" \
    --source "$REPO_ROOT"

LOGISTICS_ARN=$(agentcore describe --name logistics-agent --region "$AWS_REGION" --query "agentArn" --output text)
echo "      Logistics Agent deployed: $LOGISTICS_ARN"
echo ""

# ── Step 5: Create AgentCore Gateway ──────────────────────────
echo "[5/7] Creating AgentCore Gateway..."
GATEWAY_RESPONSE=$(aws bedrock-agentcore create-gateway \
    --gateway-name supply-chain-gateway \
    --role-arn "$AGENTCORE_RUNTIME_ROLE_ARN" \
    --region "$AWS_REGION" \
    --output json 2>/dev/null || echo "{}")

GATEWAY_ID=$(echo "$GATEWAY_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('gatewayId',''))" 2>/dev/null || echo "")

if [ -z "$GATEWAY_ID" ]; then
    GATEWAY_ID=$(aws bedrock-agentcore list-gateways \
        --region "$AWS_REGION" \
        --query "gateways[?name=='supply-chain-gateway'].gatewayId" \
        --output text 2>/dev/null || echo "")
fi

if [ -n "$GATEWAY_ID" ]; then
    GATEWAY_ENDPOINT=$(aws bedrock-agentcore get-gateway \
        --gateway-id "$GATEWAY_ID" \
        --region "$AWS_REGION" \
        --query "gatewayUrl" \
        --output text 2>/dev/null || echo "")
    echo "      Gateway ID: $GATEWAY_ID"
    echo "      Gateway endpoint: $GATEWAY_ENDPOINT"
    # Append to .env.aws for future runs
    grep -q "AGENTCORE_GATEWAY_ID=" "$REPO_ROOT/.env.aws" \
        && sed -i.bak "s|AGENTCORE_GATEWAY_ID=.*|AGENTCORE_GATEWAY_ID=$GATEWAY_ID|" "$REPO_ROOT/.env.aws" \
        || echo "AGENTCORE_GATEWAY_ID=$GATEWAY_ID" >> "$REPO_ROOT/.env.aws"
    grep -q "AGENTCORE_GATEWAY_ENDPOINT=" "$REPO_ROOT/.env.aws" \
        && sed -i.bak "s|AGENTCORE_GATEWAY_ENDPOINT=.*|AGENTCORE_GATEWAY_ENDPOINT=$GATEWAY_ENDPOINT|" "$REPO_ROOT/.env.aws" \
        || echo "AGENTCORE_GATEWAY_ENDPOINT=$GATEWAY_ENDPOINT" >> "$REPO_ROOT/.env.aws"
else
    echo "      WARNING: Could not retrieve Gateway ID. Add manually to .env.aws."
fi
echo ""

# ── Step 6: Register agents in Gateway ────────────────────────
echo "[6/7] Registering agents in Gateway..."
if [ -n "$GATEWAY_ID" ]; then
    for AGENT_NAME in vision-agent supplier-agent logistics-agent; do
        AGENT_ARN=$(agentcore describe --name "$AGENT_NAME" --region "$AWS_REGION" --query "agentArn" --output text 2>/dev/null || echo "")
        if [ -n "$AGENT_ARN" ]; then
            aws bedrock-agentcore create-gateway-target \
                --gateway-id "$GATEWAY_ID" \
                --target-name "$AGENT_NAME" \
                --target-configuration "{\"bedrockAgentCoreTarget\": {\"agentCoreArn\": \"$AGENT_ARN\"}}" \
                --region "$AWS_REGION" > /dev/null 2>&1 || true
            echo "      Registered: $AGENT_NAME"
        fi
    done
fi
echo ""

# ── Step 7: Deploy Control Tower ───────────────────────────────
echo "[7/7] Deploying Control Tower (Supervisor)..."

# Set agent URLs to Gateway endpoints for deployed environment
CT_VISION_URL="${GATEWAY_ENDPOINT}/vision-agent"
CT_SUPPLIER_URL="${GATEWAY_ENDPOINT}/supplier-agent"
CT_LOGISTICS_URL="${GATEWAY_ENDPOINT}/logistics-agent"

agentcore deploy \
    --name control-tower \
    --handler "$AGENTCORE_DIR/agents/control-tower/agentcore_handler.py" \
    --role-arn "$AGENTCORE_RUNTIME_ROLE_ARN" \
    --region "$AWS_REGION" \
    --memory 1024 \
    --timeout 300 \
    --port 8080 \
    --env "AWS_REGION=$AWS_REGION" \
    --env "AGENTCORE_GATEWAY_ID=$GATEWAY_ID" \
    --env "AGENTCORE_GATEWAY_ENDPOINT=$GATEWAY_ENDPOINT" \
    --env "VISION_AGENT_URL=$CT_VISION_URL" \
    --env "SUPPLIER_AGENT_URL=$CT_SUPPLIER_URL" \
    --env "LOGISTICS_AGENT_URL=$CT_LOGISTICS_URL" \
    --env "OAUTH_CLIENT_ID=$OAUTH_CLIENT_ID" \
    --env "OAUTH_CLIENT_SECRET=$OAUTH_CLIENT_SECRET" \
    --env "OAUTH_REFRESH_TOKEN=$OAUTH_REFRESH_TOKEN" \
    --source "$REPO_ROOT"

SERVICE_URL=$(agentcore describe --name control-tower --region "$AWS_REGION" --query "endpoint" --output text 2>/dev/null || echo "(see AgentCore console)")

echo ""
echo "╔════════════════════════════════════════════════════════╗"
echo "║  Deployment Complete!                                  ║"
echo "╠════════════════════════════════════════════════════════╣"
echo "║                                                        ║"
echo "  Endpoint:  $SERVICE_URL"
echo "  Gateway:   $GATEWAY_ENDPOINT"
echo "  Region:    $AWS_REGION"
echo "║                                                        ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""
echo "Health check:"
echo "  curl $SERVICE_URL/api/health"
echo ""
