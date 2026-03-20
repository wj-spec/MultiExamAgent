"""
语音处理工具 - 支持语音转文字和文本规范化

共享工具，基础模式和专业模式均可调用。
"""

import os
import tempfile
import logging
import re
from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool

logger = logging.getLogger(__name__)


@register_tool
class SpeechToTextTool(BaseTool):
    """
    语音转文字工具

    将用户的语音输入转换为文字。
    支持多种音频格式。
    """

    def __init__(self):
        super().__init__()
        self._name = "speech_to_text"
        self._description = (
            "将用户的语音输入转换为文字。"
            "支持 WebM、WAV、MP3 等常见音频格式。"
            "适用于语音命题、语音问答等场景。"
        )
        self._parameters = [
            ToolParameter(
                name="audio_data",
                type="string",
                description="音频数据的 Base64 编码或文件路径",
                required=True
            ),
            ToolParameter(
                name="language",
                type="string",
                description="语言代码，如 zh、en",
                required=False,
                default="zh"
            )
        ]

    def execute(self, audio_data: str, language: str = "zh") -> ToolResult:
        """
        执行语音转文字

        Args:
            audio_data: Base64编码的音频数据或文件路径
            language: 语言代码

        Returns:
            转换结果
        """
        try:
            logger.info(f"[SpeechToText] 开始语音识别，语言: {language}")

            # 判断是文件路径还是 Base64 数据
            if os.path.exists(audio_data):
                audio_path = audio_data
            else:
                # Base64 解码并保存临时文件
                import base64
                audio_bytes = base64.b64decode(audio_data)
                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                    f.write(audio_bytes)
                    audio_path = f.name

            # 执行语音识别
            text = self._transcribe(audio_path, language)

            # 清理临时文件
            if not os.path.exists(audio_data):
                os.unlink(audio_path)

            if text:
                logger.info(f"[SpeechToText] 识别成功: {text[:50]}...")
                return ToolResult(
                    success=True,
                    data={
                        "text": text,
                        "language": language
                    }
                )
            else:
                return ToolResult(
                    success=True,
                    data={
                        "text": "",
                        "message": "未能识别出语音内容"
                    }
                )

        except Exception as e:
            logger.error(f"[SpeechToText] 识别失败: {e}")
            return ToolResult(
                success=False,
                error=f"语音识别失败: {str(e)}"
            )

    def _transcribe(self, audio_path: str, language: str) -> str:
        """
        执行语音转录

        Args:
            audio_path: 音频文件路径
            language: 语言代码

        Returns:
            转录文本
        """
        try:
            from openai import OpenAI
            from utils.config import get_openai_config

            config = get_openai_config()
            client = OpenAI(api_key=config.get("api_key"))

            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language
                )

            return transcript.text

        except ImportError:
            logger.warning("[SpeechToText] OpenAI 库未安装，尝试使用本地模型")
            return self._local_transcribe(audio_path, language)

        except Exception as e:
            logger.error(f"[SpeechToText] Whisper API 调用失败: {e}")
            return self._local_transcribe(audio_path, language)

    def _local_transcribe(self, audio_path: str, language: str) -> str:
        """
        使用本地模型进行语音转录（备用方案）

        Args:
            audio_path: 音频文件路径
            language: 语言代码

        Returns:
            转录文本
        """
        try:
            # 尝试使用 whisper 本地模型
            import whisper

            model = whisper.load_model("base")
            result = model.transcribe(audio_path, language=language)
            return result["text"]

        except ImportError:
            return "[语音识别服务不可用，请安装 openai 或 whisper]"

        except Exception as e:
            return f"[本地语音识别失败: {e}]"


