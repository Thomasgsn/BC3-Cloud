"""Profilage local sans contenu client dans les résultats, pas de changement de données."""

import cProfile
import inspect
import json
import pstats
import time

from rncp_bc3 import db
from rncp_bc3.api import view_ticket
from rncp_bc3.security import key

with db.connect() as c:
    rows = c.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 200").fetchall()
supports_key = "encryption_key" in inspect.signature(view_ticket).parameters
profiler = cProfile.Profile()
start = time.perf_counter()
profiler.enable()
for _ in range(10):
    material = key() if supports_key else None
    for row in rows:
        view_ticket(row, encryption_key=material) if supports_key else view_ticket(row)
profiler.disable()
elapsed = time.perf_counter() - start
stats = pstats.Stats(profiler)
selected = []
for (_file, _line, name), (_primitive, calls, total, cumulative, _callers) in stats.stats.items():
    if (
        name in ["key", "secrets", "read_text", "open", "decrypt", "view_ticket"]
        or "io.open" in name
    ):
        selected.append(
            {
                "function": name,
                "calls": calls,
                "self_seconds": total,
                "cumulative_seconds": cumulative,
            }
        )
result = {
    "real_sql_rows": len(rows),
    "repeats": 10,
    "elapsed_seconds": elapsed,
    "profile": sorted(selected, key=lambda v: -v["cumulative_seconds"]),
    "scope": "In-process function profile, no HTTP latency claim, no ticket contents output",
}
print(json.dumps(result))
