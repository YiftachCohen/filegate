"""A small classifier trained on your own scanner history (`filegate train`).

Frozen gte-modernbert-base embedding (Apache-2.0, CPU) of path + file head,
plus inventory signals and the file kind -> logistic regression. Trained only
on files the policy gates (tests, config, JS/TS). Loads from models_dir only.
"""
from __future__ import annotations

import os
from pathlib import Path

from .facts import state

SIGNALS = ("remote_url", "script", "secret", "exec_like", "code_import", "style_import", "test_path")
KINDS = ("test", "config", "js")
EMBEDDER = "gte-modernbert-base"


def _need():
    try:
        import joblib, numpy, sklearn, sentence_transformers  # noqa: F401
    except ImportError as e:
        raise SystemExit("the trained head needs: pip install 'filegate[head]'") from e


def _embedder(models_dir: str):
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer
    p = Path(models_dir) / EMBEDDER
    if not p.exists():
        raise SystemExit(f"no embedder at {p}; run `filegate fetch-models --with head` first")
    m = SentenceTransformer(str(p), device="cpu")
    m.max_seq_length = 512
    return m


def _hand(f: dict, kind: str) -> list[float]:
    import math
    return ([float(bool(f.get(k))) for k in SIGNALS] + [float(kind == k) for k in KINDS]
            + [math.log1p(f["bytes"])])


def train(rows: list[tuple[dict, str, int, str]], models_dir: str, out: str) -> dict:
    """rows: (features, kind, label 0/1, group). Grouped CV report + final model saved to `out`."""
    _need()
    import joblib, numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    emb = _embedder(models_dir)
    E = emb.encode([state(f) for f, *_ in rows], batch_size=16, normalize_embeddings=True, show_progress_bar=True)
    X = np.hstack([E, np.array([_hand(f, k) for f, k, *_ in rows])])
    y = np.array([lab for _, _, lab, _ in rows])
    g = np.array([grp for *_, grp in rows])

    def model():
        return make_pipeline(StandardScaler(), LogisticRegression(C=0.05, class_weight="balanced", max_iter=5000))

    report = {"files": len(rows), "positives": int(y.sum()), "groups": len(set(g))}
    if len(set(g)) >= 3 and 0 < y.sum() < len(y):
        oof = np.zeros(len(y))
        for tr, te in GroupKFold(min(5, len(set(g)))).split(X, y, g):
            oof[te] = model().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        report["cv_auroc_grouped"] = float(roc_auc_score(y, oof))
    joblib.dump({"model": model().fit(X, y), "embedder": EMBEDDER, "kinds": KINDS}, out)
    return report


class HeadScorer:
    """Backend 'head': answer() returns {"head": p}. Falls back to regex facts if no trained head exists."""
    name = "head"

    def __init__(self, cfg: dict):
        p = Path(cfg["models_dir"]) / cfg["head"]["path"]
        if not p.exists():
            from .facts.regex import RegexFacts
            print(f"[filegate] no trained head at {p}; using regex facts")
            self.fallback, self.name = RegexFacts(cfg), "regex"
            return
        _need()
        import joblib
        self.fallback = None
        self.bundle = joblib.load(p)
        self.emb = _embedder(cfg["models_dir"])

    def answer(self, f: dict, kind: str) -> dict[str, float]:
        if self.fallback:
            return self.fallback.answer(f, kind)
        import numpy as np
        e = self.emb.encode([state(f)], normalize_embeddings=True)
        x = np.hstack([e, np.array([_hand(f, kind)])])
        return {"head": float(self.bundle["model"].predict_proba(x)[0, 1])}