@register_tool
class TextNormalizeTool(BaseTool):
    """
    文本规范化工具

    对用户输入的文本进行规范化处理。
    """

    def __init__(self):
        super().__init__()
        self._name = "text_normalize"
        self._description = (
            "对用户输入的文本进行规范化处理。"
            "包括去除多余空白、统一标点、修正常见错误等。"
        )
        self._parameters = [
            ToolParameter(
                name="text",
                type="string",
                description="待规范化的文本",
                required=True
            ),
            ToolParameter(
                name="options",
                type="string",
                description="规范化选项：basic(基础)、full(完整)",
                required=False,
                default="basic"
            )
        ]

    def execute(self, text: str, options: str = "basic") -> ToolResult:
        """
        执行文本规范化

        Args:
            text: 待处理的文本
            options: 规范化选项

        Returns:
            规范化后的文本
        """
        try:
            original_text = text

            # 基础规范化
            text = self._basic_normalize(text)

            # 完整规范化
            if options == "full":
                text = self._full_normalize(text)

            return ToolResult(
                success=True,
                data={
                    "original_text": original_text,
                    "normalized_text": text,
                    "options": options
                }
            )

        except Exception as e:
            logger.error(f"[TextNormalize] 规范化失败: {e}")
            return ToolResult(
                success=False,
                error=f"文本规范化失败: {str(e)}"
            )

    def _basic_normalize(self, text: str) -> str:
        """基础规范化"""
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text)

        # 去除首尾空白
        text = text.strip()

        # 统一中文标点
        punctuation_map = {
            ',': '，',
            '.': '。',
            '?': '？',
            '!': '！',
            ':': '：',
            ';': '；',
            '(': '（',
            ')': '）',
        }

        # 只替换中文语境下的标点
        for eng, chn in punctuation_map.items():
            # 检查周围是否有中文字符
            text = re.sub(
                rf'([\u4e00-\u9fff]){eng}',
                rf'\1{chn}',
                text
            )
            text = re.sub(
                rf'{eng}([\u4e00-\u9fff])',
                rf'{chn}\1',
                text
            )

        return text

    def _full_normalize(self, text: str) -> str:
        """完整规范化"""
        text = self._basic_normalize(text)

        # 修正常见错误
        corrections = {
            '的地得': {
                '高兴的跳': '高兴地跳',
                '快的跑': '快地跑',
            },
            '常见错字': {
                '做题目': '做题',
                '以经': '已经',
                '在说': '再说',
            }
        }

        for category, items in corrections.items():
            for wrong, right in items.items():
                text = text.replace(wrong, right)

        return text


@register_tool
class ExtractIntentFromSpeechTool(BaseTool):
    """
    从语音提取意图工具

    分析语音输入内容，提取用户意图和关键信息。
    """

    def __init__(self):
        super().__init__()
        self._name = "extract_intent_from_speech"
        self._description = (
            "分析语音输入内容，提取用户意图和关键信息。"
            "适用于语音命题场景，自动识别知识点、题型等。"
        )
        self._parameters = [
            ToolParameter(
                name="text",
                type="string",
                description="语音转文字后的文本",
                required=True
            )
        ]

    def execute(self, text: str) -> ToolResult:
        """
        执行意图提取

        Args:
            text: 语音转文字后的文本

        Returns:
            提取的意图和关键信息
        """
        try:
            # 定义意图关键词
            intent_keywords = {
                "proposition": ["出题", "命题", "生成试题", "考题", "做一套", "设计题目", "出几道"],
                "grading": ["阅卷", "批改", "评分", "打分", "审卷", "改卷"],
                "paper_generation": ["组卷", "生成试卷", "出一套卷", "试卷"],
                "review": ["审核", "检查", "审题", "把关"],
                "knowledge_query": ["什么是", "解释", "讲解", "介绍一下", "帮我理解"],
                "chat": []
            }

            # 定义题型关键词
            question_type_keywords = {
                "choice": ["选择题", "单选", "多选"],
                "fill_blank": ["填空题", "填空"],
                "essay": ["解答题", "简答题", "论述题", "计算题"],
                "judgment": ["判断题", "判断"],
            }

            # 定义难度关键词
            difficulty_keywords = {
                "easy": ["简单", "基础", "容易", "入门"],
                "medium": ["中等", "适中", "一般"],
                "hard": ["困难", "难", "高难度", "挑战"],
            }

            # 提取意图
            detected_intents = []
            text_lower = text.lower()

            for intent, keywords in intent_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        detected_intents.append(intent)
                        break

            # 提取题型
            detected_types = []
            for qtype, keywords in question_type_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        detected_types.append(qtype)
                        break

            # 提取难度
            detected_difficulty = None
            for diff, keywords in difficulty_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        detected_difficulty = diff
                        break

            # 提取数量
            count = None
            count_match = re.search(r'(\d+)\s*[道个条]', text)
            if count_match:
                count = int(count_match.group(1))

            # 提取学科/知识点
            subjects = ["数学", "物理", "化学", "生物", "语文", "英语", "历史", "地理", "政治"]
            detected_subjects = [s for s in subjects if s in text]

            return ToolResult(
                success=True,
                data={
                    "original_text": text,
                    "intents": detected_intents,
                    "primary_intent": detected_intents[0] if detected_intents else "chat",
                    "question_types": detected_types,
                    "difficulty": detected_difficulty,
                    "count": count,
                    "subjects": detected_subjects
                }
            )

        except Exception as e:
            logger.error(f"[ExtractIntent] 提取失败: {e}")
            return ToolResult(
                success=False,
                error=f"意图提取失败: {str(e)}"
            )


def get_speech_tools() -> List[BaseTool]:
    """
    获取所有语音处理工具

    Returns:
        工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "speech_to_text",
        "text_normalize",
        "extract_intent_from_speech"
    ])
