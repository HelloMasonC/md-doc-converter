"""MarkItDown 转换封装模块。

负责对 markitdown 库进行惰性单例封装，提供文件转 Markdown、
输出路径计算与 Markdown 文件写入等功能。

额外职责（本工具新增）：
  * 若用户已在本地配置好多模态视觉模型（Base URL / API Key / 模型名），
    则自动把一个"鸭子类型"的 OpenAI 兼容 client 注入到 MarkItDown 图片转换器的
    `llm_client` / `llm_model` 参数上，使图片识别真正可用。
  * 暴露 `reload_vision_client()` 让 UI 点"保存配置"后可立即生效。
"""
from __future__ import annotations

import os
from typing import Any, Optional


# 尝试导入 markitdown，若失败则标记不可用
try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False
    MarkItDown = None  # 类型占位，避免引用时报 NameError


# 模块级单例，惰性创建，避免每次转换都新建实例
_md_instance = None

# 图片转换器默认附加的 kwargs（视觉模型存在时这里会被填好 llm_client / llm_model / llm_prompt）
_IMAGE_CONVERT_KWARGS: dict[str, Any] = {}


def _make_vision_kwargs_if_available() -> dict[str, Any]:
    """检查本地视觉配置；可用就返回一个含 llm_client + llm_model (+ llm_prompt) 的 dict；不可用返回 {}。

    故意把 import 放在函数内：避免配置/视觉客户端在"根本没装 markitdown"时还在导。
    """
    if not MARKITDOWN_AVAILABLE:
        return {}
    try:
        from .config import VisionConfig
        from .vision_client import OpenAICompatVisionClient
    except Exception:
        return {}
    cfg = VisionConfig.load()
    if not cfg.is_valid():
        return {}
    try:
        client = OpenAICompatVisionClient(cfg)
    except Exception:
        return {}
    kwargs: dict[str, Any] = {"llm_client": client, "llm_model": cfg.model_name.strip()}
    if cfg.llm_prompt.strip():
        kwargs["llm_prompt"] = cfg.llm_prompt.strip()
    return kwargs


def _ensure_image_convert_kwargs():
    """在真正调用 convert 之前，保证 _IMAGE_CONVERT_KWARGS 是当前配置对应的最新版本。"""
    global _IMAGE_CONVERT_KWARGS
    _IMAGE_CONVERT_KWARGS = _make_vision_kwargs_if_available()


def reload_vision_client() -> dict[str, Any]:
    """UI 层保存完视觉配置后可调用：强制刷新内置的视觉 kwargs。

    返回当前生效的 kwargs（用于调试展示：有没有模型名）。
    """
    _ensure_image_convert_kwargs()
    # 为了让"已经创建过的 MarkItDown 单例"也能立刻使用新 client，
    # 我们直接丢弃旧单例，下次 convert 会根据最新配置重新创建
    # (MarkItDown 构造开销可以忽略；比起偷偷替换内部 ImageConverter 实例属性更不脆弱)
    global _md_instance
    _md_instance = None
    return dict(_IMAGE_CONVERT_KWARGS)


def _get_markitdown():
    """惰性获取 MarkItDown 单例实例。"""
    global _md_instance
    if _md_instance is None:
        if not MARKITDOWN_AVAILABLE:
            return None
        _md_instance = MarkItDown()
        # 启动时先按当前配置准备好 kwargs（避免第一次 convert 时才去读配置）
        _ensure_image_convert_kwargs()
    return _md_instance


def convert_file(file_path: str) -> tuple[bool, str]:
    """将单个文件转换为 Markdown 文本。

    参数:
        file_path: 待转换文件的绝对或相对路径

    返回:
        (True, markdown_text)  转换成功，第二项为 Markdown 文本
        (False, error_message) 转换失败，第二项为友好的中文错误提示
    """
    # 未安装 markitdown
    if not MARKITDOWN_AVAILABLE:
        return (False, "MarkItDown 未安装，请运行 pip install 'markitdown[all]'")

    # 文件不存在
    if not os.path.isfile(file_path):
        return (False, f"文件不存在: {file_path}")

    try:
        _ensure_image_convert_kwargs()
        md = _get_markitdown()
        if md is None:
            return (False, "MarkItDown 实例创建失败（请检查 markitdown 安装）")

        # 核心：在这里把视觉 client / 模型 作为 convert 的 per-call kwargs 传进去
        # markitdown 内部会按 converter key 路由；ImageConverter 会提取 llm_client / llm_model
        if _IMAGE_CONVERT_KWARGS:
            result = md.convert(file_path, **_IMAGE_CONVERT_KWARGS)
        else:
            result = md.convert(file_path)

        text = result.text_content
        # 兜底：图片在没配视觉模型时会输出空 md（仅 EXIF），这里加一个友好提示
        if not text.strip() and _is_image_ext(file_path) and not _IMAGE_CONVERT_KWARGS:
            text = (
                "<!-- MarkItDown 图片转换：未检测到视觉模型配置，本文件仅做占位。 -->\n"
                "<!-- 如需识别图片内容，请在主界面点击图片类的『⚙️ 配置视觉模型』按钮。 -->\n"
            )
        return (True, text)
    except PermissionError as e:
        return (False, f"无访问权限: {file_path}（{e}）")
    except Exception as e:
        return (False, f"转换失败: {e}")


def _is_image_ext(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext in {"jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp"}


def get_output_md_path(file_path: str) -> str:
    """返回与源文件同目录、同名但扩展名为 .md 的路径。

    使用 os.path.splitext 替换扩展名。
    """
    base, _ = os.path.splitext(file_path)
    return base + ".md"


def write_md_file(output_path: str, content: str) -> tuple[bool, str]:
    """以 UTF-8 编码将 Markdown 内容写入文件。

    参数:
        output_path: 输出 .md 文件路径
        content: 待写入的 Markdown 文本

    返回:
        (True, "")  写入成功
        (False, error_msg) 写入失败
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return (True, "")
    except PermissionError as e:
        return (False, f"写入失败（无权限）: {output_path}（{e}）")
    except Exception as e:
        return (False, f"写入失败: {e}")
