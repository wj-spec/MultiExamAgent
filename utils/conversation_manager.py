"""
对话历史管理

管理对话历史的本地存储，支持多会话管理。
"""

import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
import uuid


class ConversationState:
    """
    会话状态类

    用于管理单个会话的状态信息，
    包括当前模式和命题上下文。
    """

    def __init__(self):
        self.current_mode: str = "chat"  # proposition / chat / mixed
        self.last_proposition_params: dict = {}
        self.proposition_in_progress: bool = False

    def to_dict(self) -> dict:
        return {
            "current_mode": self.current_mode,
            "last_proposition_params": self.last_proposition_params,
            "proposition_in_progress": self.proposition_in_progress
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationState":
        state = cls()
        state.current_mode = data.get("current_mode", "chat")
        state.last_proposition_params = data.get("last_proposition_params", {})
        state.proposition_in_progress = data.get(
            "proposition_in_progress", False)
        return state


class ConversationManager:
    """
    对话历史管理器

    负责管理存储在本地的 JSON 格式对话历史数据，
    支持创建、加载、删除会话等功能。
    支持会话状态管理（当前模式和命题上下文）。
    """

    def __init__(self, conversations_dir: str = None):
        """
        初始化对话管理器

        Args:
            conversations_dir: 对话历史目录，默认为 data/conversations/
        """
        if conversations_dir is None:
            # 获取项目根目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            conversations_dir = os.path.join(
                project_root, "data", "conversations")

        self.conversations_dir = conversations_dir
        self.index_file = os.path.join(conversations_dir, "index.json")
        self._ensure_directories()

    def _ensure_directories(self):
        """确保目录和索引文件存在"""
        os.makedirs(self.conversations_dir, exist_ok=True)

        if not os.path.exists(self.index_file):
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump({"conversations": []}, f,
                          ensure_ascii=False, indent=2)

    def _load_index(self) -> Dict[str, Any]:
        """加载对话索引"""
        try:
            with open(self.index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"conversations": []}

    def _save_index(self, index: Dict[str, Any]):
        """保存对话索引"""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _get_conversation_file(self, conversation_id: str) -> str:
        """获取对话文件路径"""
        return os.path.join(self.conversations_dir, f"{conversation_id}.json")

    def create_conversation(
        self,
        title: str = None,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        创建新对话

        Args:
            title: 对话标题，如果不提供则使用时间戳
            metadata: 元数据

        Returns:
            新创建的对话信息
        """
        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        if title is None:
            title = f"对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        conversation = {
            "id": conversation_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "message_count": 0,
            "metadata": metadata or {},
            "messages": []
        }

        # 保存对话文件
        conversation_file = self._get_conversation_file(conversation_id)
        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, ensure_ascii=False, indent=2)

        # 更新索引
        index = self._load_index()
        index["conversations"].insert(0, {
            "id": conversation_id,
            "title": title,
            "created_at": conversation["created_at"],
            "updated_at": conversation["updated_at"],
            "message_count": 0
        })
        self._save_index(index)

        return conversation

    def load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        加载对话

        Args:
            conversation_id: 对话ID

        Returns:
            对话数据或 None
        """
        conversation_file = self._get_conversation_file(conversation_id)

        if not os.path.exists(conversation_file):
            return None

        try:
            with open(conversation_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def save_conversation(self, conversation: Dict[str, Any]) -> bool:
        """
        保存对话

        Args:
            conversation: 对话数据

        Returns:
            是否成功保存
        """
        conversation_id = conversation.get("id")
        if not conversation_id:
            return False

        # 更新时间戳和消息数量
        conversation["updated_at"] = datetime.now().isoformat()
        conversation["message_count"] = len(conversation.get("messages", []))

        # 保存对话文件
        conversation_file = self._get_conversation_file(conversation_id)
        with open(conversation_file, 'w', encoding='utf-8') as f:
            json.dump(conversation, f, ensure_ascii=False, indent=2)

        # 更新索引
        index = self._load_index()
        for conv in index["conversations"]:
            if conv["id"] == conversation_id:
                conv["updated_at"] = conversation["updated_at"]
                conv["message_count"] = conversation["message_count"]
                break

        # 按更新时间排序
        index["conversations"].sort(
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
        self._save_index(index)

        return True

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        向对话添加消息

        Args:
            conversation_id: 对话ID
            role: 消息角色 (user/assistant)
            content: 消息内容
            metadata: 元数据

        Returns:
            更新后的对话数据或 None
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        message = {
            "id": f"msg_{uuid.uuid4().hex[:8]}",
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        conversation["messages"].append(message)
        self.save_conversation(conversation)

        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除对话

        Args:
            conversation_id: 对话ID

        Returns:
            是否成功删除
        """
        conversation_file = self._get_conversation_file(conversation_id)

        # 删除对话文件
        if os.path.exists(conversation_file):
            os.remove(conversation_file)

        # 更新索引
        index = self._load_index()
        index["conversations"] = [
            conv for conv in index["conversations"]
            if conv["id"] != conversation_id
        ]
        self._save_index(index)

        return True

    def list_conversations(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取对话列表

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            对话摘要列表
        """
        index = self._load_index()
        conversations = index.get("conversations", [])

        return conversations[offset:offset + limit]

    def search_conversations(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索对话

        Args:
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            匹配的对话列表
        """
        index = self._load_index()
        conversations = index.get("conversations", [])

        results = []
        query_lower = query.lower()

        for conv in conversations:
            # 搜索标题
            if query_lower in conv.get("title", "").lower():
                results.append(conv)
                continue

            # 搜索消息内容
            conversation = self.load_conversation(conv["id"])
            if conversation:
                for msg in conversation.get("messages", []):
                    if query_lower in msg.get("content", "").lower():
                        results.append(conv)
                        break

            if len(results) >= limit:
                break

        return results

    def get_recent_conversations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的对话

        Args:
            limit: 返回数量限制

        Returns:
            最近的对话列表
        """
        return self.list_conversations(limit=limit)

    def clear_all_conversations(self) -> int:
        """
        清除所有对话（谨慎使用）

        Returns:
            删除的对话数量
        """
        index = self._load_index()
        count = len(index.get("conversations", []))

        # 删除所有对话文件
        for conv in index.get("conversations", []):
            conversation_file = self._get_conversation_file(conv["id"])
            if os.path.exists(conversation_file):
                os.remove(conversation_file)

        # 清空索引
        self._save_index({"conversations": []})

        return count

    def export_conversation(self, conversation_id: str) -> Optional[str]:
        """
        导出对话为 Markdown 格式

        Args:
            conversation_id: 对话ID

        Returns:
            Markdown 格式的对话内容或 None
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        md = f"# {conversation['title']}\n\n"
        md += f"创建时间: {conversation['created_at']}\n\n"
        md += "---\n\n"

        for msg in conversation.get("messages", []):
            role = "用户" if msg["role"] == "user" else "助手"
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "")

            md += f"### {role} ({timestamp})\n\n{content}\n\n"

        return md

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        index = self._load_index()
        conversations = index.get("conversations", [])

        total_messages = 0
        for conv in conversations:
            conversation = self.load_conversation(conv["id"])
            if conversation:
                total_messages += len(conversation.get("messages", []))

        return {
            "total_conversations": len(conversations),
            "total_messages": total_messages,
            "conversations_dir": self.conversations_dir
        }

    # ==================== 会话状态管理 ====================

    def get_conversation_state(self, conversation_id: str) -> Optional[ConversationState]:
        """
        获取会话状态

        Args:
            conversation_id: 会话ID

        Returns:
            ConversationState 对象或 None
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return None

        state_data = conversation.get("conversation_state", {})
        return ConversationState.from_dict(state_data)

    def update_conversation_state(
        self,
        conversation_id: str,
        state: ConversationState
    ) -> bool:
        """
        更新会话状态

        Args:
            conversation_id: 会话ID
            state: ConversationState 对象

        Returns:
            是否成功更新
        """
        conversation = self.load_conversation(conversation_id)
        if not conversation:
            return False

        conversation["conversation_state"] = state.to_dict()
        return self.save_conversation(conversation)

    def update_mode(
        self,
        conversation_id: str,
        mode: str
    ) -> bool:
        """
        更新会话模式

        Args:
            conversation_id: 会话ID
            mode: 新模式 (proposition/chat)

        Returns:
            是否成功更新
        """
        state = self.get_conversation_state(conversation_id)
        if not state:
            state = ConversationState()

        state.current_mode = mode
        return self.update_conversation_state(conversation_id, state)

    def update_proposition_params(
        self,
        conversation_id: str,
        params: dict
    ) -> bool:
        """
        更新命题参数

        Args:
            conversation_id: 会话ID
            params: 命题参数字典

        Returns:
            是否成功更新
        """
        state = self.get_conversation_state(conversation_id)
        if not state:
            state = ConversationState()

        state.last_proposition_params = params
        state.proposition_in_progress = True
        return self.update_conversation_state(conversation_id, state)

    def clear_proposition_state(self, conversation_id: str) -> bool:
        """
        清除命题状态

        Args:
            conversation_id: 会话ID

        Returns:
            是否成功清除
        """
        state = self.get_conversation_state(conversation_id)
        if not state:
            return False

        state.proposition_in_progress = False
        state.current_mode = "chat"
        return self.update_conversation_state(conversation_id, state)


# 全局单例
_conversation_manager_instance = None


def get_conversation_manager() -> ConversationManager:
    """获取全局对话管理器实例"""
    global _conversation_manager_instance
    if _conversation_manager_instance is None:
        _conversation_manager_instance = ConversationManager()
    return _conversation_manager_instance
