"""
Skills 注册表和管理器

管理可安装、可绑定、可启用/禁用的技能模块。
技能可以绑定到特定的 Agent 节点（如 creator、auditor），
为其注入额外的 Prompt 和 Tools。
"""

import json
import os
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# 技能配置文件路径
SKILLS_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "skills"
)
SKILLS_CONFIG_FILE = os.path.join(SKILLS_CONFIG_DIR, "config.json")


@dataclass
class Skill:
    """技能定义"""

    id: str                          # 唯一标识
    name: str                        # 显示名称
    description: str                 # 技能描述
    category: str                    # 分类: validation / generation / analysis
    enabled: bool = False            # 是否启用
    prompt_template: str = ""        # 注入到 Agent 的额外 Prompt
    tool_module: str = ""            # 工具模块路径 (如 skills.code_verification)
    tool_function: str = ""          # 获取工具的函数名 (如 get_tools)
    bind_to: List[str] = field(      # 绑定到哪些 Agent 节点
        default_factory=list
    )
    version: str = "1.0.0"          # 版本号
    author: str = "IntelliExam"     # 作者

    def to_dict(self) -> dict:
        """转为字典（用于序列化）"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Skill":
        """从字典创建"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class SkillRegistry:
    """
    技能注册表

    管理所有已注册的技能，支持启用/禁用、按节点查询绑定的技能。
    技能状态持久化到 data/skills/config.json。
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}
        self._load_config()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        os.makedirs(SKILLS_CONFIG_DIR, exist_ok=True)

    def _load_config(self):
        """从配置文件加载技能启用状态"""
        self._ensure_config_dir()
        if os.path.exists(SKILLS_CONFIG_FILE):
            try:
                with open(SKILLS_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._enabled_map = data.get("enabled", {})
            except (json.JSONDecodeError, IOError):
                self._enabled_map = {}
        else:
            self._enabled_map = {}

    def _save_config(self):
        """保存技能启用状态到配置文件"""
        self._ensure_config_dir()
        data = {
            "enabled": {
                skill_id: skill.enabled
                for skill_id, skill in self._skills.items()
            }
        }
        with open(SKILLS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register(self, skill: Skill):
        """
        注册技能

        Args:
            skill: 技能实例
        """
        # 恢复保存的启用状态
        if skill.id in self._enabled_map:
            skill.enabled = self._enabled_map[skill.id]

        self._skills[skill.id] = skill
        logger.info(f"已注册技能: {skill.name} (id={skill.id}, enabled={skill.enabled})")

    def unregister(self, skill_id: str):
        """
        注销技能

        Args:
            skill_id: 技能 ID
        """
        if skill_id in self._skills:
            del self._skills[skill_id]
            self._save_config()
            logger.info(f"已注销技能: {skill_id}")

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        """获取指定技能"""
        return self._skills.get(skill_id)

    def get_all_skills(self) -> List[Skill]:
        """获取所有已注册的技能"""
        return list(self._skills.values())

    def get_skills_for_node(
        self,
        node_name: str,
        enabled_only: bool = True
    ) -> List[Skill]:
        """
        获取绑定到指定节点的技能

        Args:
            node_name: 节点名称 (creator/auditor/planner/...)
            enabled_only: 是否只返回已启用的技能

        Returns:
            技能列表
        """
        result = []
        for skill in self._skills.values():
            if node_name in skill.bind_to:
                if enabled_only and not skill.enabled:
                    continue
                result.append(skill)
        return result

    def enable(self, skill_id: str) -> bool:
        """
        启用技能

        Args:
            skill_id: 技能 ID

        Returns:
            是否成功
        """
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = True
            self._save_config()
            logger.info(f"已启用技能: {skill.name}")
            return True
        return False

    def disable(self, skill_id: str) -> bool:
        """
        禁用技能

        Args:
            skill_id: 技能 ID

        Returns:
            是否成功
        """
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = False
            self._save_config()
            logger.info(f"已禁用技能: {skill.name}")
            return True
        return False

    def get_tools_for_node(self, node_name: str) -> list:
        """
        获取指定节点绑定的所有已启用技能的 Tools

        Args:
            node_name: 节点名称

        Returns:
            LangChain Tool 列表
        """
        tools = []
        for skill in self.get_skills_for_node(node_name, enabled_only=True):
            if skill.tool_module and skill.tool_function:
                try:
                    import importlib
                    mod = importlib.import_module(skill.tool_module)
                    get_tools_fn = getattr(mod, skill.tool_function)
                    skill_tools = get_tools_fn()
                    tools.extend(skill_tools)
                except Exception as e:
                    logger.error(f"加载技能 {skill.id} 的工具失败: {e}")
        return tools

    def get_prompts_for_node(self, node_name: str) -> str:
        """
        获取指定节点绑定的所有已启用技能的 Prompt

        Args:
            node_name: 节点名称

        Returns:
            合并后的额外 Prompt 字符串
        """
        prompts = []
        for skill in self.get_skills_for_node(node_name, enabled_only=True):
            if skill.prompt_template:
                prompts.append(f"[Skill: {skill.name}]\n{skill.prompt_template}")
        return "\n\n".join(prompts)

    def to_dict_list(self) -> List[dict]:
        """将所有技能转为字典列表（用于 API 响应）"""
        return [skill.to_dict() for skill in self._skills.values()]


# ==================== 全局注册表 ====================

_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取全局技能注册表实例"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        # 自动注册内置技能
        _register_builtin_skills(_registry)
    return _registry


def _register_builtin_skills(registry: SkillRegistry):
    """注册内置技能"""
    try:
        from skills.code_verification import get_code_verification_skill
        registry.register(get_code_verification_skill())
        logger.info("内置技能注册完成")
    except Exception as e:
        logger.warning(f"内置技能注册失败: {e}")
