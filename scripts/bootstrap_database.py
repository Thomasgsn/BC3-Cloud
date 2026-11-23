"""Migration avec rôle administratif séparé, puis droits limités du rôle applicatif."""

import json

from psycopg import sql

from rncp_bc3 import db, storage
from rncp_bc3.config import SECRET_DIR

runtime = json.loads((SECRET_DIR / "runtime/config.json").read_text())
db.migrate()
with db.connect() as c:
    exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname='bc3_app'").fetchone()
    if not exists:
        c.execute(
            sql.SQL(
                "CREATE ROLE bc3_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}"
            ).format(sql.Literal(runtime["db_password"]))
        )
    c.execute("GRANT CONNECT ON DATABASE bc3 TO bc3_app")
    c.execute("GRANT USAGE ON SCHEMA public TO bc3_app")
    c.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bc3_app")
    c.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bc3_app")
    c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
    c.execute("REVOKE CREATE ON SCHEMA public FROM bc3_app")
print(
    json.dumps(
        {
            "event": "database_bootstrap",
            "application_role": "bc3_app",
            "superuser": False,
            "create_database": False,
            "create_role": False,
            "schema_creation": False,
            "admin_secret_exposed_to_application": False,
        }
    )
)

# La création de bucket est réservée à cet outil administratif, jamais au rôle applicatif.
storage.initialize()
