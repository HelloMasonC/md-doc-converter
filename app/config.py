"""视觉（多模态）模型调用的本地配置读写。

约定：
  * 配置文件放在用户主目录下的 `~/.markitdown_tool/vision_config.json`，
    避免和项目仓库混在一起，也天然不会被 Git 跟踪；
  * 字段：base_url / api_key / model_name / llm_prompt（选填，用于自定义图片描述的提示词）
  * 允许通过 MarkItDown(llm_client=..., llm_model=...) 方式注入到 markitdown 的 convert
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Optional


CONFIG_DIRNAME = ".markitdown_tool"
CONFIG_FILENAME = "vision_config.json"


def get_config_path() -> str:
    """返回视觉配置 JSON 文件的完整路径（默认：~/.markitdown_tool/vision_config.json）。

    作为模块级函数 + VisionConfig 静态方法，同步提供两种调用方式。
    """
    home = os.path.expanduser("~")
    return os.path.join(home, CONFIG_DIRNAME, CONFIG_FILENAME)


@dataclass
class VisionConfig:
    base_url: str = ""                 # 例如："https://api.openai.com/v1" 或任意 OpenAI 兼容端点
    api_key: str = ""                  # 密钥（明文保存到本地文件；如需更强加密用户可自行改造）
    model_name: str = ""               # 模型名，例如："gpt-4o-mini" / "qwen-vl-plus" 等
    llm_prompt: str = ""               # 图片描述提示词，留空则用 markitdown 默认
    # 兼容字段：部分供应商要求不同的 URL 路径，但我们统一走 "chat/completions"
    timeout: int = 60

    # --- 便捷方法 ---------------------------------------------------------
    @staticmethod
    def get_config_path() -> str:
        """返回视觉配置 JSON 文件的完整路径（~/.markitdown_tool/vision_config.json）。"""
        return get_config_path()

    def is_valid(self) -> bool:
        """三项核心信息齐全才算"已配置"。"""
        return bool(self.base_url.strip() and self.api_key.strip() and self.model_name.strip())

    def masked_api_key(self) -> str:
        key = (self.api_key or "").strip()
        if len(key) <= 8:
            return "*" * len(key)
        return key[:4] + "*" * (len(key) - 8) + key[-4:]

    # --- 持久化 -----------------------------------------------------------
    def save(self) -> str:
        path = get_config_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        # 收紧权限（仅当前用户可读写，尽力而为）
        try:
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(path, 0x80)  # FILE_ATTRIBUTE_NORMAL
            else:
                os.chmod(path, 0o600)
        except Exception:
            pass
        return path

    @classmethod
    def load(cls) -> "VisionConfig":
        path = get_config_path()
        if not os.path.isfile(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            # 配置文件坏了就返回默认（不要让整个程序起不来）
            return cls()
        return cls(
            base_url=str(data.get("base_url", "") or ""),
            api_key=str(data.get("api_key", "") or ""),
            model_name=str(data.get("model_name", "") or ""),
            llm_prompt=str(data.get("llm_prompt", "") or ""),
            timeout=int(data.get("timeout", 60) or 60),
        )

    @classmethod
    def clear(cls) -> str:
        """删除配置文件（返回删除的路径或提示）。"""
        path = get_config_path()
        if os.path.isfile(path):
            try:
                os.remove(path)
                return f"已删除配置文件：{path}"
            except Exception as e:
                return f"删除配置文件失败：{e}"
        return "未检测到本地配置文件，无需删除"


def current_vision_config() -> VisionConfig:
    """给上层模块用的快捷函数。"""
    return VisionConfig.load()
