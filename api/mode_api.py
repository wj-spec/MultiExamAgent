"""
模式切换 API

提供对话模式切换的 REST API 和 WebSocket 端点。
支持：
1. 手动模式切换
2. 自动模式切换确认
3. WebSocket 实时状态同步
"""

import logging
from typing import Dict, Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mode", tags=["模式切换"])


# ==================== 数据模型 ====================

class ModeSwitchRequest(BaseModel):
    """模式切换请求"""
    session_id: str
    mode: str  # chat, proposition, grading
    auto: bool = False  # 是否为自动切换


class ModeSwitchResponse(BaseModel):
    """模式切换响应"""
    success: bool
    mode: str
    transition: str  # enter, exit, none, switch
    requires_confirmation: bool = False
    message: str = ""


class ModeStatusResponse(BaseModel):
    """模式状态响应"""
    session_id: str
    current_mode: str
    auto_switch_enabled: bool
    mode_history: List[Dict]


# ==================== 连接管理器 ====================

class ModeConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """建立连接"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"[ModeAPI] WebSocket 连接建立: {session_id}")

    def disconnect(self, session_id: str):
        """断开连接"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"[ModeAPI] WebSocket 连接断开: {session_id}")

    async def send_mode_update(self, session_id: str, mode_data: dict):
        """发送模式更新"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(mode_data)
            except Exception as e:
                logger.error(f"[ModeAPI] 发送更新失败: {e}")

    async def broadcast(self, message: dict):
        """广播消息"""
        for session_id in self.active_connections:
            await self.send_mode_update(session_id, message)


manager = ModeConnectionManager()


# ==================== 会话模式状态管理 ====================

class SessionModeManager:
    """会话模式状态管理器"""

    def __init__(self):
        self._sessions: Dict[str, Dict] = {}

    def get_or_create(self, session_id: str) -> Dict:
        """获取或创建会话状态"""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "current_mode": "chat",
                "auto_switch_enabled": True,
                "mode_history": []
            }
        return self._sessions[session_id]

    def set_mode(self, session_id: str, mode: str) -> str:
        """
        设置模式

        Returns:
            切换类型: enter, exit, switch, none
        """
        session = self.get_or_create(session_id)
        old_mode = session["current_mode"]

        if old_mode == mode:
            return "none"

        # 记录历史
        session["mode_history"].append({
            "from": old_mode,
            "to": mode,
            "timestamp": self._get_timestamp()
        })

        # 更新模式
        session["current_mode"] = mode

        # 判断切换类型
        if old_mode == "chat":
            return "enter"
        elif mode == "chat":
            return "exit"
        else:
            return "switch"

    def get_mode(self, session_id: str) -> str:
        """获取当前模式"""
        session = self.get_or_create(session_id)
        return session["current_mode"]

    def set_auto_switch(self, session_id: str, enabled: bool):
        """设置自动切换开关"""
        session = self.get_or_create(session_id)
        session["auto_switch_enabled"] = enabled

    def get_auto_switch(self, session_id: str) -> bool:
        """获取自动切换开关状态"""
        session = self.get_or_create(session_id)
        return session["auto_switch_enabled"]

    def get_status(self, session_id: str) -> Dict:
        """获取完整状态"""
        return self.get_or_create(session_id)

    def _get_timestamp(self) -> str:
        """获取时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()


session_manager = SessionModeManager()


# ==================== REST API 端点 ====================

@router.post("/switch", response_model=ModeSwitchResponse)
async def switch_mode(request: ModeSwitchRequest):
    """
    切换对话模式

    Args:
        request: 模式切换请求

    Returns:
        模式切换结果
    """
    # 验证模式有效性
    valid_modes = ["chat", "proposition", "grading"]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"无效的模式: {request.mode}，有效模式: {valid_modes}"
        )

    # 如果是自动切换，检查是否开启
    if request.auto:
        auto_enabled = session_manager.get_auto_switch(request.session_id)
        if not auto_enabled:
            return ModeSwitchResponse(
                success=False,
                mode=session_manager.get_mode(request.session_id),
                transition="none",
                requires_confirmation=False,
                message="自动切换已禁用"
            )

    # 执行模式切换
    transition = session_manager.set_mode(request.session_id, request.mode)

    # 广播更新
    await manager.send_mode_update(request.session_id, {
        "type": "mode_update",
        "session_id": request.session_id,
        "mode": request.mode,
        "transition": transition,
        "auto": request.auto
    })

    # 生成消息
    messages = {
        "enter": f"已进入{request.mode}模式",
        "exit": "已退出专业模式，返回基础对话",
        "switch": f"已切换到{request.mode}模式",
        "none": "模式未改变"
    }

    return ModeSwitchResponse(
        success=True,
        mode=request.mode,
        transition=transition,
        requires_confirmation=False,
        message=messages.get(transition, "")
    )


