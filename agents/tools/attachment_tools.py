"""
附件处理工具 - 支持文件上传、解析和内容提取

共享工具，基础模式和专业模式均可调用。
支持 PDF、Word、图片等格式。
"""

import os
import tempfile
import logging
from typing import List, Optional, Dict, Any
from agents.tools.base import BaseTool, ToolParameter, ToolResult, register_tool

logger = logging.getLogger(__name__)


@register_tool
class AnalyzeAttachmentTool(BaseTool):
    """
    附件分析工具

    分析用户上传的附件内容，提取关键信息。
    支持 PDF、Word、图片等格式。
    """

    def __init__(self):
        super().__init__()
        self._name = "analyze_attachment"
        self._description = (
            "分析用户上传的附件内容，提取关键信息。"
            "支持 PDF、Word、图片等格式。"
            "可用于分析试卷、教材、参考资料等文档。"
        )
        self._parameters = [
            ToolParameter(
                name="file_path",
                type="string",
                description="文件路径或文件ID",
                required=True
            ),
            ToolParameter(
                name="purpose",
                type="string",
                description="分析目的，如'提取试题'、'理解教材内容'、'分析试卷结构'",
                required=False,
                default="理解文件内容"
            )
        ]

    def execute(self, file_path: str, purpose: str = "理解文件内容") -> ToolResult:
        """
        执行附件分析

        Args:
            file_path: 文件路径
            purpose: 分析目的

        Returns:
            分析结果
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {file_path}"
                )

            # 获取文件扩展名
            ext = os.path.splitext(file_path)[1].lower()
            filename = os.path.basename(file_path)

            logger.info(f"[AnalyzeAttachment] 正在分析: {filename}, 目的: {purpose}")

            # 根据文件类型选择解析方式
            if ext == '.pdf':
                content = self._extract_pdf(file_path)
            elif ext in ['.doc', '.docx']:
                content = self._extract_docx(file_path)
            elif ext in ['.txt', '.md']:
                content = self._extract_text(file_path)
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                content = self._extract_image(file_path)
            else:
                return ToolResult(
                    success=False,
                    error=f"不支持的文件格式: {ext}"
                )

            # 生成内容摘要
            summary = self._generate_summary(content, purpose)

            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "filename": filename,
                    "file_type": ext,
                    "purpose": purpose,
                    "content_preview": content[:1000],
                    "full_content": content,
                    "content_length": len(content),
                    "summary": summary
                }
            )

        except Exception as e:
            logger.error(f"[AnalyzeAttachment] 分析失败: {e}")
            return ToolResult(
                success=False,
                error=f"附件分析失败: {str(e)}"
            )

    def _extract_pdf(self, file_path: str) -> str:
        """提取 PDF 内容"""
        try:
            from langchain_community.document_loaders import PyPDFLoader
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            content = "\n\n".join([doc.page_content for doc in docs])
            logger.info(f"[AnalyzeAttachment] PDF提取完成，页数: {len(docs)}")
            return content
        except ImportError:
            # 备用方案：使用 PyPDF2
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    content = "\n\n".join([page.extract_text()
                                          for page in reader.pages])
                return content
            except Exception as e:
                return f"[PDF提取失败: {e}]"
        except Exception as e:
            return f"[PDF提取失败: {e}]"

    def _extract_docx(self, file_path: str) -> str:
        """提取 Word 文档内容"""
        try:
            from langchain_community.document_loaders import UnstructuredWordDocumentLoader
            loader = UnstructuredWordDocumentLoader(file_path)
            docs = loader.load()
            content = "\n".join([doc.page_content for doc in docs])
            logger.info(f"[AnalyzeAttachment] Word提取完成")
            return content
        except ImportError:
            # 备用方案：使用 python-docx
            try:
                from docx import Document
                doc = Document(file_path)
                content = "\n".join([para.text for para in doc.paragraphs])
                return content
            except Exception as e:
                return f"[Word提取失败: {e}]"
        except Exception as e:
            return f"[Word提取失败: {e}]"

    def _extract_text(self, file_path: str) -> str:
        """提取纯文本内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gbk') as f:
                return f.read()

    def _extract_image(self, file_path: str) -> str:
        """提取图片内容（OCR 或 Vision）"""
        try:
            from utils.config import get_llm_config
            llm_config = get_llm_config()

            # 检查是否支持 Vision
            vision_model = llm_config.get("vision_model", "")
            if vision_model:
                return self._vision_analysis(file_path, vision_model)
            else:
                return "[图片内容需要 Vision API 支持，请配置 vision_model]"

        except Exception as e:
            return f"[图片处理失败: {e}]"

    def _vision_analysis(self, file_path: str, model: str) -> str:
        """使用 Vision API 分析图片"""
        try:
            import base64
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage
            from utils.config import get_llm

            # 读取图片
            with open(file_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')

            # 获取图片格式
            ext = os.path.splitext(file_path)[1].lower()
            mime_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(ext, 'image/jpeg')

            # 构建消息
            llm = get_llm(model=model)

            message = HumanMessage(content=[
                {"type": "text", "text": "请详细描述这张图片的内容，如果有文字请完整提取。"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_data}"
                    }
                }
            ])

            response = llm.invoke([message])
            return response.content

        except Exception as e:
            return f"[Vision分析失败: {e}]"

    def _generate_summary(self, content: str, purpose: str) -> str:
        """生成内容摘要"""
        if not content or len(content) < 100:
            return content

        # 简单截取前200字作为摘要
        summary = content[:200]
        if len(content) > 200:
            summary += "..."
        return summary


