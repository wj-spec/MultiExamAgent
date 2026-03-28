"""
IntelliExam-Agent FastAPI 服务

替换 Chainlit，提供：
- 静态文件服务（frontend/ 目录）
- WebSocket /ws/{session_id}：实时 Agent 执行状态推送
- REST API：对话管理、文件上传、记忆库查询
"""

from api.mode_api import router as mode_router
from api.todo_api import router as todo_router
from tools.retriever import get_retriever, VECTOR_STORE_AVAILABLE
from agents.executor_agent import format_questions_response
from utils.memory_manager import get_memory_manager
from utils.conversation_manager import get_conversation_manager
from graphs.workflow_server import run_workflow_async_server
from graphs.state import create_initial_state
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ==================== 应用初始化 ====================

app = FastAPI(
    title="IntelliExam-Agent API",
    description="AI 智能命题系统后端服务",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存会话存储 {session_id -> session_data}
sessions: Dict[str, Dict[str, Any]] = {}


# ==================== WebSocket 端点 ====================

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 实时通信端点

    消息协议（v3.0）：
      客户端→服务端: {"type": "message", "content": "...", "conversation_id": "...", "scene": "chat|proposition|review"}
                     {"type": "ping"}
                     {"type": "switch_conversation", "conversation_id": "..."}
                     {"type": "switch_scene", "scene": "chat|proposition|review"}
                     {"type": "todo_confirm", "group_id": "..."}
                     {"type": "todo_replan", "group_id": "...", "feedback": "..."}

      服务端→客户端: {"type": "connected", "session_id": "...", "conversation_id": "..."}
                     {"type": "agent_step", "step": "...", "status": "running|done|error", ...}
                     {"type": "agent_params", "params": {...}}
                     {"type": "response", "content": "..."}
                     {"type": "result", "markdown": "...", ...}
                     {"type": "error", "message": "..."}
                     {"type": "pong"}
                     {"type": "scene_switched", "scene": "..."}
                     --- v3.0 待办事件 ---
                     {"type": "todo_group_created", "group": {...}}         — Planner 生成任务组
                     {"type": "todo_task_update", "task": {...}}             — 任务状态变更
                     {"type": "todo_task_result", "task_id": "...", "result": "..."}  — 任务完成
                     {"type": "todo_comment_added", "task_id": "...", "comment": {...}} — 新评论
    """
    await websocket.accept()

    conv_manager = get_conversation_manager()

    # 新建初始对话
    conversation = conv_manager.create_conversation()
    conv_id = conversation["id"]
    sess_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    state = create_initial_state("", sess_time)

    sessions[session_id] = {
        "state": state,
        "chat_history": [],
        "conversation_id": conv_id,
    }

    # 通知连接成功
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "conversation_id": conv_id
    })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            # ---- 心跳 ----
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            # ---- 切换/重置会话 ----
            if msg_type == "switch_conversation":
                new_conv_id = data.get("conversation_id", "")
                if new_conv_id:
                    # 加载历史对话
                    conv_data = conv_manager.load_conversation(new_conv_id)
                    if conv_data:
                        msgs = conv_data.get("messages", [])
                        history = [
                            {"role": m["role"], "content": m["content"]} for m in msgs]
                        sess_time2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                        sessions[session_id] = {
                            "state": create_initial_state("", sess_time2),
                            "chat_history": history,
                            "conversation_id": new_conv_id,
                        }
                        await websocket.send_json({
                            "type": "conversation_loaded",
                            "conversation_id": new_conv_id,
                            "messages": [
                                {"role": m["role"], "content": m["content"]}
                                for m in msgs
                            ]
                        })
                    continue
                else:
                    # 新建对话
                    new_conv = conv_manager.create_conversation()
                    new_conv_id = new_conv["id"]
                    sess_time2 = datetime.now().strftime("%Y%m%d_%H%M%S")
                    sessions[session_id] = {
                        "state": create_initial_state("", sess_time2),
                        "chat_history": [],
                        "conversation_id": new_conv_id,
                    }
                    await websocket.send_json({
                        "type": "conversation_created",
                        "conversation_id": new_conv_id,
                    })
                    continue

            # ---- v3.0: 切换场景 ----
            if msg_type == "switch_scene":
                scene = data.get("scene", "chat")
                if session_id in sessions:
                    sessions[session_id]["scene"] = scene
                await websocket.send_json({
                    "type": "scene_switched",
                    "scene": scene,
                })
                continue

            # ---- v3.0: 确认执行任务组 ----
            if msg_type == "todo_confirm":
                group_id = data.get("group_id", "")
                if group_id:
                    from services.todo_service import TodoService
                    TodoService.update_group_status(group_id, "running")
                    group = TodoService.get_group(group_id)
                    if group:
                        import asyncio
                        from agents.proposition.solver import PropositionSolver
                        solver = PropositionSolver()
                        async def _on_update(msg):
                            await websocket.send_json(msg)
                        
                        user_input = session_data.get("user_input", "")
                        asyncio.create_task(
                            solver.execute_group(group, user_input, on_update=_on_update)
                        )
                continue

            # ---- v3.1: 大纲确认 ----
            if msg_type == "outline_confirm":
                outline = data.get("outline", {})
                group_id = data.get("group_id", "")
                if outline:
                    # 用户确认大纲，开始执行任务
                    await websocket.send_json({
                        "type": "outline_confirmed",
                        "outline": outline,
                        "message": "大纲已确认，开始执行..."
                    })
                    # TODO: 触发 Solver 执行
                continue

            # ---- v3.1: 大纲修改 ----
            if msg_type == "outline_modify":
                outline = data.get("outline", {})
                feedback = data.get("feedback", "")
                group_id = data.get("group_id", "")
                if feedback:
                    # 触发重新规划
                    try:
                        from agents.proposition.planner import PropositionPlanner
                        planner = PropositionPlanner()
                        new_plan = planner.replan(outline, feedback)

                        # 发送更新的大纲
                        await websocket.send_json({
                            "type": "outline_updated",
                            "outline": {
                                "title": new_plan.title,
                                "description": new_plan.summary,
                                "examSpec": {},
                                "questionDistribution": [
                                    {"type": t.title, "count": 1,
                                        "percentage": 100 / len(new_plan.tasks)}
                                    for t in new_plan.tasks
                                ],
                                "difficultyDistribution": {"easy": 0, "medium": 0, "hard": 0},
                                "estimatedTime": "约2-5分钟"
                            }
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"大纲修改失败: {str(e)}"
                        })
                continue

            # ---- v3.0: 执行单个任务 ----
            if msg_type == "todo_run_task":
                task_id = data.get("task_id", "")
                group_id = data.get("group_id", "")
                if task_id:
                    from services.todo_service import TodoService
                    task = TodoService.get_task(task_id)
                    if task:
                        # 异步执行（避免阻塞 WS 循环）
                        import asyncio
                        from agents.proposition.solver import PropositionSolver
                        sess = sessions.get(session_id, {})
                        user_q = sess.get("state", {}).get("user_input", "")
                        solver = PropositionSolver()

                        async def _run_task():
                            await solver.execute_task(
                                task, user_q,
                                on_update=lambda evt: websocket.send_json(evt)
                            )
                        asyncio.create_task(_run_task())
                continue

            # ---- 用户发送消息 ----
            if msg_type == "message":

                content = data.get("content", "").strip()
                if not content:
                    continue

                sess = sessions[session_id]
                state = sess["state"]
                chat_history = sess["chat_history"]

                state["user_input"] = content
                chat_history.append({
                    "role": "user",
                    "content": content,
                    "timestamp": datetime.now().isoformat()
                })

                # ---- 步骤计时器 ----
                step_timers: Dict[str, datetime] = {}
                current_steps: List[Dict] = []

                async def step_callback(step_name: str, detail: str, params: dict = None, step_id: str = None, parent_id: str = None):
                    """工作流步骤回调：推送步骤状态到客户端"""
                    now = datetime.now()
                    s_id = step_id or step_name

                    # 关闭上一个 running 步骤 (如果是同一层级的新步骤，或者没有任何指定)
                    for s in current_steps:
                        if s["status"] == "running" and s["step"] != s_id:
                            # 简化处理：默认只自动关闭同级，为了避免复杂的状态跟踪，直接由前端覆盖也行
                            # 但如果要计算准确时间，还需要完善。这里保持原来的简单逻辑
                            elapsed = (
                                now - step_timers.get(s["step"], now)).total_seconds()
                            s["status"] = "done"
                            s["elapsed"] = f"{elapsed:.1f}s"

                            # v3.1: 发送多种事件类型
                            # 1. agent_step (兼容旧版)
                            await websocket.send_json({
                                "type": "agent_step",
                                "step": s["step_name"],
                                "status": "done",
                                "detail": s.get("detail", ""),
                                "elapsed": s["elapsed"],
                                "step_id": s["step"],
                                "parent_id": s.get("parent_id")
                            })

                            # 2. status_update (v3.1 新增)
                            await websocket.send_json({
                                "type": "status_update",
                                "status": "done",
                                "step": s["step_name"],
                                "progress": 100,
                                "elapsed": s["elapsed"]
                            })

                    # 记录新步骤状态
                    existing_step = next(
                        (s for s in current_steps if s["step"] == s_id), None)
                    if not existing_step:
                        new_step = {
                            "step": s_id,
                            "step_name": step_name,
                            "parent_id": parent_id,
                            "status": "running",
                            "detail": detail,
                            "elapsed": None
                        }
                        current_steps.append(new_step)
                        step_timers[s_id] = now
                    else:
                        existing_step["status"] = "running"
                        existing_step["detail"] = detail

                    await websocket.send_json({
                        "type": "agent_step",
                        "step": step_name,
                        "status": "running",
                        "detail": detail,
                        "elapsed": None,
                        "step_id": step_id,
                        "parent_id": parent_id
                    })

                    if params:
                        await websocket.send_json({
                            "type": "agent_params",
                            "params": params
                        })

                # ---- 辩论回调 ----
                async def debate_callback(role: str, avatar: str, content: str):
                    await websocket.send_json({
                        "type": "debate_stream",
                        "role": role,
                        "avatar": avatar,
                        "content": content
                    })

                # ---- 运行工作流 ----
                try:
                    result = await run_workflow_async_server(
                        state,
                        chat_history,
                        status_callback=step_callback,
                        debate_callback=debate_callback
                    )
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"工作流执行失败: {str(e)}"
                    })
                    continue

                # ---- 关闭最后的 running 步骤 ----
                now = datetime.now()
                for s in current_steps:
                    if s["status"] == "running":
                        elapsed = (
                            now - step_timers.get(s["step"], now)).total_seconds()
                        await websocket.send_json({
                            "type": "agent_step",
                            "step": s["step_name"],
                            "status": "done",
                            "detail": s.get("detail", ""),
                            "elapsed": f"{elapsed:.1f}s",
                            "step_id": s["step"],
                            "parent_id": s.get("parent_id")
                        })

                # ---- 构建最终响应 ----
                final_response = result.get("final_response", "")
                if not final_response:
                    if result.get("draft_questions"):
                        final_response = format_questions_response(
                            result["draft_questions"])
                    else:
                        final_response = "任务处理完成，但未能生成有效结果，请重试。"

                # ---- 检测模式切换信号 ----
                mode_switch = result.get("mode_switch")
                mode_transition = result.get("mode_transition")
                print(
                    f"[DEBUG] Server mode_switch={mode_switch}, mode_transition={mode_transition}")
                if mode_switch and mode_transition in ["enter", "switch"]:
                    # 发送模式切换建议给前端
                    print(
                        f"[DEBUG] Sending mode_suggest to frontend: {mode_switch}")
                    await websocket.send_json({
                        "type": "mode_suggest",
                        "suggested_mode": mode_switch,
                        "transition": mode_transition
                    })

                # ---- v3.0: 场景切换建议（Chat Agent 检测命题/审题意图）----
                scene_hint = result.get("scene_switch_hint")
                if scene_hint in ("proposition", "review"):
                    await websocket.send_json({
                        "type": "scene_switch_hint",
                        "scene": scene_hint,
                    })

                # ---- v3.2: 任务看板挂起与推送 ----
                if "current_todo_group" in result:
                    await websocket.send_json({
                        "type": "todo_group_created",
                        "group": result["current_todo_group"],
                    })

                chart_history_updated = chat_history + [{
                    "role": "assistant",
                    "content": final_response,
                    "timestamp": datetime.now().isoformat()
                }]

                # 保存到对话历史
                current_conv_id = sess["conversation_id"]
                try:
                    conv_manager.add_message(current_conv_id, "user", content)
                    conv_manager.add_message(
                        current_conv_id, "assistant", final_response)
                except Exception:
                    pass

                # 发送最终文本响应
                await websocket.send_json({
                    "type": "response",
                    "content": final_response
                })

                # 如果有试题，额外发送结构化结果（用于右侧面板展示+下载）
                draft_questions = result.get("draft_questions", [])
                if draft_questions:
                    params = result.get("extracted_params", {})
                    await websocket.send_json({
                        "type": "result",
                        "markdown": final_response,
                        "question_count": len(draft_questions),
                        "topic": params.get("topic", "试题"),
                        "question_type": params.get("question_type", ""),
                        "difficulty": params.get("difficulty", ""),
                    })

                # 更新会话状态
                sess["state"] = result
                sess["chat_history"] = chart_history_updated

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket 异常: {e}")
    finally:
        sessions.pop(session_id, None)


# ==================== REST API ====================

@app.get("/api/conversations")
async def list_conversations(limit: int = Query(20, ge=1, le=100)):
    """获取历史对话列表"""
    conv_manager = get_conversation_manager()
    conversations = conv_manager.list_conversations(limit=limit)
    return {"conversations": conversations}


@app.post("/api/conversations")
async def create_conversation():
    """新建对话"""
    conv_manager = get_conversation_manager()
    conv = conv_manager.create_conversation()
    return conv


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """加载指定对话"""
    conv_manager = get_conversation_manager()
    conv = conv_manager.load_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除指定对话"""
    conv_manager = get_conversation_manager()
    success = conv_manager.delete_conversation(conversation_id)
    return {"success": success}


@app.delete("/api/conversations")
async def clear_all_conversations():
    """清除所有对话"""
    conv_manager = get_conversation_manager()
    count = conv_manager.clear_all_conversations()
    return {"deleted_count": count}


@app.get("/api/memories")
async def get_memories(limit: int = Query(20, ge=1, le=100)):
    """获取记忆库内容"""
    manager = get_memory_manager()
    memories = manager.get_all_memories(limit=limit)
    return {"memories": memories}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传知识库文件"""
    filename = file.filename or "uploaded_file"
    file_path = os.path.join("data", "knowledge_base", filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    if VECTOR_STORE_AVAILABLE:
        retriever = get_retriever()
        success = retriever.add_documents(file_path)
        return {
            "filename": filename,
            "success": success,
            "message": f"文件 {filename} 已{'成功' if success else '失败'}添加到知识库"
        }

    return {"filename": filename, "success": True, "message": f"文件 {filename} 已保存"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ==================== Skills & MCP API ====================

@app.get("/api/skills")
async def list_skills():
    """获取所有已注册的技能列表"""
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    return {"skills": registry.to_dict_list()}


@app.post("/api/skills/{skill_id}/enable")
async def enable_skill(skill_id: str):
    """启用指定技能"""
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    success = registry.enable(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    return {"success": True, "message": f"技能 {skill_id} 已启用"}


@app.post("/api/skills/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """禁用指定技能"""
    from skills.registry import get_skill_registry
    registry = get_skill_registry()
    success = registry.disable(skill_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"技能 {skill_id} 不存在")
    return {"success": True, "message": f"技能 {skill_id} 已禁用"}


@app.get("/api/mcp/status")
async def mcp_status():
    """获取 MCP 服务状态"""
    from utils.mcp_client import get_mcp_client
    client = get_mcp_client()
    return client.get_status()


@app.post("/api/asr")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    语音识别接口

    接收音频文件（WebM/WAV），调用 vllm Qwen ASR 服务转录为文字。

    Args:
        file: 上传的音频文件

    Returns:
        转录后的文本
    """
    import tempfile
    import base64

    # 保存临时文件
    suffix = ".webm" if "webm" in (file.content_type or "") else ".wav"
    try:
        content = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        # 读取并编码为 base64
        with open(tmp_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 构建 data URL
        mime = file.content_type or "audio/webm"
        audio_data_url = f"data:{mime};base64,{audio_b64}"

        # 调用 ASR 服务
        from utils.config import get_asr_client, settings
        client = get_asr_client()

        response = client.chat.completions.create(
            model=settings.asr_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_data_url,
                                "format": suffix.lstrip(".")
                            }
                        },
                        {
                            "type": "text",
                            "text": "请将这段语音转录为文字，只输出转录的文字内容，不要添加任何解释。"
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0
        )

        text = response.choices[0].message.content.strip()
        return {"text": text, "success": True}

    except Exception as e:
        print(f"ASR 转录失败: {e}")
        return JSONResponse(
            status_code=500,
            content={"text": "", "success": False, "error": str(e)}
        )
    finally:
        # 清理临时文件
        try:
            import os as _os
            _os.unlink(tmp_path)
        except Exception:
            pass


# ==================== 静态文件服务 ====================

# 先挂载 API 路由，再挂载静态文件（顺序重要）
frontend_dir = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "frontend")

# 注册模式切换 API
app.include_router(mode_router)
# 注册待办任务 API (v3.0)
app.include_router(todo_router)


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

# 挂载静态文件（CSS、JS 等）
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")


# ==================== 启动入口 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."]
    )
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["."]
    )
