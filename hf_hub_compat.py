"""
Pyannote (and older HF code) calls hf_hub_download(..., use_auth_token=...).
huggingface_hub 1.x only accepts `token`. Map the old kwarg before pyannote loads models.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

_applied = False


def apply_hf_hub_use_auth_token_compat() -> None:
    global _applied
    if _applied:
        return

    import huggingface_hub as hf
    import huggingface_hub.file_download as fd

    _orig: Callable[..., Any] = fd.hf_hub_download

    @functools.wraps(_orig)
    def _patched(*args: Any, **kwargs: Any) -> Any:
        if "use_auth_token" in kwargs:
            uat = kwargs.pop("use_auth_token")
            if kwargs.get("token", None) is None and uat is not None:
                kwargs["token"] = uat
        return _orig(*args, **kwargs)

    fd.hf_hub_download = _patched
    hf.hf_hub_download = _patched

    _applied = True