@register_tool
class UploadToKnowledgeBaseTool(BaseTool):
    """
    上传到知识库工具

    将文件上传到知识库，以便后续检索使用。
    """

    def __init__(self):
        super().__init__()
        self._name = "upload_to_knowledge_base"
        self._description = (
            "将文件上传到知识库，以便后续检索使用。"
            "支持 PDF、Word 等格式。"
            "上传后可通过知识检索工具查询相关内容。"
        )
        self._parameters = [
            ToolParameter(
                name="file_path",
                type="string",
                description="要上传的文件路径",
                required=True
            ),
            ToolParameter(
                name="category",
                type="string",
                description="知识分类，如'教材'、'试卷'、'参考资料'",
                required=False,
                default="通用"
            )
        ]

    def execute(self, file_path: str, category: str = "通用") -> ToolResult:
        """
        执行上传到知识库

        Args:
            file_path: 文件路径
            category: 知识分类

        Returns:
            上传结果
        """
        try:
            if not os.path.exists(file_path):
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {file_path}"
                )

            from tools.retriever import get_retriever

            retriever = get_retriever()
            success = retriever.add_documents(file_path)

            if success:
                filename = os.path.basename(file_path)
                logger.info(f"[UploadToKnowledgeBase] 上传成功: {filename}")

                return ToolResult(
                    success=True,
                    data={
                        "uploaded": True,
                        "filename": filename,
                        "category": category,
                        "message": f"文件 '{filename}' 已成功上传到知识库"
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error="文件上传失败，请检查文件格式"
                )

        except Exception as e:
            logger.error(f"[UploadToKnowledgeBase] 上传失败: {e}")
            return ToolResult(
                success=False,
                error=f"上传失败: {str(e)}"
            )


@register_tool
class ExtractQuestionsFromDocumentTool(BaseTool):
    """
    从文档提取试题工具

    专门用于从试卷、练习册等文档中提取试题内容。
    """

    def __init__(self):
        super().__init__()
        self._name = "extract_questions_from_document"
        self._description = (
            "从试卷、练习册等文档中提取试题内容。"
            "自动识别题型、题号、选项、答案等结构化信息。"
        )
        self._parameters = [
            ToolParameter(
                name="file_path",
                type="string",
                description="文档路径",
                required=True
            )
        ]

    def execute(self, file_path: str) -> ToolResult:
        """
        执行试题提取

        Args:
            file_path: 文档路径

        Returns:
            提取的试题列表
        """
        try:
            # 首先提取文档内容
            analyze_tool = AnalyzeAttachmentTool()
            result = analyze_tool.execute(file_path, purpose="提取试题")

            if not result.success:
                return result

            content = result.data.get("full_content", "")

            # 使用 LLM 结构化提取试题
            from utils.config import get_llm
            from langchain_core.messages import SystemMessage, HumanMessage

            llm = get_llm(temperature=0)

            system_prompt = """你是一个专业的试题提取助手。请从给定的文档内容中提取所有试题。

对于每道试题，请提取以下信息：
1. 题号
2. 题型（选择题/填空题/解答题/判断题等）
3. 题目内容
4. 选项（如果是选择题）
5. 答案（如果有）
6. 解析（如果有）

请以 JSON 格式返回，格式如下：
{
    "questions": [
        {
            "number": 1,
            "type": "选择题",
            "content": "题目内容",
            "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"],
            "answer": "A",
            "explanation": "解析内容"
        }
    ],
    "total_count": 10
}
"""

            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"请从以下文档内容中提取试题：\n\n{content[:5000]}")
            ])

            # 解析 JSON
            import json
            import re

            json_match = re.search(r'\{[\s\S]*\}', response.content)
            if json_match:
                questions_data = json.loads(json_match.group())
            else:
                questions_data = {"questions": [], "total_count": 0}

            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "questions": questions_data.get("questions", []),
                    "total_count": questions_data.get("total_count", 0),
                    "raw_content": content[:2000]
                }
            )

        except Exception as e:
            logger.error(f"[ExtractQuestions] 提取失败: {e}")
            return ToolResult(
                success=False,
                error=f"试题提取失败: {str(e)}"
            )


def get_attachment_tools() -> List[BaseTool]:
    """
    获取所有附件处理工具

    Returns:
        工具列表
    """
    from agents.tools.base import registry
    return registry.get_tools([
        "analyze_attachment",
        "upload_to_knowledge_base",
        "extract_questions_from_document"
    ])
