"""
provision_knowledge_base.py — One-time setup for the Supplier Agent Knowledge Base

Replaces: AlloyDB ScaNN + Vertex AI text-embedding-005
With:      Amazon Bedrock Knowledge Base (OpenSearch Serverless + Titan Embeddings v2)

Run once before deploying:
    python agentcore/setup/provision_knowledge_base.py

Outputs BEDROCK_KNOWLEDGE_BASE_ID — add to .env.aws
"""

import json
import os
import sys
import time
from pathlib import Path

import boto3
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))
if Path(".env.aws").exists():
    load_dotenv(".env.aws", override=True)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCOUNT_ID = os.environ.get("AWS_ACCOUNT_ID", "")
AGENTCORE_RUNTIME_ROLE_ARN = os.environ.get("AGENTCORE_RUNTIME_ROLE_ARN", "")

COLLECTION_NAME = "supply-chain-parts"
KB_NAME = "supply-chain-inventory-kb"

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_SQL = REPO_ROOT / "database" / "seed_data.sql"


def parse_seed_data(sql_path: Path) -> list[dict]:
    """Extract inventory rows from seed_data.sql as plain-text documents."""
    docs = []
    if not sql_path.exists():
        print(f"WARNING: {sql_path} not found — skipping seed data")
        return docs

    with open(sql_path) as f:
        content = f.read()

    import re
    matches = re.findall(
        r"INSERT INTO.*?VALUES\s*\(([^;]+)\)",
        content,
        re.DOTALL | re.IGNORECASE,
    )

    for match in matches:
        row_values = [v.strip().strip("'") for v in match.split(",")]
        if len(row_values) >= 4:
            doc_text = " ".join(row_values[:6])
            docs.append({"text": doc_text})

    print(f"Parsed {len(docs)} inventory items from seed_data.sql")
    return docs


