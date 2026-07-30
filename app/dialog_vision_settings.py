"""视觉模型配置对话框。

字段：
  * Base URL（必填，末尾 /v1 或不带都能接受）
  * API Key（必填，可切换显示/隐藏）
  * 模型名称（必填）
  * 自定义图片描述提示词（选填，留空用 markitdown 默认）
  * 超时秒数（选填，默认 60）

按钮：
  * 测试连接：用 1x1 PNG 发一次真实请求
  * 保存：写入 ~/.markitdown_tool/vision_config.json，并通知主窗口 reload
  * 取消：什么都不做
"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QDialogButtonBox,
    QPushButton, QMessageBox, QSpinBox, QPlainTextEdit, QHBoxLayout, QWidget,
)

from .config import VisionConfig
from .vision_client import probe_vision_api


class VisionSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️  配置多模态视觉模型（图片识别）")
        self.resize(560, 520)
        self._cfg: VisionConfig = VisionConfig.load()
        self._build_ui()
        self._load_to_ui(self._cfg)

    # --------------------------------------------------------------- UI ---
    def _build_ui(self):
        root = QVBoxLayout(self)
        info = QLabel(
            "说明：本工具通过 <b>OpenAI 兼容的 Chat Completions 协议</b>调用多模态视觉模型。<br>"
            "支持：Azure OpenAI / 通义 / 智谱 GLM / 月之暗面 / 本地 Ollama（开 API 端口） / OneAPI 等任何兼容协议的服务。<br>"
            "配置保存在 <code>~/.markitdown_tool/vision_config.json</code>（独立于项目仓库，不会被 Git 跟踪）。"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#444; padding:4px 0 10px 0;")
        root.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.ed_base = QLineEdit()
        self.ed_base.setPlaceholderText("例如：https://api.openai.com/v1  或  https://dashscope.aliyuncs.com/compatible-mode/v1")
        form.addRow("Base URL <font color=red>*</font>", self.ed_base)

        # API Key 行 + 显示/隐藏按钮
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        self.ed_key = QLineEdit()
        self.ed_key.setEchoMode(QLineEdit.Password)
        self.ed_key.setPlaceholderText("sk-xxxxxxxxxxxxxxxxxx")
        self.btn_toggle_key = QPushButton("👁 显示")
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.setFixedWidth(78)
        self.btn_toggle_key.toggled.connect(self._toggle_key_visible)
        key_row.addWidget(self.ed_key, 1)
        key_row.addWidget(self.btn_toggle_key)
        key_wrap = QWidget()
        key_wrap.setLayout(key_row)
        form.addRow("API Key <font color=red>*</font>", key_wrap)

        self.ed_model = QLineEdit()
        self.ed_model.setPlaceholderText("例如：gpt-4o-mini、qwen-vl-plus、glm-4v-flash 等")
        form.addRow("模型名称 <font color=red>*</font>", self.ed_model)

        self.sp_timeout = QSpinBox()
        self.sp_timeout.setRange(3, 600)
        self.sp_timeout.setSuffix(" 秒")
        self.sp_timeout.setValue(60)
        form.addRow("调用超时", self.sp_timeout)

        self.ed_prompt = QPlainTextEdit()
        self.ed_prompt.setPlaceholderText(
            "选填，留空则使用 markitdown 默认提示词："
            "Write a detailed caption for this image.\n"
            "中文推荐：『请用中文详细描述这张图片的内容，包括主体、场景、文字、颜色、布局等。』"
        )
        self.ed_prompt.setFixedHeight(110)
        form.addRow("图片描述提示词", self.ed_prompt)

        root.addLayout(form)

        # 测试连接按钮
        test_row = QHBoxLayout()
        self.btn_test = QPushButton("🧪 测试连接（用 1x1 小图发一次真实请求）")
        self.btn_test.clicked.connect(self._on_test)
        test_row.addWidget(self.btn_test)
        test_row.addStretch(1)
        root.addLayout(test_row)

        # 保存 / 取消
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("💾 保存配置")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self._on_save)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    # ----------------------------------------------------------- 行为 ---
    def _toggle_key_visible(self, checked: bool):
        if checked:
            self.ed_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_key.setText("🙈 隐藏")
        else:
            self.ed_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_key.setText("👁 显示")

    def _load_to_ui(self, cfg: VisionConfig):
        self.ed_base.setText(cfg.base_url)
        self.ed_key.setText(cfg.api_key)
        self.ed_model.setText(cfg.model_name)
        self.ed_prompt.setPlainText(cfg.llm_prompt)
        self.sp_timeout.setValue(max(3, int(cfg.timeout or 60)))

    def _collect_from_ui(self) -> VisionConfig:
        return VisionConfig(
            base_url=self.ed_base.text().strip(),
            api_key=self.ed_key.text().strip(),
            model_name=self.ed_model.text().strip(),
            llm_prompt=self.ed_prompt.toPlainText().strip(),
            timeout=max(3, int(self.sp_timeout.value())),
        )

    def _on_test(self):
        cfg = self._collect_from_ui()
        if not cfg.is_valid():
            QMessageBox.warning(self, "参数不完整", "请先完整填写 Base URL / API Key / 模型名称 三项必填字段。")
            return
        self.btn_test.setEnabled(False)
        self.btn_test.setText("请求中，请稍候……")
        QApplication_instance = None
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication_instance = QApplication.instance()
            if QApplication_instance:
                QApplication_instance.processEvents()
        except Exception:
            pass
        try:
            msg = probe_vision_api(cfg)
            QMessageBox.information(self, "连接成功", msg)
        except Exception as e:
            QMessageBox.critical(self, "连接失败", f"测试请求失败：\n{e}")
        finally:
            self.btn_test.setEnabled(True)
            self.btn_test.setText("🧪 测试连接（用 1x1 小图发一次真实请求）")

    def _on_save(self):
        cfg = self._collect_from_ui()
        if not cfg.is_valid():
            ret = QMessageBox.question(
                self,
                "必填项未填完",
                "当前 Base URL / API Key / 模型名称 未全部填写，保存后图片识别仍会处于『未启用』状态。\n"
                "确定要保存（作为部分配置留档）吗？",
            )
            if ret != QMessageBox.Yes:
                return
        try:
            path = cfg.save()
            self._cfg = cfg
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"写入配置文件失败：{e}")
            return
        self.accept()
        QMessageBox.information(
            self,
            "已保存 ✅",
            f"视觉配置已保存到：\n{path}\n\n"
            f"当前生效的模型：{cfg.model_name or '（未填，图片仍未启用）'}\n"
            f"密钥显示：{cfg.masked_api_key()}",
        )

    def saved_config(self) -> VisionConfig:
        return self._cfg
