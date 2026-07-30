"""最小 OpenAI 兼容多模态客户端。

目的：
  不想强制用户安装整个 `openai` SDK 或 `httpx`，这里用 Python 标准库 `urllib.request`
  发 HTTP 请求，就能驱动绝大多数兼容 OpenAI Chat Completions 协议的多模态视觉模型
  （Azure / 智谱 / 通义 / 月之暗面 / OneAPI 聚合层…… 只要走 chat/completions 都能用）。

markitdown 的 ImageConverter._get_llm_description() 期待的 llm_client 接口是：
    client.chat.completions.create(model=..., messages=...) -> 返回对象上
        response.choices[0].message.content == 描述字符串
这里我们用最小鸭子类型（dataclass 加属性）模拟那个返回结构，不依赖任何第三方包。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import ssl
import urllib.error
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, BinaryIO, List, Optional

from .config import VisionConfig


# ------------------- 鸭子类型的响应对象（模仿 openai SDK 返回结构） -------------------
@dataclass
class _Message:
    content: str = ""


@dataclass
class _Choice:
    message: _Message = field(default_factory=_Message)


@dataclass
class _ChatCompletionsResponse:
    choices: List[_Choice] = field(default_factory=list)


# ------------------- 真正干活的 client 类 -----------------------------------------
class OpenAICompatVisionClient:
    """最小可用的 OpenAI Chat Completions 客户端（只实现多模态用到的子集）。"""

    def __init__(self, config: VisionConfig):
        if not config.is_valid():
            raise ValueError("视觉模型配置未完成，无法创建客户端（需要 base_url / api_key / model_name）")
        self.config = config
        # 保证 base_url 统一以 "/" 结尾，后面再接 "chat/completions"
        self._base = config.base_url.strip().rstrip("/") + "/"
        self._api_key = config.api_key.strip()

        # 宽松 SSL：企业内网自签证书常出问题，这里允许但记一笔
        self._ssl_ctx: Optional[ssl.SSLContext] = None
        try:
            self._ssl_ctx = ssl.create_default_context()
        except Exception:
            self._ssl_ctx = None

    # --- 对外暴露的属性（ImageConverter 里访问 client.chat.completions.create）---
    @property
    def chat(self):  # 为了属性链式访问
        return self

    @property
    def completions(self):
        return self

    def create(self, model: str, messages: list, **_kwargs: Any) -> _ChatCompletionsResponse:
        url = self._base + "chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0,          # 图片描述希望稳定，不要幻觉
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout, context=self._ssl_ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"视觉模型 HTTP {e.code}：{err_body or e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"视觉模型网络错误：{e.reason}（请检查 Base URL / 代理 / 证书）") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"视觉模型返回不是合法 JSON：{raw[:500]}") from e

        # 兼容多种返回：
        #   标准：{"choices":[{"message":{"content":"..."}}]}
        #   有些供应商：{"choices":[{"delta":{"content":"..."}}]} 流式拼接，这里只处理一次性返回
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"视觉模型返回 choices 为空：{raw[:500]}")
        first = choices[0]
        msg = first.get("message") or first.get("delta") or {}
        content = str(msg.get("content") or "").strip()
        if not content and "error" in data:
            err = data["error"]
            raise RuntimeError(f"视觉模型返回错误：{err}")
        if not content:
            raise RuntimeError(f"视觉模型未返回描述内容：{raw[:500]}")

        choice0 = _Choice(message=_Message(content=content))
        return _ChatCompletionsResponse(choices=[choice0])


# ------------------- 用一个真实 jpg/png 发一次"烟雾测试" -------------------------
def probe_vision_api(config: VisionConfig, sample_image_path: Optional[str] = None) -> str:
    """测试配置是否可用：用 1x1 小 PNG 发请求，模型正常返回非空字符串即认为 OK。

    返回：成功时返回 `连接成功，模型返回：xxxxx`；失败直接抛异常（让上层 QMessageBox 展示）。
    """
    import io, struct, zlib, os

    client = OpenAICompatVisionClient(config)

    if sample_image_path and os.path.isfile(sample_image_path):
        with open(sample_image_path, "rb") as f:
            img_bytes = f.read()
        ext = os.path.splitext(sample_image_path)[1].lower()
        if ext == ".png":
            mime = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".webp":
            mime = "image/webp"
        else:
            mime = "image/png"
    else:
        # 没有给样本就构造一个 1x1 全透明 PNG，保证能过 API 格式校验
        png_bytes_io = io.BytesIO()
        def chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1 RGBA
        raw = b"\x00" + bytes((0, 0, 0, 0))  # filter byte + RGBA(0,0,0,0)
        idat = zlib.compress(raw, 9)
        png_bytes_io.write(sig)
        png_bytes_io.write(chunk(b"IHDR", ihdr))
        png_bytes_io.write(chunk(b"IDAT", idat))
        png_bytes_io.write(chunk(b"IEND", b""))
        img_bytes = png_bytes_io.getvalue()
        mime = "image/png"

    base64_image = base64.b64encode(img_bytes).decode("utf-8")
    data_uri = f"data:{mime};base64,{base64_image}"

    prompt = config.llm_prompt.strip() or "用一句非常简短的话描述这张图片（20 字以内）。"
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }
    ]
    resp = client.chat.completions.create(model=config.model_name.strip(), messages=messages)
    text = resp.choices[0].message.content.strip().replace("\n", " ")
    if len(text) > 60:
        text = text[:60] + "……"
    return f"连接成功 ✅  模型返回示例：{text}"


__all__ = ["OpenAICompatVisionClient", "probe_vision_api", "VisionConfig"]
