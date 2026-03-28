"""
待办任务服务层 - TodoService

负责 TodoGroup / TodoTask / TodoComment 的 CRUD 操作，
数据持久化到 SQLite 数据库。

主要方法：
- create_group(...)         → 创建任务组（Planner 输出时调用）
- get_group(group_id)       → 读取任务组（含所有任务）
- get_session_groups(...)   → 获取会话下所有任务组
- update_task_status(...)   → 更新任务状态/结果（Solver 调用）
- add_comment(...)          → 添加用户/Agent 评论
- mark_tasks_ready(...)     → 将 pending → ready（用户确认执行）
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any


# 数据库路径（与现有数据库同目录）
DB_PATH = Path(__file__).parent.parent / "data" / "todo.db"


def _get_conn() -> sqlite3.Connection:
    """获取数据库连接（Row 工厂模式）"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表（幂等操作）"""
    conn = _get_conn()
    try:
        conn.executescript("""
            -- 任务组表
            CREATE TABLE IF NOT EXISTS todo_groups (
                id          TEXT PRIMARY KEY,
                session_id  TEXT NOT NULL,
                scene       TEXT NOT NULL,   -- proposition | review
                title       TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'planning',
                planner_summary TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_todo_groups_session
                ON todo_groups(session_id);

            -- 待办任务表
            CREATE TABLE IF NOT EXISTS todo_tasks (
                id              TEXT PRIMARY KEY,
                task_group_id   TEXT NOT NULL REFERENCES todo_groups(id) ON DELETE CASCADE,
                title           TEXT NOT NULL,
                description     TEXT NOT NULL DEFAULT '',
                task_type       TEXT NOT NULL DEFAULT 'general',
                status          TEXT NOT NULL DEFAULT 'pending',
                dependencies    TEXT NOT NULL DEFAULT '[]',   -- JSON array of task IDs
                result          TEXT,
                result_data     TEXT,                          -- JSON blob
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL,
                elapsed_ms      INTEGER,
                sort_order      INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_todo_tasks_group
                ON todo_tasks(task_group_id);

            -- 评论表
            CREATE TABLE IF NOT EXISTS todo_comments (
                id          TEXT PRIMARY KEY,
                task_id     TEXT NOT NULL REFERENCES todo_tasks(id) ON DELETE CASCADE,
                author      TEXT NOT NULL,   -- user | agent
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_todo_comments_task
                ON todo_comments(task_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ==================== 内部辅助 ====================

def _now() -> str:
    return datetime.now().isoformat()


def _row_to_comment(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "author": row["author"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def _row_to_task(row: sqlite3.Row, comments: List[dict]) -> dict:
    return {
        "id": row["id"],
        "task_group_id": row["task_group_id"],
        "title": row["title"],
        "description": row["description"],
        "task_type": row["task_type"],
        "status": row["status"],
        "dependencies": json.loads(row["dependencies"]),
        "comments": comments,
        "result": row["result"],
        "result_data": json.loads(row["result_data"]) if row["result_data"] else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "elapsed_ms": row["elapsed_ms"],
        "order": row["sort_order"],
    }


def _row_to_group(row: sqlite3.Row, tasks: List[dict]) -> dict:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "scene": row["scene"],
        "title": row["title"],
        "status": row["status"],
        "planner_summary": row["planner_summary"],
        "tasks": tasks,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _load_tasks_for_group(conn: sqlite3.Connection, group_id: str) -> List[dict]:
    """从数据库加载任务组的所有任务（含评论）"""
    task_rows = conn.execute(
        "SELECT * FROM todo_tasks WHERE task_group_id=? ORDER BY sort_order",
        (group_id,)
    ).fetchall()

    tasks = []
    for row in task_rows:
        comment_rows = conn.execute(
            "SELECT * FROM todo_comments WHERE task_id=? ORDER BY created_at",
            (row["id"],)
        ).fetchall()
        comments = [_row_to_comment(c) for c in comment_rows]
        tasks.append(_row_to_task(row, comments))
    return tasks


# ==================== 公共接口 ====================

class TodoService:
    """待办任务服务（无状态，可直接调用静态方法）"""

    # ---------- 任务组 ----------

    @staticmethod
    def create_group(
        session_id: str,
        scene: str,
        title: str,
        tasks: List[Dict[str, Any]],
        planner_summary: str = "",
    ) -> dict:
        """
        创建任务组（Planner 规划完成后调用）

        Args:
            session_id: WebSocket 会话 ID
            scene: "proposition" | "review"
            title: 任务组标题
            tasks: 任务列表（每项包含 title/description/task_type/dependencies/order）
            planner_summary: Planner 的规划说明

        Returns:
            完整的任务组字典
        """
        init_db()
        group_id = str(uuid.uuid4())
        now = _now()

        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO todo_groups
                   (id, session_id, scene, title, status, planner_summary, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'planning', ?, ?, ?)""",
                (group_id, session_id, scene, title, planner_summary, now, now)
            )

            task_dicts = []
            for i, t in enumerate(tasks):
                task_id = str(uuid.uuid4())
                deps = json.dumps(t.get("dependencies", []), ensure_ascii=False)
                conn.execute(
                    """INSERT INTO todo_tasks
                       (id, task_group_id, title, description, task_type,
                        status, dependencies, created_at, updated_at, sort_order)
                       VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                    (
                        task_id, group_id,
                        t.get("title", ""),
                        t.get("description", ""),
                        t.get("task_type", "general"),
                        deps, now, now,
                        t.get("order", i)
                    )
                )
                task_dicts.append({
                    "id": task_id,
                    "task_group_id": group_id,
                    "title": t.get("title", ""),
                    "description": t.get("description", ""),
                    "task_type": t.get("task_type", "general"),
                    "status": "pending",
                    "dependencies": t.get("dependencies", []),
                    "comments": [],
                    "result": None,
                    "result_data": None,
                    "created_at": now,
                    "updated_at": now,
                    "elapsed_ms": None,
                    "order": t.get("order", i),
                })

            conn.commit()
        finally:
            conn.close()

        return {
            "id": group_id,
            "session_id": session_id,
            "scene": scene,
            "title": title,
            "status": "planning",
            "planner_summary": planner_summary,
            "tasks": task_dicts,
            "created_at": now,
            "updated_at": now,
        }

    @staticmethod
    def get_group(group_id: str) -> Optional[dict]:
        """获取任务组（含所有任务和评论）"""
        init_db()
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM todo_groups WHERE id=?", (group_id,)
            ).fetchone()
            if not row:
                return None
            tasks = _load_tasks_for_group(conn, group_id)
            return _row_to_group(row, tasks)
        finally:
            conn.close()

    @staticmethod
    def get_session_groups(session_id: str, limit: int = 20) -> List[dict]:
        """获取会话下所有任务组（摘要，不含任务详情）"""
        init_db()
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM todo_groups WHERE session_id=? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
            result = []
            for row in rows:
                tasks = _load_tasks_for_group(conn, row["id"])
                result.append(_row_to_group(row, tasks))
            return result
        finally:
            conn.close()

    @staticmethod
    def update_group_status(group_id: str, status: str) -> bool:
        """更新任务组状态"""
        init_db()
        conn = _get_conn()
        try:
            n = conn.execute(
                "UPDATE todo_groups SET status=?, updated_at=? WHERE id=?",
                (status, _now(), group_id)
            ).rowcount
            conn.commit()
            return n > 0
        finally:
            conn.close()

    @staticmethod
    def delete_group(group_id: str) -> bool:
        """删除任务组（级联删除所有任务和评论）"""
        init_db()
        conn = _get_conn()
        try:
            n = conn.execute(
                "DELETE FROM todo_groups WHERE id=?", (group_id,)
            ).rowcount
            conn.commit()
            return n > 0
        finally:
            conn.close()

    # ---------- 任务 ----------

    @staticmethod
    def get_task(task_id: str) -> Optional[dict]:
        """获取单个任务"""
        init_db()
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM todo_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row:
                return None
            comment_rows = conn.execute(
                "SELECT * FROM todo_comments WHERE task_id=? ORDER BY created_at",
                (task_id,)
            ).fetchall()
            return _row_to_task(row, [_row_to_comment(c) for c in comment_rows])
        finally:
            conn.close()

    @staticmethod
    def update_task_status(
        task_id: str,
        status: str,
        result: Optional[str] = None,
        result_data: Optional[dict] = None,
        elapsed_ms: Optional[int] = None,
    ) -> Optional[dict]:
        """
        更新任务状态和执行结果（Solver 调用）

        Returns:
            更新后的任务字典，或 None（任务不存在）
        """
        init_db()
        conn = _get_conn()
        try:
            result_data_str = json.dumps(result_data, ensure_ascii=False) if result_data else None
            n = conn.execute(
                """UPDATE todo_tasks
                   SET status=?, result=?, result_data=?, elapsed_ms=?, updated_at=?
                   WHERE id=?""",
                (status, result, result_data_str, elapsed_ms, _now(), task_id)
            ).rowcount
            conn.commit()
            if n == 0:
                return None
            return TodoService.get_task(task_id)
        finally:
            conn.close()

    @staticmethod
    def mark_tasks_ready(group_id: str) -> int:
        """将任务组中所有 pending 任务标记为 ready（用户确认执行后调用）"""
        init_db()
        conn = _get_conn()
        try:
            n = conn.execute(
                "UPDATE todo_tasks SET status='ready', updated_at=? WHERE task_group_id=? AND status='pending'",
                (_now(), group_id)
            ).rowcount
            conn.execute(
                "UPDATE todo_groups SET status='ready', updated_at=? WHERE id=?",
                (_now(), group_id)
            )
            conn.commit()
            return n
        finally:
            conn.close()

    # ---------- 评论 ----------

    @staticmethod
    def add_comment(
        task_id: str,
        content: str,
        author: str = "user",
    ) -> Optional[dict]:
        """
        为任务添加评论

        Returns:
            评论字典，或 None（任务不存在）
        """
        init_db()
        conn = _get_conn()
        try:
            # 确认任务存在
            exists = conn.execute(
                "SELECT 1 FROM todo_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not exists:
                return None

            comment_id = str(uuid.uuid4())
            now = _now()
            conn.execute(
                "INSERT INTO todo_comments (id, task_id, author, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (comment_id, task_id, author, content, now)
            )
            # 任务状态如果是 done，评论后标记为 need_revision
            task_row = conn.execute(
                "SELECT status FROM todo_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if task_row and task_row["status"] in ("done", "ready"):
                conn.execute(
                    "UPDATE todo_tasks SET status='need_revision', updated_at=? WHERE id=?",
                    (now, task_id)
                )
            conn.commit()
            return {"id": comment_id, "author": author, "content": content, "created_at": now}
        finally:
            conn.close()

    @staticmethod
    def get_task_comments(task_id: str) -> List[dict]:
        """获取任务的所有评论"""
        init_db()
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM todo_comments WHERE task_id=? ORDER BY created_at",
                (task_id,)
            ).fetchall()
            return [_row_to_comment(r) for r in rows]
        finally:
            conn.close()


# 模块级初始化
init_db()

# 导出便捷函数（供 Agent 直接调用）
todo_service = TodoService()
