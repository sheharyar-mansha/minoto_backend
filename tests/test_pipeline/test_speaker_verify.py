from __future__ import annotations

import numpy as np

from pipeline.speaker.verify import SpeakerRef, verify_speaker


def test_normalize_pools_flattened_sliding_embeddings():
    from pipeline.speaker.backends import normalize_embedding_vector

    flat = np.arange(512 * 36, dtype=np.float32)
    pooled = normalize_embedding_vector(flat)
    assert pooled is not None
    assert pooled.shape == (512,)


def test_device_prior_prefers_uploader_at_borderline():
    uploader = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    other = np.array([0.9, 0.1, 0.0], dtype=np.float32)
    seg = np.array([0.95, 0.05, 0.0], dtype=np.float32)
    refs = [
        SpeakerRef(user_id="alice", full_name="Alice", embedding=other),
        SpeakerRef(user_id="bob", full_name="Bob", embedding=uploader),
    ]
    speaker_id, score, status = verify_speaker(refs, seg, uploader_user_id="bob")
    assert speaker_id == "bob"
    assert status == "matched"
    assert score > 0
