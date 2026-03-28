"""
待办任务数据模型 (Pydantic v2)

用于 REST API 请求/响应的验证与序列化。
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
import uuid


# ==================== 基础模型 ====================

class CommentCreate(BaseModel):
    """创建评论请求"""
    content: str = Field(..., min_length=1, description="评论内容")
    author: Literal["user", "agent"] = Field("user", description="评论来源")


class CommentResponse(BaseModel):
    """评论响应"""
    id: str
    author: Literal["user", "agent"]
    content: str
    created_at: str

    @classmethod
    def from_dict(cls, d: dict) -> "CommentResponse":
        return cls(**d)


# ==================== 待办任务模型 ====================

class TodoTaskCreate(BaseModel):
    """创建任务请求（通常由 Planner 调用）"""
    title: str = Field(..., description="任务标题")
    description: str = Field("", description="任务详细说明")
    task_type: str = Field("general", description="任务类型")
    dependencies: List[str] = Field(default_factory=list, description="依赖任务 ID")
    order: int = Field(0, description="显示顺序")


class TodoTaskUpdate(BaseModel):
    """更新任务状态请求"""
    status: Optional[Literal[
        "pending", "ready", "running", "done", "need_revision", "skipped"
    ]] = None
    result: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    elapsed_ms: Optional[int] = None


class TodoTaskResponse(BaseModel):
    """任务响应"""
    id: str
    task_group_id: str
    title: str
    description: str
    task_type: str
    status: str
    dependencies: List[str]
    comments: List[CommentResponse]
    result: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str
    elapsed_ms: Optional[int] = None
    order: int

    @classmethod
    def from_dict(cls, d: dict) -> "TodoTaskResponse":
        d = dict(d)
        d["comments"] = [CommentResponse.from_dict(c) for c in d.get("comments", [])]
        return cls(**d)


# ==================== 任务组模型 ====================

class TodoGroupCreate(BaseModel):
    """创建任务组请求（Planner 规划完成后调用）"""
    session_id: str
    scene: Literal["proposition", "review"]
    title: str
    tasks: List[TodoTaskCreate] = Field(default_factory=list)
    planner_summary: str = Field("", description="Planner 的规划说明")


class TodoGroupResponse(BaseModel):
    """任务组响应"""
    id: str
    session_id: str
    scene: str
    title: str
    status: str
    tasks: List[TodoTaskResponse]
    planner_summary: str
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, d: dict) -> "TodoGroupResponse":
        d = dict(d)
        d["tasks"] = [TodoTaskResponse.from_dict(t) for t in d.get("tasks", [])]
        return cls(**d)


class ReplanRequest(BaseModel):
    """重新规划请求（用户评论后触发）"""
    user_feedback: str = Field(..., description="用户对当前规划的反馈或修改意见")
