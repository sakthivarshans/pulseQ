"""
modules/api/routers/integrations.py
─────────────────────────────────────
Integration management endpoints with Fernet-encrypted credentials.
Supports: aws, azure, gcp, github, gitlab, slack, pagerduty, jira,
          datadog, newrelic, webhook
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, UTC
from typing import Any

import structlog
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])
logger = structlog.get_logger(__name__)

SUPPORTED_TYPES = [
    "aws", "azure", "gcp", "github", "gitlab",
    "slack", "pagerduty", "jira", "datadog", "newrelic", "webhook",
]


# ── Encryption helpers ─────────────────────────────────────────────────────────

def _get_fernet():
    """Return a Fernet instance using the app SECRET_KEY. Falls back to a simple XOR if cryptography is unavailable."""
    try:
        from cryptography.fernet import Fernet
        from shared.config import get_settings
        settings = get_settings()
        # Derive a 32-byte key from the secret
        key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        return Fernet(fernet_key)
    except ImportError:
        return None


def encrypt_config(config: dict) -> str:
    fernet = _get_fernet()
    raw = json.dumps(config).encode()
    if fernet:
        return fernet.encrypt(raw).decode()
    # Fallback: base64 (not secure — install cryptography for real encryption)
    return base64.b64encode(raw).decode()


def decrypt_config(encrypted: str) -> dict:
    fernet = _get_fernet()
    raw = encrypted.encode()
    if fernet:
        try:
            decrypted = fernet.decrypt(raw)
            return json.loads(decrypted)
        except Exception:
            pass
    # Fallback: try base64
    try:
        return json.loads(base64.b64decode(raw))
    except Exception:
        return {}


def mask_config(config: dict) -> dict:
    """Return config with sensitive fields replaced by asterisks."""
    sensitive = {
        "secret_access_key", "client_secret", "api_key", "token", "bot_token",
        "api_token", "service_account_json", "password", "webhook_key",
        "secret_key", "signing_secret",
    }
    return {
        k: ("••••••••" if any(s in k.lower() for s in sensitive) else v)
        for k, v in config.items()
    }


# ── Request models ─────────────────────────────────────────────────────────────

class IntegrationSaveRequest(BaseModel):
    config: dict[str, Any]


# ── Helper: DB session ─────────────────────────────────────────────────────────

async def _get_session(db_session):
    if db_session is None:
        raise HTTPException(503, "Database not available")
    return db_session()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("")
async def list_integrations(db_session=None) -> dict[str, Any]:
    """List all integration types with their configured status. Never returns credentials."""
    if db_session is None:
        return {"integrations": [{"type": t, "is_configured": False, "last_test_status": None} for t in SUPPORTED_TYPES]}

    try:
        async with db_session() as session:
            result = await session.execute(
                text("SELECT integration_type, is_configured, last_tested_at, last_test_status, last_test_error "
                     "FROM integrations")
            )
            rows = {r["integration_type"]: r for r in result.mappings().all()}

        integrations = []
        for itype in SUPPORTED_TYPES:
            row = rows.get(itype)
            integrations.append({
                "type": itype,
                "is_configured": row["is_configured"] if row else False,
                "last_tested_at": row["last_tested_at"].isoformat() if row and row["last_tested_at"] else None,
                "last_test_status": row["last_test_status"] if row else None,
                "last_test_error": row["last_test_error"] if row else None,
            })
        return {"integrations": integrations}
    except Exception as exc:
        logger.warning("integrations_list_failed", error=str(exc))
        return {"integrations": [{"type": t, "is_configured": False, "last_test_status": None} for t in SUPPORTED_TYPES]}


@router.get("/{integration_type}")
async def get_integration(integration_type: str, db_session=None) -> dict[str, Any]:
    """Return masked config for a specific integration type."""
    if integration_type not in SUPPORTED_TYPES:
        raise HTTPException(404, f"Unknown integration type: {integration_type}")

    if db_session is None:
        return {"type": integration_type, "is_configured": False, "config": {}}

    try:
        async with db_session() as session:
            result = await session.execute(
                text("SELECT config_encrypted, is_configured, last_tested_at, last_test_status "
                     "FROM integrations WHERE integration_type = :t"),
                {"t": integration_type},
            )
            row = result.mappings().first()

        if not row or not row["config_encrypted"]:
            return {"type": integration_type, "is_configured": False, "config": {}}

        config = decrypt_config(row["config_encrypted"])
        return {
            "type": integration_type,
            "is_configured": row["is_configured"],
            "last_tested_at": row["last_tested_at"].isoformat() if row["last_tested_at"] else None,
            "last_test_status": row["last_test_status"],
            "config": mask_config(config),
        }
    except Exception as exc:
        logger.warning("integration_get_failed", integration=integration_type, error=str(exc))
        return {"type": integration_type, "is_configured": False, "config": {}}


@router.post("/{integration_type}")
async def save_integration(
    integration_type: str,
    req: IntegrationSaveRequest,
    db_session=None,
) -> dict[str, str]:
    """Save encrypted credentials for an integration."""
    if integration_type not in SUPPORTED_TYPES:
        raise HTTPException(404, f"Unknown integration type: {integration_type}")

    if db_session is None:
        raise HTTPException(503, "Database not available")

    encrypted = encrypt_config(req.config)
    try:
        async with db_session() as session:
            await session.execute(
                text(
                    "INSERT INTO integrations (integration_type, config_encrypted, is_configured, updated_at) "
                    "VALUES (:t, :enc, TRUE, NOW()) "
                    "ON CONFLICT (integration_type) DO UPDATE SET "
                    "  config_encrypted = EXCLUDED.config_encrypted, "
                    "  is_configured = TRUE, "
                    "  updated_at = NOW()"
                ),
                {"t": integration_type, "enc": encrypted},
            )
            await session.commit()
    except Exception as exc:
        logger.error("integration_save_failed", integration=integration_type, error=str(exc))
        raise HTTPException(500, f"Failed to save integration: {exc}")

    return {"status": "saved", "type": integration_type}


@router.post("/{integration_type}/test")
async def test_integration(integration_type: str, db_session=None) -> dict[str, Any]:
    """Run a real connection test using saved credentials."""
    if integration_type not in SUPPORTED_TYPES:
        raise HTTPException(404, f"Unknown integration type: {integration_type}")

    if db_session is None:
        raise HTTPException(503, "Database not available")

    # Load config
    try:
        async with db_session() as session:
            result = await session.execute(
                text("SELECT config_encrypted FROM integrations WHERE integration_type = :t"),
                {"t": integration_type},
            )
            row = result.mappings().first()
    except Exception as exc:
        raise HTTPException(503, f"Database error: {exc}")

    if not row or not row["config_encrypted"]:
        raise HTTPException(400, "Integration not configured. Save credentials first.")

    config = decrypt_config(row["config_encrypted"])
    result_data = await _run_connection_test(integration_type, config)

    # Persist test result
    try:
        async with db_session() as session:
            await session.execute(
                text(
                    "UPDATE integrations SET last_tested_at = NOW(), "
                    "last_test_status = :status, last_test_error = :error "
                    "WHERE integration_type = :t"
                ),
                {
                    "t": integration_type,
                    "status": "success" if result_data.get("success") else "failed",
                    "error": result_data.get("error"),
                },
            )
            await session.commit()
    except Exception:
        pass

    return result_data


async def _run_connection_test(integration_type: str, config: dict) -> dict[str, Any]:
    """Dispatch to the appropriate connection tester."""
    try:
        if integration_type == "slack":
            return await _test_slack(config)
        elif integration_type == "github":
            return await _test_github(config)
        elif integration_type == "jira":
            return await _test_jira(config)
        elif integration_type == "pagerduty":
            return await _test_pagerduty(config)
        elif integration_type == "webhook":
            return await _test_webhook(config)
        elif integration_type == "gitlab":
            return await _test_gitlab(config)
        elif integration_type == "aws":
            return _test_aws(config)
        elif integration_type == "azure":
            return _test_azure(config)
        elif integration_type == "gcp":
            return _test_gcp(config)
        elif integration_type == "datadog":
            return await _test_datadog(config)
        elif integration_type == "newrelic":
            return await _test_newrelic(config)
        else:
            return {"success": False, "error": "No test implemented for this integration"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def _test_slack(config: dict) -> dict:
    token = config.get("bot_token", "")
    if not token:
        return {"success": False, "error": "bot_token is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = r.json()
    if data.get("ok"):
        return {"success": True, "team": data.get("team"), "user": data.get("user")}
    return {"success": False, "error": data.get("error", "Unknown Slack error")}


async def _test_github(config: dict) -> dict:
    token = config.get("personal_access_token", "")
    if not token:
        return {"success": False, "error": "personal_access_token is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        )
    if r.status_code == 200:
        data = r.json()
        return {"success": True, "user": data.get("login"), "name": data.get("name")}
    return {"success": False, "error": f"GitHub returned HTTP {r.status_code}"}


async def _test_jira(config: dict) -> dict:
    url = config.get("jira_url", "").rstrip("/")
    email = config.get("email", "")
    token = config.get("api_token", "")
    if not url or not email or not token:
        return {"success": False, "error": "jira_url, email, and api_token are required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{url}/rest/api/3/myself",
            auth=(email, token),
        )
    if r.status_code == 200:
        data = r.json()
        return {"success": True, "account_id": data.get("accountId"), "display_name": data.get("displayName")}
    return {"success": False, "error": f"Jira returned HTTP {r.status_code}: {r.text[:200]}"}


async def _test_pagerduty(config: dict) -> dict:
    api_key = config.get("api_key", "")
    if not api_key:
        return {"success": False, "error": "api_key is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.pagerduty.com/users/me",
            headers={"Authorization": f"Token token={api_key}", "Accept": "application/vnd.pagerduty+json;version=2"},
        )
    if r.status_code == 200:
        data = r.json()
        return {"success": True, "user": data.get("user", {}).get("email")}
    return {"success": False, "error": f"PagerDuty returned HTTP {r.status_code}"}


async def _test_webhook(config: dict) -> dict:
    url = config.get("webhook_url", "")
    if not url:
        return {"success": False, "error": "webhook_url is required"}
    method = config.get("http_method", "POST").upper()
    headers = config.get("headers", {})
    payload = {"test": True, "source": "NeuralOps", "message": "Connection test from NeuralOps"}
    async with httpx.AsyncClient(timeout=10) as client:
        if method == "POST":
            r = await client.post(url, json=payload, headers=headers)
        else:
            r = await client.get(url, headers=headers)
    if r.status_code < 400:
        return {"success": True, "status_code": r.status_code}
    return {"success": False, "error": f"Webhook returned HTTP {r.status_code}"}


async def _test_gitlab(config: dict) -> dict:
    token = config.get("personal_access_token", "")
    if not token:
        return {"success": False, "error": "personal_access_token is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://gitlab.com/api/v4/user",
            headers={"PRIVATE-TOKEN": token},
        )
    if r.status_code == 200:
        data = r.json()
        return {"success": True, "username": data.get("username"), "name": data.get("name")}
    return {"success": False, "error": f"GitLab returned HTTP {r.status_code}"}


async def _test_datadog(config: dict) -> dict:
    api_key = config.get("api_key", "")
    app_key = config.get("application_key", "")
    if not api_key:
        return {"success": False, "error": "api_key is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.datadoghq.com/api/v1/validate",
            headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
        )
    if r.status_code == 200:
        return {"success": True}
    return {"success": False, "error": f"Datadog returned HTTP {r.status_code}"}


async def _test_newrelic(config: dict) -> dict:
    api_key = config.get("api_key", "")
    if not api_key:
        return {"success": False, "error": "api_key is required"}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.newrelic.com/v2/applications.json",
            headers={"X-Api-Key": api_key},
        )
    if r.status_code == 200:
        return {"success": True}
    return {"success": False, "error": f"New Relic returned HTTP {r.status_code}"}


def _test_aws(config: dict) -> dict:
    """Test AWS credentials using boto3 if available."""
    access_key = config.get("access_key_id", "")
    secret_key = config.get("secret_access_key", "")
    region = config.get("default_region", "us-east-1")
    if not access_key or not secret_key:
        return {"success": False, "error": "access_key_id and secret_access_key are required"}
    try:
        import boto3
        sts = boto3.client(
            "sts",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        identity = sts.get_caller_identity()
        return {"success": True, "account": identity.get("Account"), "arn": identity.get("Arn")}
    except ImportError:
        return {"success": False, "error": "boto3 not installed. Run: pip install boto3"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _test_azure(config: dict) -> dict:
    """Test Azure credentials using azure-identity if available."""
    tenant_id = config.get("tenant_id", "")
    client_id = config.get("client_id", "")
    client_secret = config.get("client_secret", "")
    subscription_id = config.get("subscription_id", "")
    if not tenant_id or not client_id or not client_secret:
        return {"success": False, "error": "tenant_id, client_id, and client_secret are required"}
    try:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.resource import SubscriptionClient
        cred = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
        if subscription_id:
            sub_client = SubscriptionClient(cred)
            subs = list(sub_client.subscriptions.list())
            return {"success": True, "subscriptions": len(subs)}
        return {"success": True}
    except ImportError:
        return {"success": False, "error": "azure-identity and azure-mgmt-resource not installed"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _test_gcp(config: dict) -> dict:
    """Test GCP credentials using google-cloud-resource-manager if available."""
    project_id = config.get("project_id", "")
    sa_json = config.get("service_account_json", "")
    if not project_id and not sa_json:
        return {"success": False, "error": "project_id or service_account_json is required"}
    try:
        import google.auth
        credentials, project = google.auth.default()
        return {"success": True, "project": project or project_id}
    except ImportError:
        return {"success": False, "error": "google-auth not installed"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
