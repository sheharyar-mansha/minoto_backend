"""Closed-set speaker IDENTIFICATION: diarized clusters -> enrolled contacts.

Every meeting member records a voice intro, so a meeting is a *closed set*: each
diarized speaker cluster should correspond to exactly one enrolled contact. We:

  1. Pool each cluster's cleanest speech (up to ~18s) and **re-embed it with the
     same pyannote/embedding model used at enrollment** (512-dim).

     CRITICAL INVARIANT: never reuse diarization's internal embeddings — pyannote
     3.1 diarizes with wespeaker (256-dim), which is **not** comparable to the
     enrollment vectors. A runtime assert + unit test guard the 512-dim contract.

  2. Build a cluster x contact cosine matrix and solve a 1:1 assignment with the
     Hungarian algorithm (``scipy.optimize.linear_sum_assignment``).

  3. Accept a pair only when the cosine clears ``SPEAKER_MATCH_MIN_SCORE`` *and*
     beats the cluster's second-best contact by ``SPEAKER_MATCH_MIN_MARGIN``;
     otherwise the cluster is left ``unknown``. Top-2 candidate contact ids are
     always recorded.

The pure matching math (``cosine`` / ``match_clusters``) takes plain vectors so it
is unit-testable without audio or models; ``build_cluster_vectors`` is the only
part that touches the embedding backend.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy.optimize import linear_sum_assignment

from config.settings import settings
from pipeline.audio_io import slice_audio
from pipeline.speaker.backends import EMBEDDING_DIM, normalize_embedding_vector

log = logging.getLogger(__name__)

__all__ = ["cosine", "match_clusters", "build_cluster_vectors"]

# Cap on how much of a cluster's speech we pool before embedding.
_MAX_POOL_SECONDS = 18.0


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors; 0.0 if either is empty/zero."""
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def build_cluster_vectors(
    audio: np.ndarray,
    sr: int,
    turns: list[dict],
    backend,
    *,
    min_segment_sec: float | None = None,
    max_pool_seconds: float = _MAX_POOL_SECONDS,
) -> dict[str, np.ndarray]:
    """Pool each cluster's cleanest non-overlapping speech and embed it (512-dim).

    Args:
        audio: decoded mono/16k waveform for the whole recording.
        sr: sample rate.
        turns: diarized turns ``[{start, end, speaker_label, is_overlap?}]``.
        backend: a ``PyannoteEmbeddingBackend`` (pyannote/embedding, 512-dim).

    Returns:
        ``{speaker_label: 512-dim unit-ish vector}`` for clusters we could embed.
    """
    if min_segment_sec is None:
        min_segment_sec = settings.SPEAKER_MATCH_MIN_SEGMENT_SEC

    # Group turns per cluster, preferring non-overlapping, longest-first spans.
    by_label: dict[str, list[dict]] = {}
    for t in turns:
        if t.get("is_overlap"):
            continue  # overlapped speech muddies the embedding
        dur = float(t["end"]) - float(t["start"])
        if dur < min_segment_sec:
            continue
        by_label.setdefault(str(t["speaker_label"]), []).append(t)

    vectors: dict[str, np.ndarray] = {}
    for label, cluster_turns in by_label.items():
        cluster_turns.sort(key=lambda x: (x["end"] - x["start"]), reverse=True)

        pooled: list[np.ndarray] = []
        pooled_sec = 0.0
        for t in cluster_turns:
            if pooled_sec >= max_pool_seconds:
                break
            chunk = slice_audio(audio, sr, float(t["start"]), float(t["end"]))
            if chunk.size == 0:
                continue
            pooled.append(chunk)
            pooled_sec += chunk.size / sr

        if not pooled:
            continue
        waveform = np.concatenate(pooled)
        vec = backend.embed_waveform(waveform, sr)
        vec = normalize_embedding_vector(vec)
        if vec is None:
            continue

        # CRITICAL INVARIANT: enrollment & cluster vectors must both be 512-dim.
        assert vec.shape[0] == EMBEDDING_DIM, (
            f"cluster '{label}' embedding has dim {vec.shape[0]}, expected {EMBEDDING_DIM}; "
            "diarization's internal (256-dim) embeddings must never be used here."
        )
        vectors[label] = vec

    log.info("Built %d cluster embedding(s).", len(vectors))
    return vectors


def match_clusters(
    cluster_vectors: dict[str, np.ndarray],
    contact_vectors: dict[str, np.ndarray],
    *,
    min_score: float | None = None,
    min_margin: float | None = None,
) -> dict[str, dict]:
    """Assign clusters to contacts 1:1 with thresholded Hungarian matching.

    Pure function: pass vectors, get decisions. No audio, no models.

    Returns ``{cluster_label: {contact_id|None, score, status, candidates}}`` where
    ``status`` is ``'matched'`` or ``'unknown'`` and ``candidates`` is the top-2
    contact ids by cosine (best first).
    """
    if min_score is None:
        min_score = settings.SPEAKER_MATCH_MIN_SCORE
    if min_margin is None:
        min_margin = settings.SPEAKER_MATCH_MIN_MARGIN

    labels = list(cluster_vectors.keys())
    contact_ids = list(contact_vectors.keys())
    result: dict[str, dict] = {}
    if not labels:
        return result

    # Per-cluster contact similarities, sorted best-first.
    sims: dict[str, list[tuple[str, float]]] = {}
    for lab in labels:
        cv = cluster_vectors[lab]
        scored = sorted(
            ((cid, cosine(cv, contact_vectors[cid])) for cid in contact_ids),
            key=lambda x: x[1],
            reverse=True,
        )
        sims[lab] = scored
        result[lab] = {
            "contact_id": None,
            "score": (scored[0][1] if scored else None),
            "status": "unknown",
            "candidates": [cid for cid, _ in scored[:2]],
        }

    if not contact_ids:
        return result

    # Hungarian assignment on cost = -cosine (maximise total similarity).
    cost = np.zeros((len(labels), len(contact_ids)), dtype=np.float64)
    for i, lab in enumerate(labels):
        row = dict(sims[lab])
        for j, cid in enumerate(contact_ids):
            cost[i, j] = -row[cid]

    rows, cols = linear_sum_assignment(cost)
    for i, j in zip(rows, cols):
        lab = labels[i]
        scored = sims[lab]
        best_id, best_score = scored[0]
        # Single enrolled contact => no runner-up, so the margin test is vacuous and
        # only min_score gates acceptance. Intended, not a bug.
        second_score = scored[1][1] if len(scored) > 1 else -1.0
        assigned_id = contact_ids[j]
        assigned_score = dict(scored)[assigned_id]
        # match_score keeps reporting the cluster's BEST cosine (== candidates[0], set
        # when result[lab] was initialised); we don't overwrite it with the
        # Hungarian-assigned contact's score, which can differ on a rejected cluster.

        margin = best_score - second_score
        # Accept only the cluster's own best contact, and only when both the
        # absolute score and the lead over the runner-up are convincing.
        if (
            assigned_id == best_id
            and assigned_score >= min_score
            and margin >= min_margin
        ):
            result[lab]["contact_id"] = assigned_id
            result[lab]["status"] = "matched"

    return result
