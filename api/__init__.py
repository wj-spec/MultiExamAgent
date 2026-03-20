"""
API 模块

包含各种 REST API 和 WebSocket 端点。
"""

from api.mode_api import router as mode_router

__all__ = ["mode_router"]
