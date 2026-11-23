"""Contrat et qualité observés du benchmark original, sans altérer les fichiers."""

import collections
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path

r = Path(__file__).resolve().parents[1]
folder = r / "data/raw/banking77"
categories = json.loads((folder / "categories.json").read_text())
parts = {}


def norm(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


for name in ["train", "test"]:
    with (folder / (name + ".csv")).open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["text", "category"]
        rows = list(reader)
    groups = collections.defaultdict(set)
    for row in rows:
        groups[norm(row["text"])].add(row["category"])
    counts = collections.Counter(row["category"] for row in rows)
    empty = sum(not row["text"].strip() or not row["category"] for row in rows)
    unknown = sorted(set(counts) - set(categories))
    assert not empty and not unknown
    parts[name] = {
        "rows": len(rows),
        "categories": len(counts),
        "min_class_rows": min(counts.values()),
        "max_class_rows": max(counts.values()),
        "empty_rows": empty,
        "unknown_categories": unknown,
        "duplicate_normalized_rows": len(rows) - len(groups),
        "normalized_groups_with_conflicting_labels": sum(
            len(labels) > 1 for labels in groups.values()
        ),
        "class_counts": dict(sorted(counts.items())),
        "sha256": hashlib.sha256((folder / (name + ".csv")).read_bytes()).hexdigest(),
    }
result = {
    "source": "Original pinned BANKING77, no user customer records",
    "language": "English",
    "declared_categories": len(categories),
    "partitions": parts,
}
assert parts["train"]["rows"] == 10003 and parts["test"]["rows"] == 3080 and len(categories) == 77
out = r / "docs/evidence/mlops/data-quality.json"
out.write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: {
                key: v[key]
                for key in [
                    "rows",
                    "categories",
                    "empty_rows",
                    "duplicate_normalized_rows",
                    "normalized_groups_with_conflicting_labels",
                ]
            }
            for k, v in parts.items()
        }
    )
)
