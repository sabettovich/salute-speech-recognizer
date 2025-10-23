from __future__ import annotations
from typing import Dict, Any

# Thin wrappers around existing implementations to stabilize public API
from .grpc_async import _apply_speaker_mapping as _impl_apply
from .grpc_async import _load_speaker_map as _impl_load


def apply_speaker_mapping(norm: Dict[str, Any], phrase_map: Dict[str, str]) -> Dict[str, Any]:
    return _impl_apply(norm, phrase_map)


def load_speaker_map(path: str) -> Dict[str, str]:
    return _impl_load(path)
