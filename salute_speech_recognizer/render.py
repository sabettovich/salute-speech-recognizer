from __future__ import annotations
from typing import Any, Dict, List
import copy

# Thin wrapper around existing implementation to stabilize public API
from .grpc_async import _build_markdown_from_json as _impl_md


def build_markdown_from_json(data: Dict[str, Any]) -> str:
    """Render normalized JSON into Markdown with deduplication.
    If segments have '_duplicate_of' (soft dedup), annotate text accordingly.
    """
    try:
        d = copy.deepcopy(data)
        segs: List[Dict[str, Any]] = list(d.get("segments") or [])
        for s in segs:
            if isinstance(s, dict) and s.get("_duplicate_of") and s.get("text"):
                s["text"] = f"(возможный дубль) {s['text']}"
        d["segments"] = segs
        return _impl_md(d)
    except Exception:
        return _impl_md(data)
