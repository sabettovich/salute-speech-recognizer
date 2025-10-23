from __future__ import annotations
from typing import Any, Optional, List, Dict

# Delegate to existing implementation to avoid code duplication for v1.0
from .grpc_async import _normalize_grpc_result as _impl_normalize


def normalize_grpc_result(data: Dict[str, Any], hints: Optional[List[str]] = None) -> Dict[str, Any]:
    """Normalize gRPC JSON into flat segments; select best hypothesis by hints coverage.

    Thin wrapper over grpc_async._normalize_grpc_result to stabilize API.
    """
    return _impl_normalize(data, hints=hints)