@router.get("/status/{session_id}", response_model=ModeStatusResponse)
async def get_mode_status(session_id: str):
    """
    获取模式状态

    Args:
        session_id: 会话ID

    Returns:
        模式状态
    """
    status = session_manager.get_status(session_id)

    return ModeStatusResponse(
        session_id=session_id,
        current_mode=status["current_mode"],
        auto_switch_enabled=status["auto_switch_enabled"],
        mode_history=status["mode_history"][-10:]  # 最近10次
    )


@router.post("/auto-toggle/{session_id}")
async def set_auto_toggle(session_id: str, enabled: bool):
    """
    设置自动切换开关

    Args:
        session_id: 会话ID
        enabled: 是否启用

    Returns:
        操作结果
    """
    session_manager.set_auto_switch(session_id, enabled)

    return {
        "success": True,
        "session_id": session_id,
        "auto_switch_enabled": enabled
    }


@router.post("/confirm/{session_id}")
async def confirm_mode_switch(session_id: str, confirmed: bool):
    """
    确认模式切换

    当自动检测到需要切换时，前端弹窗确认后调用此接口。

    Args:
        session_id: 会话ID
        confirmed: 是否确认切换

    Returns:
        操作结果
    """
    if not confirmed:
        return {
            "success": True,
            "message": "用户取消切换",
            "mode": session_manager.get_mode(session_id)
        }

    # 获取建议的模式（从前端传入或从状态中获取）
    # 这里简化处理，实际可能需要存储建议的模式
    return {
        "success": True,
        "message": "切换已确认",
        "mode": session_manager.get_mode(session_id)
    }


# ==================== WebSocket 端点 ====================

@router.websocket("/ws/{session_id}")
async def mode_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket 连接 - 实时模式状态同步

    支持的消息类型：
    - mode_update: 模式更新通知
    - mode_switch_request: 前端请求切换模式
    - mode_confirm: 前端确认切换
    - ping/pong: 心跳
    """
    await manager.connect(session_id, websocket)

    try:
        # 发送初始状态
        status = session_manager.get_status(session_id)
        await websocket.send_json({
            "type": "init",
            "data": status
        })

        while True:
            # 接收消息
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "mode_switch_request":
                # 处理前端请求切换
                new_mode = data.get("mode")
                if new_mode:
                    transition = session_manager.set_mode(session_id, new_mode)
                    await websocket.send_json({
                        "type": "mode_update",
                        "mode": new_mode,
                        "transition": transition
                    })

            elif msg_type == "mode_confirm":
                # 处理确认切换
                confirmed = data.get("confirmed", False)
                if confirmed:
                    suggested_mode = data.get("suggested_mode", "proposition")
                    transition = session_manager.set_mode(
                        session_id, suggested_mode)
                    await websocket.send_json({
                        "type": "mode_update",
                        "mode": suggested_mode,
                        "transition": transition
                    })
                else:
                    await websocket.send_json({
                        "type": "mode_cancelled",
                        "message": "用户取消切换"
                    })

    except WebSocketDisconnect:
        manager.disconnect(session_id)

    except Exception as e:
        logger.error(f"[ModeAPI] WebSocket 错误: {e}")
        manager.disconnect(session_id)


# ==================== 辅助函数 ====================

def get_mode_manager() -> SessionModeManager:
    """获取模式管理器实例"""
    return session_manager


def get_connection_manager() -> ModeConnectionManager:
    """获取连接管理器实例"""
    return manager
