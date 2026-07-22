"""KNN trigger classifier + Leave-One-Out cross-validation evaluator.
Ported 1:1 from the old Smart Staff project's `motion_model.js`
(`MotionModel.Classifier` / `MotionModel.Evaluator`): k=3, Euclidean
distance, Z-score normalization (population mean/std across the whole
training set), weighted voting (weight = 1/max(d^2, eps)). See
docs/agent/DONE.md for the full port rationale.

Pure, no I/O — callers own loading sessions and persisting the trained
model (see trigger_sessions.py / app.py's /api/triggers/train).
"""
from __future__ import annotations
import math
from motion_features import extract

K = 3
EPS = 1e-9


def _compute_norm(vectors: list[list[float]]) -> dict:
    n = len(vectors)
    size = len(vectors[0])
    means = [0.0] * size
    stds = [0.0] * size
    for i in range(size):
        s = sum(v[i] for v in vectors)
        means[i] = s / n
    for i in range(size):
        var_sum = sum((v[i] - means[i]) ** 2 for v in vectors)
        stds[i] = math.sqrt(var_sum / n)
    return {'means': means, 'stds': stds}


def _normalize(vec: list[float], norm_params: dict) -> list[float]:
    means, stds = norm_params['means'], norm_params['stds']
    return [(v - means[i]) / stds[i] if stds[i] > EPS else 0.0 for i, v in enumerate(vec)]


def _dist(v1: list[float], v2: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(v1, v2)))


def _weighted_vote(neighbors: list[dict]) -> tuple[str | None, float]:
    """neighbors: [{'label', 'dist'}, ...] (already sorted, top-k only).
    Returns (winning_label, confidence) where confidence is the winner's
    vote-share of total weighted votes across the k neighbors (not
    "fraction of k that agree")."""
    votes: dict[str, float] = {}
    total = 0.0
    for n in neighbors:
        w = 1.0 / max(n['dist'] ** 2, EPS)
        votes[n['label']] = votes.get(n['label'], 0.0) + w
        total += w
    best_label, best_w = None, 0.0
    for label, w in votes.items():
        if w > best_w:
            best_w, best_label = w, label
    confidence = best_w / total if total > 0 else 0.0
    return best_label, confidence


class Classifier:
    def __init__(self):
        self.norm_params: dict | None = None
        self.training_data: list[dict] = []  # [{'label', 'vector'}]

    def train(self, sessions: list[dict]) -> bool:
        """sessions: [{'label': str, 'frames': [...]}]"""
        if not sessions:
            return False
        raw = [{'label': s['label'], 'vector': extract(s['frames'])} for s in sessions]
        self.norm_params = _compute_norm([r['vector'] for r in raw])
        self.training_data = [{'label': r['label'], 'vector': _normalize(r['vector'], self.norm_params)} for r in raw]
        return True

    def predict(self, frames: list[dict]) -> dict:
        """Returns {'label': str|None, 'confidence': float, 'kNearest': [...]}."""
        if not self.training_data or not self.norm_params:
            return {'label': None, 'confidence': 0.0, 'kNearest': []}
        query = _normalize(extract(frames), self.norm_params)
        dists = sorted(
            ({'label': td['label'], 'dist': _dist(query, td['vector'])} for td in self.training_data),
            key=lambda d: d['dist'],
        )
        k_nearest = dists[:K]
        label, confidence = _weighted_vote(k_nearest)
        return {'label': label, 'confidence': confidence, 'kNearest': k_nearest}


def _predict_one(train_sessions: list[dict], test_frames: list[dict]) -> str | None:
    """One fold of LOO-CV: fresh independent normalization on train_sessions
    only (no leakage from the held-out sample), then the same weighted-KNN
    vote as Classifier.predict, returning just the winning label."""
    raw = [{'label': s['label'], 'vector': extract(s['frames'])} for s in train_sessions]
    norm_params = _compute_norm([r['vector'] for r in raw])
    training_data = [{'label': r['label'], 'vector': _normalize(r['vector'], norm_params)} for r in raw]
    query = _normalize(extract(test_frames), norm_params)
    dists = sorted(
        ({'label': td['label'], 'dist': _dist(query, td['vector'])} for td in training_data),
        key=lambda d: d['dist'],
    )
    label, _ = _weighted_vote(dists[:K])
    return label


def _f1_scores(matrix: dict) -> dict:
    """matrix[actual][predicted] = count. Returns per-class {precision, recall, f1, tp, fp, fn}."""
    classes = set(matrix.keys())
    for preds in matrix.values():
        classes.update(preds.keys())
    out = {}
    for cls in classes:
        tp = fp = fn = 0
        for actual, preds in matrix.items():
            for pred, count in preds.items():
                if actual == cls and pred == cls:
                    tp += count
                elif actual != cls and pred == cls:
                    fp += count
                elif actual == cls and pred != cls:
                    fn += count
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        out[cls] = {'precision': precision, 'recall': recall, 'f1': f1, 'tp': tp, 'fp': fp, 'fn': fn}
    return out


class Evaluator:
    @staticmethod
    def cross_validate(sessions: list[dict]) -> dict:
        """Leave-One-Out CV. sessions: [{'label', 'frames'}].
        Returns {'accuracy', 'matrix', 'perClass'}."""
        if not sessions or len(sessions) < 3:
            return {'accuracy': 0.0, 'matrix': {}, 'perClass': {}}
        correct = 0
        matrix: dict[str, dict[str, int]] = {}
        for i, test in enumerate(sessions):
            train = [s for j, s in enumerate(sessions) if j != i]
            predicted = _predict_one(train, test['frames'])
            actual = test['label']
            matrix.setdefault(actual, {})
            matrix[actual][predicted] = matrix[actual].get(predicted, 0) + 1
            if predicted == actual:
                correct += 1
        accuracy = correct / len(sessions)
        per_class = _f1_scores(matrix)
        return {'accuracy': accuracy, 'matrix': matrix, 'perClass': per_class}
