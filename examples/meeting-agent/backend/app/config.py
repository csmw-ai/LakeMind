from __future__ import annotations
import os

SERVER_URL = os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823").rstrip("/")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "")
TENANT_ID = os.environ.get("TENANT_ID", "examples-meeting-agent")
MS_URL = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824").rstrip("/")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "")
SKILL_REF = os.environ.get("SKILL_REF", "lake://skills/meeting-processing@0.2.0")
S3_BUCKET = os.environ.get("S3_BUCKET", "lakemind-filesets")
DB_PATH = os.environ.get("DB_PATH", "/data/meeting-agent.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "meeting-agent-demo-secret-key")
CHUNK_DURATION_MS = int(os.environ.get("CHUNK_DURATION_MS", "20000"))
SUMMARIZE_INTERVAL = int(os.environ.get("SUMMARIZE_INTERVAL", "6"))

ASSET_MCP_URL = os.environ.get("ASSET_MCP_URL", "http://lakemind-asset-mcp:8401/mcp")
DATA_MCP_URL = os.environ.get("DATA_MCP_URL", "http://lakemind-data-mcp:8402/mcp")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "meeting-agent-mcp-token")
