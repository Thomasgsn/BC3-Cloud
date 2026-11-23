"""Suggestion anglaise supervisée, artefact du build vérifié avant désérialisation."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from prometheus_client import Counter

PREDICTIONS = Counter("bc3_intent_predictions_total", "Suggestions d’intention", ["version"])


@lru_cache(maxsize=1)
def load():
    root = Path(os.getenv("BC3_MODEL_DIR", "/app/models"))
    manifest = json.loads((root / "active.json").read_text())
    version = manifest["version"]
    if Path(version).name != version:
        raise ValueError("Version modèle invalide")
    path = root / version / "model.joblib"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["model_sha256"]:
        raise ValueError("Intégrité modèle invalide")
    # Ce chemin appartient à l’image construite, jamais à un upload utilisateur.
    import joblib

    return manifest, joblib.load(path)


def suggest(text):
    manifest, model = load()
    scores = model.decision_function([text])[0]
    indices = scores.argsort()[-3:][::-1]
    PREDICTIONS.labels(manifest["version"]).inc()
    return {
        "model_version": manifest["version"],
        "language": "en",
        "suggestions": [
            {"category": str(model.classes_[i]), "margin": float(scores[i])} for i in indices
        ],
        "notice": "Texte anglais uniquement. Les marges ne sont pas des probabilités. Suggestion à confirmer humainement.",
    }
