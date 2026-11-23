"""BANKING77 original : validation groupée, test officiel réservé, modèles versionnés."""

import csv
import datetime
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

ROOT = Path("/workspace")
data = ROOT / "data/raw/banking77"
out = ROOT / "models"
out.mkdir(exist_ok=True)
lock = json.loads((ROOT / "infra/banking77.lock.json").read_text())
for name, info in lock["files"].items():
    assert hashlib.sha256((data / name).read_bytes()).hexdigest() == info["sha256"], name


def read(name):
    with (data / name).open(newline="") as f:
        return list(csv.DictReader(f))


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).casefold()).strip()


train = read("train.csv")
test = read("test.csv")
testgroups = {norm(r["text"]) for r in test}
removed = sum(norm(r["text"]) in testgroups for r in train)
train = [r for r in train if norm(r["text"]) not in testgroups]
x = np.array([r["text"] for r in train])
y = np.array([r["category"] for r in train])
groups = np.array([norm(s) for s in x])
tr, va = next(StratifiedGroupKFold(5, shuffle=True, random_state=42).split(x, y, groups))
assert not set(groups[tr]) & set(groups[va])
assert not set(groups) & testgroups
baseline = DummyClassifier(strategy="most_frequent").fit(np.zeros((len(tr), 1)), y[tr])
baseline_f1 = f1_score(y[va], baseline.predict(np.zeros((len(va), 1))), average="macro")
protocol = {
    "split": "first fold StratifiedGroupKFold(5,shuffle=True,seed=42), groups=NFKC/casefold/whitespace",
    "candidate_C": [0.25, 1.0],
    "selection": "validation macro F1 only; official test used once after selection",
    "promotion_floor_macro_f1": 0.75,
    "max_validation_regression": 0.02,
    "language": "English only; not a language detector; margin not calibrated probability",
    "train_rows_original": 10003,
    "train_rows_after_cross_split_removal": len(train),
    "test_rows": len(test),
    "removed_train_rows_matching_official_test": removed,
    "duplicate_train_normalized_rows": len(train) - len(set(groups)),
    "validation_rows": len(va),
    "fit_rows": len(tr),
    "dummy_validation_macro_f1": baseline_f1,
    "dataset_revision": lock["revision"],
}
(ROOT / "docs/evidence/mlops").mkdir(exist_ok=True)
(ROOT / "docs/evidence/mlops/protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
candidates = []
for C in protocol["candidate_C"]:
    model = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("classifier", LinearSVC(C=C, random_state=42)),
        ]
    )
    model.fit(x[tr], y[tr])
    pred = model.predict(x[va])
    version = "banking77-c" + str(C).replace(".", "-")
    folder = out / version
    folder.mkdir(exist_ok=True)
    joblib.dump(model, folder / "model.joblib", compress=3)
    manifest = {
        "version": version,
        "C": C,
        "validation_macro_f1": f1_score(y[va], pred, average="macro"),
        "validation_accuracy": accuracy_score(y[va], pred),
        "model_sha256": hashlib.sha256((folder / "model.joblib").read_bytes()).hexdigest(),
        "dataset": lock,
        "trusted_local_pipeline": True,
        "language": "en",
        "created_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    candidates.append((manifest, model))
    print(
        json.dumps(
            {k: manifest[k] for k in ["version", "validation_macro_f1", "validation_accuracy"]}
        ),
        flush=True,
    )
best, model = max(candidates, key=lambda item: item[0]["validation_macro_f1"])
xt = [r["text"] for r in test]
yt = [r["category"] for r in test]
pred = model.predict(xt)
scores = model.decision_function(xt)
classes = model.classes_
top3 = classes[np.argsort(scores, axis=1)[:, -3:]]
report = {
    "selected_version": best["version"],
    "selection_frozen_before_test": True,
    "test_accuracy": accuracy_score(yt, pred),
    "test_macro_f1": f1_score(yt, pred, average="macro"),
    "test_top3_accuracy": float(
        np.mean([label in top for label, top in zip(yt, top3, strict=True)])
    ),
    "classification_report": classification_report(yt, pred, output_dict=True),
    "labels": classes.tolist(),
    "confusion_matrix": confusion_matrix(yt, pred, labels=classes).tolist(),
    "limitations": [
        "Public benchmark English, no customer distribution or fairness guarantee",
        "Test examples never included in TF-IDF fit",
        "No calibrated probability, no autonomous financial decision",
    ],
}
(ROOT / "docs/evidence/mlops/evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
print(
    json.dumps(
        {
            k: report[k]
            for k in [
                "selected_version",
                "test_accuracy",
                "test_macro_f1",
                "test_top3_accuracy",
            ]
        }
    ),
    flush=True,
)
