"""Pure-logic tests for cluster->contact matching (no audio, no models)."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.match import build_cluster_vectors, cosine, match_clusters
from pipeline.speaker.backends import EMBEDDING_DIM


def _vec(*vals) -> np.ndarray:
    return np.asarray(vals, dtype=np.float32)


def test_cosine_basic():
    assert cosine(_vec(1, 0), _vec(1, 0)) == 1.0
    assert cosine(_vec(1, 0), _vec(0, 1)) == 0.0
    assert cosine(_vec(1, 0), _vec(-1, 0)) == -1.0


def test_cosine_handles_zero_and_mismatch():
    assert cosine(_vec(0, 0), _vec(1, 1)) == 0.0
    assert cosine(_vec(1, 0, 0), _vec(1, 0)) == 0.0  # length mismatch


def test_hungarian_one_to_one_assignment():
    # Two clusters, two contacts, each cluster clearly closest to one contact.
    clusters = {"S0": _vec(1.0, 0.0), "S1": _vec(0.0, 1.0)}
    contacts = {"alice": _vec(1.0, 0.05), "bob": _vec(0.05, 1.0)}
    res = match_clusters(clusters, contacts, min_score=0.3, min_margin=0.05)

    assert res["S0"]["contact_id"] == "alice"
    assert res["S0"]["status"] == "matched"
    assert res["S1"]["contact_id"] == "bob"
    assert res["S1"]["status"] == "matched"
    # A cluster is never assigned to two contacts; the two picks are distinct.
    assert res["S0"]["contact_id"] != res["S1"]["contact_id"]


def test_below_min_score_is_unknown():
    clusters = {"S0": _vec(1.0, 0.0)}
    # Orthogonal-ish -> cosine ~0.1, below threshold.
    contacts = {"alice": _vec(0.1, 1.0)}
    res = match_clusters(clusters, contacts, min_score=0.35, min_margin=0.05)
    assert res["S0"]["status"] == "unknown"
    assert res["S0"]["contact_id"] is None


def test_margin_rejection_is_unknown():
    # Cluster is equally similar to both contacts -> margin too small.
    clusters = {"S0": _vec(1.0, 1.0)}
    contacts = {"alice": _vec(1.0, 1.0), "bob": _vec(1.0, 1.0)}
    res = match_clusters(clusters, contacts, min_score=0.3, min_margin=0.05)
    assert res["S0"]["status"] == "unknown"
    assert res["S0"]["contact_id"] is None


def test_top_two_candidates_recorded():
    clusters = {"S0": _vec(1.0, 0.0, 0.0)}
    contacts = {
        "alice": _vec(0.9, 0.1, 0.0),
        "bob": _vec(0.5, 0.5, 0.0),
        "carol": _vec(0.0, 0.0, 1.0),
    }
    res = match_clusters(clusters, contacts, min_score=0.3, min_margin=0.05)
    assert res["S0"]["candidates"] == ["alice", "bob"]  # top-2 by cosine, best first


def test_more_contacts_than_clusters_ok():
    clusters = {"S0": _vec(1.0, 0.0)}
    contacts = {"alice": _vec(1.0, 0.0), "bob": _vec(0.0, 1.0), "carol": _vec(-1.0, 0.0)}
    res = match_clusters(clusters, contacts, min_score=0.3, min_margin=0.05)
    assert set(res.keys()) == {"S0"}
    assert res["S0"]["contact_id"] == "alice"


class _FakeBackend:
    """Stand-in embedding backend returning a fixed-dim vector (no models)."""

    def __init__(self, dim: int):
        self.dim = dim

    def embed_waveform(self, waveform, sr):  # noqa: D401, ANN001
        return np.ones(self.dim, dtype=np.float32)


def test_cluster_vectors_are_512_dim():
    sr = 16000
    audio = np.ones(sr * 20, dtype=np.float32)  # 20s of (fake) audio
    turns = [{"start": 0.0, "end": 10.0, "speaker_label": "S0", "is_overlap": False}]
    vecs = build_cluster_vectors(audio, sr, turns, _FakeBackend(EMBEDDING_DIM), min_segment_sec=0.8)
    assert set(vecs.keys()) == {"S0"}
    assert vecs["S0"].shape[0] == EMBEDDING_DIM == 512


def test_wrong_dim_cluster_vector_trips_invariant():
    sr = 16000
    audio = np.ones(sr * 20, dtype=np.float32)
    turns = [{"start": 0.0, "end": 10.0, "speaker_label": "S0", "is_overlap": False}]
    # 256-dim (wespeaker) must never be accepted as a cluster vector.
    with pytest.raises(AssertionError):
        build_cluster_vectors(audio, sr, turns, _FakeBackend(256), min_segment_sec=0.8)


def test_no_contacts_all_unknown():
    clusters = {"S0": _vec(1.0, 0.0), "S1": _vec(0.0, 1.0)}
    res = match_clusters(clusters, {}, min_score=0.3, min_margin=0.05)
    assert res["S0"]["status"] == "unknown"
    assert res["S1"]["status"] == "unknown"
    assert res["S0"]["candidates"] == []
