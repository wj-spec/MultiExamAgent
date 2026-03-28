"""
待办任务 REST API 路由 (api/todo_api.py)

端点列表：
  GET  /api/todos/session/{session_id}          - 获取会话的所有任务组
  GET  /api/todos/groups/{group_id}             - 获取单个任务组（含所有任务）
  POST /api/todos/groups/{group_id}/confirm     - 用户确认执行（pending → ready）
  POST /api/todos/groups/{group_id}/replan      - 触发重新规划（带用户反馈）
  DELETE /api/todos/groups/{group_id}           - 删除任务组
  GET  /api/todos/tasks/{task_id}               - 获取单个任务
  PATCH /api/todos/tasks/{task_id}              - 更新任务状态（Solver 调用）
  POST /api/todos/tasks/{task_id}/comment       - 添加评论
  GET  /api/todos/tasks/{task_id}/comments      - 获取任务评论列表
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Optional
import os
import tempfile

from models.todo import (
    TodoGroupResponse,
    TodoTaskResponse,
    TodoTaskUpdate,
    CommentCreate,
    CommentResponse,
    ReplanRequest,
)
from services.todo_service import TodoService

router = APIRouter(prefix="/api/todos", tags=["todos"])


# ==================== 任务组端点 ====================

@router.get("/session/{session_id}", response_model=List[TodoGroupResponse])
async def get_session_groups(session_id: str, limit: int = 20):
    """获取会话下的所有任务组"""
    groups = TodoService.get_session_groups(session_id, limit=limit)
    return [TodoGroupResponse.from_dict(g) for g in groups]


@router.get("/groups/{group_id}", response_model=TodoGroupResponse)
async def get_group(group_id: str):
    """获取任务组详情（含所有任务和评论）"""
    group = TodoService.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"任务组 {group_id} 不存在")
    return TodoGroupResponse.from_dict(group)


@router.post("/groups/{group_id}/confirm")
async def confirm_execution(group_id: str):
    """
    用户确认执行：将任务组中所有 pending 任务标记为 ready，
    任务组状态改为 ready。
    """
    group = TodoService.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"任务组 {group_id} 不存在")

    count = TodoService.mark_tasks_ready(group_id)
    return {
        "success": True,
        "message": f"已将 {count} 个任务标记为待执行",
        "group_id": group_id,
        "ready_count": count,
    }


@router.post("/groups/{group_id}/replan")
async def trigger_replan(group_id: str, request: ReplanRequest):
    """
    触发重新规划。
    
    将任务组状态设置为 replanning，并返回反馈给前端。
    实际重新规划由 WebSocket 消息驱动（前端发送 replan 消息到 WS）。
    """
    group = TodoService.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"任务组 {group_id} 不存在")

    TodoService.update_group_status(group_id, "replanning")
    return {
        "success": True,
        "group_id": group_id,
        "status": "replanning",
        "user_feedback": request.user_feedback,
        "message": "已收到重新规划请求，请通过对话框告知 AI 您的修改意见",
    }


@router.delete("/groups/{group_id}")
async def delete_group(group_id: str):
    """删除任务组"""
    success = TodoService.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"任务组 {group_id} 不存在")
    return {"success": True, "message": f"任务组 {group_id} 已删除"}


# ==================== 任务端点 ====================

@router.get("/tasks/{task_id}", response_model=TodoTaskResponse)
async def get_task(task_id: str):
    """获取单个任务详情"""
    task = TodoService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return TodoTaskResponse.from_dict(task)


@router.patch("/tasks/{task_id}", response_model=TodoTaskResponse)
async def update_task(task_id: str, update: TodoTaskUpdate):
    """
    更新任务状态和执行结果（主要由 Solver 通过内部调用，
    或前端手动调用更新状态）
    """
    task = TodoService.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    updated = TodoService.update_task_status(
        task_id=task_id,
        status=update.status or task["status"],
        result=update.result,
        result_data=update.result_data,
        elapsed_ms=update.elapsed_ms,
    )
    return TodoTaskResponse.from_dict(updated)


# ==================== 评论端点 ====================

@router.post("/tasks/{task_id}/comment", response_model=CommentResponse)
async def add_comment(task_id: str, comment: CommentCreate):
    """为任务添加评论（用户反馈 / Agent 注释）"""
    result = TodoService.add_comment(
        task_id=task_id,
        content=comment.content,
        author=comment.author,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return CommentResponse.from_dict(result)


@router.get("/tasks/{task_id}/comments", response_model=List[CommentResponse])
async def get_comments(task_id: str):
    """获取任务的所有评论"""
    comments = TodoService.get_task_comments(task_id)
    return [CommentResponse.from_dict(c) for c in comments]


# ==================== 审题文件上传端点 ====================

ALLOWED_REVIEW_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}
MAX_REVIEW_FILE_MB = 20


@router.post("/review/upload-exam")
async def upload_exam_for_review(file: UploadFile = File(...)):
    """
    审题场景专用文件上传端点。

    接收用户上传的试题/试卷文件（PDF/Word/TXT），
    解析并返回纯文本内容，供前端填充到审题输入框或直接发送给 Planner。

    Returns:
        {
            "filename": "...",
            "file_type": ".pdf",
            "content": "提取的文本内容",
            "char_count": 1234,
            "preview": "前200字...",
        }
    """
    filename = file.filename or "exam_file"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_REVIEW_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 {ext}，请上传 PDF、Word 或文本文件",
        )

    # 读取文件内容（检查大小）
    content_bytes = await file.read()
    size_mb = len(content_bytes) / (1024 * 1024)
    if size_mb > MAX_REVIEW_FILE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{size_mb:.1f}MB），最大支持 {MAX_REVIEW_FILE_MB}MB",
        )

    # 写入临时文件（attachment_tools 需要文件路径）
    suffix = ext
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content_bytes)
        tmp_path = tmp.name

    try:
        from agents.tools.attachment_tools import AnalyzeAttachmentTool
        tool = AnalyzeAttachmentTool()
        result = tool.execute(tmp_path, purpose="提取试题内容以便审核")

        if not result.success:
            raise HTTPException(status_code=422, detail=f"文件解析失败: {result.error}")

        full_text = result.data.get("full_content", "")
        return {
            "filename": filename,
            "file_type": ext,
            "content": full_text,
            "char_count": len(full_text),
            "preview": full_text[:300] + ("..." if len(full_text) > 300 else ""),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务端解析错误: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
