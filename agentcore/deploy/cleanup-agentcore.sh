#!/bin/bash
# ============================================================================
# cleanup-agentcore.sh — Tear down AgentCore resources
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$REPO_ROOT/.env.aws" ]; then
    set -a && source "$REPO_ROOT/.env.aws" && set +a
fi

AWS_REGION="${AWS_REGION:-us-east-1}"

echo ""
echo "This will delete all AgentCore resources for this project:"
echo "  - Agents: vision-agent, supplier-agent, logistics-agent, control-tower"
echo "  - Gateway: supply-chain-gateway"
echo ""
read -p "Confirm teardown? (yes/N): " CONFIRM
[ "$CONFIRM" != "yes" ] && { echo "Aborted."; exit 0; }

echo ""
echo "Deleting agents..."
for AGENT_NAME in control-tower vision-agent supplier-agent logistics-agent; do
    agentcore delete --name "$AGENT_NAME" --region "$AWS_REGION" 2>/dev/null && echo "  Deleted: $AGENT_NAME" || echo "  Not found: $AGENT_NAME"
done

if [ -n "$AGENTCORE_GATEWAY_ID" ]; then
    echo "Deleting Gateway $AGENTCORE_GATEWAY_ID..."
    aws bedrock-agentcore delete-gateway --gateway-id "$AGENTCORE_GATEWAY_ID" --region "$AWS_REGION" 2>/dev/null || true
    echo "  Gateway deleted"
fi

echo ""
echo "Cleanup complete."
echo "Note: OpenSearch Serverless collection and Bedrock Knowledge Base are NOT deleted."
echo "To remove those, delete collection 'supply-chain-parts' and Knowledge Base '$BEDROCK_KNOWLEDGE_BASE_ID' in the AWS console."
