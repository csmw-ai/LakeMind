from __future__ import annotations
import hashlib
from datetime import datetime, timezone
import ulid
from ..db import execute, execute_one
from ..security.context import SecurityContext
from .asset_service import AssetService
from .audit_service import AuditService


def _ulid(prefix: str) -> str:
    return f"{prefix}_{str(ulid.new())}"


class SkillService:

    @staticmethod
    def register(ctx: SecurityContext, manifest: dict, code_package: bytes | dict,
                 trust_level: str = "untrusted") -> dict:
        asset = AssetService.create_asset(
            ctx, asset_type="skill", name=manifest.get("name", "unnamed"),
            source_type="upload", metadata={"manifest": manifest},
            version=manifest.get("version", "1.0.0"),
        )
        asset_id = asset["asset_id"]

        if isinstance(code_package, dict):
            code_checksum = hashlib.sha256(
                code_package.get("s3_uri", "").encode()
            ).hexdigest()
        else:
            code_checksum = hashlib.sha256(code_package).hexdigest()

        execute(
            "INSERT INTO skill_meta (asset_id, manifest, code_checksum, entry_point, "
            "input_schema, output_schema, dependencies, permissions, model_profiles, "
            "secret_declarations, resource_needs, network_needs, trust_level, publish_status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'DRAFT')",
            (asset_id, manifest, code_checksum,
             manifest.get("entry_point", ""),
             manifest.get("input_schema", {}),
             manifest.get("output_schema", {}),
             manifest.get("dependencies", []),
             manifest.get("permissions", []),
             manifest.get("model_profiles", []),
             manifest.get("secret_declarations", []),
             manifest.get("resource_needs", {}),
             manifest.get("network_needs", {}),
             trust_level),
        )

        AssetService.create_binding(
            asset_id=asset_id,
            binding_type="SKILL_PACKAGE",
            provider="seaweedfs",
            physical_uri=f"{ctx.tenant_id}/{asset_id}/skill_package",
            is_required=True,
            checksum=code_checksum,
        )

        return {"asset_id": asset_id, "name": manifest.get("name"), "status": "DRAFT", "checksum": code_checksum}

    @staticmethod
    def validate(ctx: SecurityContext, skill_id: str) -> dict:
        row = execute_one("SELECT * FROM skill_meta WHERE asset_id = %s", (skill_id,))
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")

        errors: list[str] = []
        manifest = row["manifest"]
        for field in ["name", "version", "entry_point", "input_schema", "output_schema"]:
            if not manifest.get(field):
                errors.append(f"Missing required field: {field}")

        if errors:
            return {"skill_id": skill_id, "is_valid": False, "errors": errors}

        return {"skill_id": skill_id, "is_valid": True, "errors": []}

    @staticmethod
    def publish(ctx: SecurityContext, skill_id: str) -> dict:
        row = execute_one("SELECT publish_status FROM skill_meta WHERE asset_id = %s", (skill_id,))
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        if row["publish_status"] != "DRAFT":
            raise ValueError("SKILL_VERSION_IMMUTABLE")

        validation = SkillService.validate(ctx, skill_id)
        if not validation["is_valid"]:
            raise ValueError(f"Validation failed: {validation['errors']}")

        execute(
            "UPDATE skill_meta SET publish_status = 'PUBLISHED', published_by = %s, published_at = %s "
            "WHERE asset_id = %s",
            (ctx.principal_id, datetime.now(timezone.utc), skill_id),
        )
        AuditService.record(
            event_type="skill.publish",
            principal_id=ctx.principal_id,
            tenant_id=ctx.tenant_id,
            resource_id=skill_id,
            action="publish_skill",
            result="success",
        )
        return {"skill_id": skill_id, "publish_status": "PUBLISHED"}

    @staticmethod
    def revoke(ctx: SecurityContext, skill_id: str, reason: str) -> dict:
        execute(
            "UPDATE skill_meta SET publish_status = 'REVOKED' WHERE asset_id = %s",
            (skill_id,),
        )
        AuditService.record(
            event_type="skill.revoke",
            principal_id=ctx.principal_id,
            tenant_id=ctx.tenant_id,
            resource_id=skill_id,
            action="revoke_skill",
            result="success",
            details={"reason": reason},
        )
        return {"skill_id": skill_id, "publish_status": "REVOKED"}

    @staticmethod
    def get_skill(ctx: SecurityContext, name: str, version: str) -> dict | None:
        _cols = "a.*, s.manifest, s.code_checksum, s.publish_status, s.trust_level, s.entry_point"
        if version == "latest":
            return execute_one(
                f"SELECT {_cols} "
                "FROM assets a JOIN skill_meta s ON a.asset_id = s.asset_id "
                "WHERE a.tenant_id = %s AND a.name = %s AND a.deleted_at IS NULL "
                "ORDER BY a.created_at DESC LIMIT 1",
                (ctx.tenant_id, name),
            )
        return execute_one(
            f"SELECT {_cols} "
            "FROM assets a JOIN skill_meta s ON a.asset_id = s.asset_id "
            "WHERE a.tenant_id = %s AND a.name = %s AND a.version = %s",
            (ctx.tenant_id, name, version),
        )

    @staticmethod
    def list_skills(ctx: SecurityContext, publish_status: str | None = None,
                    page: int = 1, page_size: int = 50) -> dict:
        query = ("SELECT a.asset_id, a.name, a.version, s.publish_status, s.trust_level "
                 "FROM assets a JOIN skill_meta s ON a.asset_id = s.asset_id "
                 "WHERE a.tenant_id = %s AND a.deleted_at IS NULL")
        params: list = [ctx.tenant_id]
        if publish_status:
            query += " AND s.publish_status = %s"; params.append(publish_status)
        query += " ORDER BY a.created_at DESC"
        items = execute(query, tuple(params))
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def is_executable(skill_id: str) -> bool:
        row = execute_one(
            "SELECT publish_status FROM skill_meta WHERE asset_id = %s",
            (skill_id,),
        )
        if row is None:
            return False
        return row["publish_status"] == "PUBLISHED"
