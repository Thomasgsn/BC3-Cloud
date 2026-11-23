"""Inventaire de conservation en lecture seule ; aucune suppression implémentée."""

from datetime import UTC, datetime, timedelta

from . import db, storage


def age_bucket(modified, now, days):
    if modified.tzinfo is None or now.tzinfo is None or days <= 0:
        raise ValueError("Dates avec fuseau et durée positive requises")
    if modified > now:
        return "future_timestamp"
    return (
        "past_proposed_retention"
        if modified <= now - timedelta(days=days)
        else "within_proposed_retention"
    )


def inventory(export_days=7, audit_days=30, backup_days=180, object_limit=5000):
    if min(export_days, audit_days, backup_days, object_limit) <= 0:
        raise ValueError("Durées et plafond strictement positifs requis")
    now = datetime.now(UTC)
    with db.connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        sql = conn.execute(
            """SELECT
            (SELECT count(*) FROM sessions WHERE expires_at <= %s) expired_sessions,
            (SELECT count(*) FROM exports WHERE status='complete' AND updated_at <= %s) completed_exports_past_proposal,
            (SELECT count(*) FROM exports WHERE status IN ('pending','processing')) protected_active_exports,
            (SELECT count(*) FROM audit WHERE at <= %s) audit_rows_past_proposal""",
            (now, now - timedelta(days=export_days), now - timedelta(days=audit_days)),
        ).fetchone()
    objects = {"backups": {}, "exports": {}}
    examined = 0
    for prefix, days in [("backups", backup_days), ("exports", export_days)]:
        pages = (
            storage.client()
            .get_paginator("list_objects_v2")
            .paginate(Bucket=storage.BUCKET, Prefix=prefix + "/")
        )
        for page in pages:
            for obj in page.get("Contents", []):
                examined += 1
                if examined > object_limit:
                    raise ValueError(
                        "Inventaire incomplet : plafond objet dépassé, aucune action effectuée"
                    )
                category = age_bucket(obj["LastModified"], now, days)
                entry = objects[prefix].setdefault(category, {"objects": 0, "encrypted_bytes": 0})
                entry["objects"] += 1
                entry["encrypted_bytes"] += obj["Size"]
    return {
        "event": "retention_read_only_inventory",
        "at_utc": now.isoformat(),
        "policy_status": "proposal_not_approved",
        "mode": "inventory_only_no_deletion",
        "proposed_days": {"exports": export_days, "audit": audit_days, "backups": backup_days},
        "sql": dict(sql),
        "objects": objects,
        "objects_examined": examined,
        "complete_within_limit": True,
        "deleted_rows": 0,
        "deleted_objects": 0,
        "limits": "Age S3 calculé sur LastModified ; aucune équivalence à une durée légale ni à une purge exécutée. Attachments/tickets exclus ; versions S3 et GLACIER non exercés ici.",
    }