def provision():
    if not AWS_ACCOUNT_ID:
        print("ERROR: AWS_ACCOUNT_ID not set in .env.aws")
        sys.exit(1)
    if not AGENTCORE_RUNTIME_ROLE_ARN:
        print("ERROR: AGENTCORE_RUNTIME_ROLE_ARN not set in .env.aws")
        sys.exit(1)

    aoss = boto3.client("opensearchserverless", region_name=AWS_REGION)
    bedrock_agent = boto3.client("bedrock-agent", region_name=AWS_REGION)
    s3 = boto3.client("s3", region_name=AWS_REGION)

    bucket_name = f"supply-chain-kb-{AWS_ACCOUNT_ID}-{AWS_REGION}"

    # ── S3 bucket for seed documents ──────────────────────────
    print(f"\n[1/5] Creating S3 bucket: {bucket_name}")
    try:
        if AWS_REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
            )
        print(f"      Created: {bucket_name}")
    except s3.exceptions.BucketAlreadyOwnedByYou:
        print(f"      Already exists: {bucket_name}")

    docs = parse_seed_data(SEED_SQL)
    for i, doc in enumerate(docs):
        key = f"inventory/item_{i:03d}.txt"
        s3.put_object(Bucket=bucket_name, Key=key, Body=doc["text"].encode())
    print(f"      Uploaded {len(docs)} documents")

    # ── OpenSearch Serverless collection ───────────────────────
    print(f"\n[2/5] Creating OpenSearch Serverless collection: {COLLECTION_NAME}")
    try:
        resp = aoss.create_collection(
            name=COLLECTION_NAME,
            type="VECTORSEARCH",
            description="Supply chain parts inventory for semantic search",
        )
        collection_id = resp["createCollectionDetail"]["id"]
        collection_arn = resp["createCollectionDetail"]["arn"]
        print(f"      Created collection: {collection_id}")
    except aoss.exceptions.ConflictException:
        existing = aoss.list_collections(collectionFilters={"name": COLLECTION_NAME})
        collection_id = existing["collectionSummaries"][0]["id"]
        collection_arn = existing["collectionSummaries"][0]["arn"]
        print(f"      Already exists: {collection_id}")

    # Wait for collection to become active
    print("      Waiting for collection to become ACTIVE...")
    for _ in range(30):
        status = aoss.batch_get_collection(ids=[collection_id])
        state = status["collectionDetails"][0]["status"]
        if state == "ACTIVE":
            break
        print(f"      Status: {state} — waiting...")
        time.sleep(10)
    print("      Collection ACTIVE")

    # ── Access policy ──────────────────────────────────────────
    print("\n[3/5] Setting OpenSearch access policy...")
    policy_name = f"{COLLECTION_NAME}-access"
    try:
        aoss.create_access_policy(
            name=policy_name,
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "index", "Resource": [f"index/{COLLECTION_NAME}/*"],
                     "Permission": ["aoss:CreateIndex", "aoss:DescribeIndex",
                                    "aoss:ReadDocument", "aoss:WriteDocument",
                                    "aoss:UpdateIndex", "aoss:DeleteIndex"]},
                    {"ResourceType": "collection", "Resource": [f"collection/{COLLECTION_NAME}"],
                     "Permission": ["aoss:CreateCollectionItems", "aoss:DescribeCollectionItems",
                                    "aoss:DeleteCollectionItems", "aoss:UpdateCollectionItems"]},
                ],
                "Principal": [AGENTCORE_RUNTIME_ROLE_ARN],
            }]),
        )
        print(f"      Access policy created: {policy_name}")
    except aoss.exceptions.ConflictException:
        print(f"      Access policy already exists: {policy_name}")

    # ── Bedrock Knowledge Base ─────────────────────────────────
    print(f"\n[4/5] Creating Bedrock Knowledge Base: {KB_NAME}")
    try:
        kb_resp = bedrock_agent.create_knowledge_base(
            name=KB_NAME,
            description="Supply chain parts inventory — Titan Embeddings v2 + OpenSearch Serverless",
            roleArn=AGENTCORE_RUNTIME_ROLE_ARN,
            knowledgeBaseConfiguration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": f"arn:aws:bedrock:{AWS_REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                },
            },
            storageConfiguration={
                "type": "OPENSEARCH_SERVERLESS",
                "opensearchServerlessConfiguration": {
                    "collectionArn": collection_arn,
                    "vectorIndexName": "supply-chain-index",
                    "fieldMapping": {
                        "vectorField": "embedding",
                        "textField": "text",
                        "metadataField": "metadata",
                    },
                },
            },
        )
        kb_id = kb_resp["knowledgeBase"]["knowledgeBaseId"]
        print(f"      Knowledge Base created: {kb_id}")
    except bedrock_agent.exceptions.ConflictException:
        existing = bedrock_agent.list_knowledge_bases()
        kb_id = next(
            kb["knowledgeBaseId"]
            for kb in existing["knowledgeBaseSummaries"]
            if kb["name"] == KB_NAME
        )
        print(f"      Already exists: {kb_id}")

    # ── Data source + ingestion ────────────────────────────────
    print(f"\n[5/5] Creating data source and starting ingestion...")
    try:
        ds_resp = bedrock_agent.create_data_source(
            knowledgeBaseId=kb_id,
            name="inventory-s3",
            dataSourceConfiguration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": f"arn:aws:s3:::{bucket_name}",
                    "inclusionPrefixes": ["inventory/"],
                },
            },
        )
        ds_id = ds_resp["dataSource"]["dataSourceId"]
        print(f"      Data source created: {ds_id}")
    except bedrock_agent.exceptions.ConflictException:
        sources = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)
        ds_id = sources["dataSourceSummaries"][0]["dataSourceId"]
        print(f"      Data source already exists: {ds_id}")

    ingest_resp = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    job_id = ingest_resp["ingestionJob"]["ingestionJobId"]
    print(f"      Ingestion job started: {job_id}")

    print("\n" + "=" * 60)
    print("PROVISIONING COMPLETE")
    print("=" * 60)
    print(f"\nBEDROCK_KNOWLEDGE_BASE_ID={kb_id}")
    print(f"BEDROCK_DATA_SOURCE_ID={ds_id}")
    print(f"\nAdd these to your .env.aws file.")
    print(f"\nIngestion job {job_id} is running in the background.")
    print("Wait ~2 minutes before running the supplier agent.\n")


if __name__ == "__main__":
    provision()
