"""
PyTorch 2.6+ defaults torch.load(..., weights_only=True), which breaks pyannote /
PyTorch Lightning checkpoints that pickle callback objects (e.g. EarlyStopping).

Lightning Fabric also passes weights_only=None/True explicitly. We force
weights_only=False for trusted Hugging Face / pyannote checkpoints.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

_applied = False


def _force_full_checkpoint_load(kwargs: dict[str, Any]) -> None:
    if kwargs.get("weights_only") is not False:
        kwargs["weights_only"] = False


def apply_torch_load_compat() -> None:
    global _applied
    if _applied:
        return

    import torch

    _orig: Callable[..., Any] = torch.load

    @functools.wraps(_orig)
    def _patched_torch_load(*args: Any, **kwargs: Any) -> Any:
        _force_full_checkpoint_load(kwargs)
        return _orig(*args, **kwargs)

    torch.load = _patched_torch_load  # type: ignore[assignment]

    try:
        import torch.serialization as ts

        ts.load = _patched_torch_load  # type: ignore[assignment]
    except Exception:
        pass

    try:
        import lightning_fabric.utilities.cloud_io as cloud_io

        _orig_pl: Callable[..., Any] = cloud_io._load

        @functools.wraps(_orig_pl)
        def _patched_pl_load(
            path_or_url: Any,
            map_location: Any = None,
            weights_only: bool | None = None,
        ) -> Any:
            if weights_only is not False:
                weights_only = False
            return _orig_pl(path_or_url, map_location=map_location, weights_only=weights_only)

        cloud_io._load = _patched_pl_load  # type: ignore[assignment]
    except Exception:
        pass

    _applied = True
