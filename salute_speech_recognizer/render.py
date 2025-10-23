from __future__ import annotations
from typing import Any, Dict

# Thin wrapper around existing implementation to stabilize public API
from .grpc_async import _build_markdown_from_json as _impl_md


def build_markdown_from_json(data: Dict[str, Any]) -> str:
    """Render normalized JSON into Markdown with deduplication."""
    return _impl_md(data)
