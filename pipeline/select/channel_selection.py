from __future__ import annotations

from collections import defaultdict

from pipeline.types import SelectedRegion, SpeechRegion


def select_best_channels(
    regions: list[SpeechRegion],
    overlap_merge_sec: float = 0.25,
) -> list[SelectedRegion]:
    """
    For overlapping speech across channels, pick the channel with highest energy
    (near-field proxy). Structural dedup: one region -> one channel.
    """
    if not regions:
        return []
    sorted_regions = sorted(regions, key=lambda r: (r.start_sec, -r.energy))
    timeline: list[SelectedRegion] = []

    buckets: dict[int, list[SpeechRegion]] = defaultdict(list)
    for r in sorted_regions:
        key = int(r.start_sec / overlap_merge_sec)
        buckets[key].append(r)
        buckets[key - 1].append(r)
        buckets[key + 1].append(r)

    used_spans: list[tuple[float, float, str]] = []
    for r in sorted_regions:
        overlaps = False
        for s0, s1, cid in used_spans:
            if cid == r.channel_id:
                continue
            if r.start_sec < s1 and r.end_sec > s0:
                if r.energy <= max(x.energy for x in regions if x.channel_id != r.channel_id):
                    overlaps = True
                    break
        if overlaps:
            continue
        # Compare competing channels in same window
        competitors = [
            x
            for x in regions
            if x.start_sec < r.end_sec + overlap_merge_sec
            and x.end_sec > r.start_sec - overlap_merge_sec
        ]
        best = max(competitors, key=lambda x: x.energy)
        if best.channel_id != r.channel_id:
            continue
        span = (r.start_sec, r.end_sec, r.channel_id)
        if any(abs(r.start_sec - s0) < 0.05 and r.channel_id == cid for s0, _, cid in used_spans):
            continue
        used_spans.append(span)
        timeline.append(
            SelectedRegion(
                channel_id=best.channel_id,
                uploader_user_id=best.uploader_user_id,
                start_sec=r.start_sec,
                end_sec=r.end_sec,
                score=best.energy,
            )
        )

    return sorted(timeline, key=lambda x: x.start_sec)
