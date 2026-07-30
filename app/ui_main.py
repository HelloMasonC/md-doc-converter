"""主窗口 UI 模块。

实现基于 PyQt5 的 MD文档转换工具主窗口，包含：
- 顶部文件选择模式区（目录全部文件 / 目录指定类型 / 指定文件）
- 中部文件列表表格
- 底部进度条与操作按钮
- 状态栏统计信息

本模块仅实现 UI 与文件选择逻辑；转换流程串联由后续任务实现。
"""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QGridLayout,
    QScrollArea,
    QFrame,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QProgressBar,
    QMessageBox,
    QHeaderView,
    QAbstractItemView,
)

from PyQt5.QtGui import QBrush
from app import converter
from app.worker import ConvertWorker


# 支持的文件类型（按类别分组，每组 [(显示名, 扩展名(小写无点)) ...]）
# 注意：分类名不要加 emoji，QGroupBox 标题栏会因宽度估算错误被截断
SUPPORTED_EXT_CATEGORIES = {
    "表格文件": [
        ("Excel 新格式 (*.xlsx)", "xlsx"),
        ("Excel 旧格式 (*.xls)", "xls"),
        ("逗号分隔 (*.csv)", "csv"),
        ("制表分隔 (*.tsv)", "tsv"),
        ("OpenOffice 表格 (*.ods)", "ods"),
    ],
    "文档文件": [
        ("Word 新格式 (*.docx)", "docx"),
        ("Word 旧格式 (*.doc)", "doc"),
        ("PDF 文档 (*.pdf)", "pdf"),
        ("网页 HTML (*.html)", "html"),
        ("网页 HTM (*.htm)", "htm"),
        ("纯文本 (*.txt)", "txt"),
        ("XML 文档 (*.xml)", "xml"),
        ("Markdown (*.md)", "md"),
        ("RTF 文档 (*.rtf)", "rtf"),
        ("OpenOffice 文档 (*.odt)", "odt"),
    ],
    "演示文稿": [
        ("PPT 新格式 (*.pptx)", "pptx"),
        ("PPT 旧格式 (*.ppt)", "ppt"),
        ("OpenOffice 演示 (*.odp)", "odp"),
    ],
    "音频文件": [
        ("MP3 音频 (*.mp3)", "mp3"),
        ("WAV 音频 (*.wav)", "wav"),
        ("FLAC 音频 (*.flac)", "flac"),
        ("M4A 音频 (*.m4a)", "m4a"),
        ("OGG 音频 (*.ogg)", "ogg"),
    ],
    "图片文件": [
        ("JPG 图片 (*.jpg)", "jpg"),
        ("JPEG 图片 (*.jpeg)", "jpeg"),
        ("PNG 图片 (*.png)", "png"),
        ("GIF 图片 (*.gif)", "gif"),
        ("BMP 图片 (*.bmp)", "bmp"),
        ("TIFF 图片 (*.tiff)", "tiff"),
        ("WebP 图片 (*.webp)", "webp"),
    ],
    "其他常见文件": [
        ("JSON (*.json)", "json"),
        ("YAML (*.yaml)", "yaml"),
        ("YML (*.yml)", "yml"),
        ("ZIP 压缩 (*.zip)", "zip"),
        ("RAR 压缩 (*.rar)", "rar"),
        ("7z 压缩 (*.7z)", "7z"),
        ("INI 配置 (*.ini)", "ini"),
        ("TOML 配置 (*.toml)", "toml"),
        ("日志文件 (*.log)", "log"),
        ("邮件 (*.eml)", "eml"),
    ],
}

# 「常用」预设对应的扩展名集合（启动时默认勾选 & 点击「✅ 常用」按钮恢复的那一套）
# 选择原则：日常办公 80% 场景会碰到的 + 现在已经零配置支持的格式
# 说明（非常重要）：
#   * 音频（mp3/wav/m4a 等）：已通过 imageio-ffmpeg 内置静态 ffmpeg，零配置支持
#   * 图片（jpg/jpeg/png 等）：markitdown 的 ImageConverter 在没有多模态 LLM 客户端时
#     只会吐出 EXIF 元数据（尺寸/日期/GPS 等），几乎等于空内容；需要配置视觉多模态模型
#     才会真的"看懂图片"。所以图片默认不勾选，有特殊需求时用户自己手动勾即可
COMMONLY_USED_EXTS = {
    # 表格（5/5 全勾）
    "xlsx", "xls", "csv", "tsv", "ods",
    # 文档（7/10：md 去掉——本工具输出就是 .md，再"把 md 转 md"属冗余）
    "docx", "doc", "pdf", "html", "htm", "txt", "xml",
    # 演示文稿（常用 2 个）
    "pptx", "ppt",
    # 音频（ffmpeg 已内置，直接勾上最常见的 4 个）
    "mp3", "wav", "m4a", "flac",
    # 其他常见
    "json", "yaml", "yml", "zip", "log",
}


def format_size(num_bytes: int) -> str:
    """将字节数格式化为人类可读字符串。

    例如：1024 -> "1.00 KB"，1572864 -> "1.50 MB"。
    """
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "未知"
    if size < 0:
        return "未知"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


class MainWindow(QMainWindow):
    """MD文档转换工具主窗口。"""

    def __init__(self):
        super().__init__()

        # 实例变量初始化
        self.file_list: list[str] = []  # 完整路径列表
        self.success_count = 0
        self.fail_count = 0
        self.worker = None  # 转换线程引用，避免被 GC 过早回收

        # 窗口基本设置
        self.setWindowTitle("MD文档转换工具")
        self.resize(900, 600)
        self._center_window()

        # 构建 UI
        self._build_ui()

        # 初始控件启用状态
        self._update_mode_controls()

        # 初始状态栏
        self._refresh_status_bar()

    # ------------------------------------------------------------------
    # 窗口辅助
    # ------------------------------------------------------------------
    def _center_window(self):
        """将窗口居中显示到屏幕中央。"""
        screen = self.screen().availableGeometry() if hasattr(self, "screen") else None
        if screen is None:
            # 兼容旧版本 PyQt5
            from PyQt5.QtWidgets import QDesktopWidget
            screen = QDesktopWidget().availableGeometry()
        size = self.geometry()
        self.move(
            (screen.width() - size.width()) // 2,
            (screen.height() - size.height()) // 2,
        )

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        """构建整体 UI 布局。"""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.setSpacing(8)

        # 顶部模式选择区
        root_layout.addWidget(self._build_mode_group())

        # 中部文件列表
        root_layout.addWidget(self._build_file_table(), 1)

        # 底部进度与操作区
        root_layout.addWidget(self._build_bottom_group())

    def _build_mode_group(self) -> QGroupBox:
        """构建顶部文件选择模式区。"""
        group = QGroupBox("文件选择模式")
        layout = QVBoxLayout(group)
        layout.setSpacing(6)

        # 第一行：单选按钮
        radio_row = QHBoxLayout()
        self.rb_dir_all = QRadioButton("目录全部文件")
        self.rb_dir_filtered = QRadioButton("目录指定类型")
        self.rb_files = QRadioButton("指定文件")

        # 默认选中「目录全部文件」
        self.rb_dir_all.setChecked(True)

        # 放入 QButtonGroup 实现互斥
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_dir_all)
        self.mode_group.addButton(self.rb_dir_filtered)
        self.mode_group.addButton(self.rb_files)

        radio_row.addWidget(self.rb_dir_all)
        radio_row.addWidget(self.rb_dir_filtered)
        radio_row.addWidget(self.rb_files)
        radio_row.addStretch(1)
        layout.addLayout(radio_row)

        # ---------- 第二行：文件类型面板（可折叠） ----------
        # 2.1 折叠控制条（全选/反选/常用 + 展开/收起切换 + 自定义追加输入）
        type_toolbar = QHBoxLayout()
        self.btn_type_common = QPushButton("✅ 常用")
        self.btn_type_common.setToolTip("一键勾选最常用的 Office + PDF + 文本 + 演示格式")
        self.btn_type_select_all = QPushButton("全选")
        self.btn_type_select_none = QPushButton("清空")
        self.btn_type_toggle = QPushButton("▼ 展开文件类型清单")
        self.btn_type_toggle.setCheckable(True)
        self.btn_type_toggle.setChecked(False)  # 默认收起

        self.extra_ext_label = QLabel("自定义追加(逗号分隔):")
        self.extra_ext_edit = QLineEdit()
        self.extra_ext_edit.setPlaceholderText("如: epub, md, 7z  （可留空）")

        type_toolbar.addWidget(self.btn_type_common)
        type_toolbar.addWidget(self.btn_type_select_all)
        type_toolbar.addWidget(self.btn_type_select_none)
        type_toolbar.addSpacing(8)
        type_toolbar.addWidget(self.btn_type_toggle)
        type_toolbar.addSpacing(12)
        type_toolbar.addWidget(self.extra_ext_label)
        type_toolbar.addWidget(self.extra_ext_edit, 1)
        layout.addLayout(type_toolbar)

        # 2.2 折叠面板主体（分类复选框组 + 滚动）
        self.type_panel_container = QWidget()
        type_panel_layout = QVBoxLayout(self.type_panel_container)
        type_panel_layout.setContentsMargins(0, 4, 0, 0)
        type_panel_layout.setSpacing(6)

        # 存放所有 ext -> QCheckBox，方便读值
        self.ext_checkboxes: dict[str, QCheckBox] = {}
        # 存放每一组对应的组标题（用于整组全选快速定位）
        self._cat_group_checkboxes: list[list[QCheckBox]] = []

        for cat_name, items in SUPPORTED_EXT_CATEGORIES.items():
            is_image_cat = (cat_name == "图片文件")
            cat_box = QGroupBox("")  # 标题在 _refresh_image_box_state 里统一设置（便于切换启用/未启用）
            self._style_cat_box(cat_box, is_image_cat, enabled=False)
            cat_grid = QGridLayout(cat_box)
            cat_grid.setHorizontalSpacing(14)   # 列间距略放大，避免复选框文字紧贴右侧被截断
            cat_grid.setVerticalSpacing(4)
            cat_grid.setContentsMargins(12, 10, 12, 10)
            cat_checkbox_list: list[QCheckBox] = []

            # 图片类：顶部先放一条配置工具栏 + 状态标签
            if is_image_cat:
                vision_bar = QHBoxLayout()
                self.btn_open_vision = QPushButton("⚙️  配置视觉模型")
                self.btn_open_vision.setToolTip("填 Base URL / API Key / 模型名，保存后图片识别立刻生效")
                self.btn_open_vision.clicked.connect(self._open_vision_settings)
                self.btn_clear_vision = QPushButton("🗑 清除本地配置")
                self.btn_clear_vision.setToolTip("删除 ~/.markitdown_tool/vision_config.json，图片还原『未启用』状态")
                self.btn_clear_vision.clicked.connect(self._clear_vision_config)
                self.lbl_vision_state = QLabel()
                self.lbl_vision_state.setWordWrap(True)
                vision_bar.addWidget(self.btn_open_vision)
                vision_bar.addWidget(self.btn_clear_vision)
                vision_bar.addSpacing(10)
                vision_bar.addWidget(self.lbl_vision_state, 1)
                r = cat_grid.rowCount()
                cat_grid.addLayout(vision_bar, r, 0, 1, 3)

            # 每行 3 个复选框（4 列太挤，部分长文本（如 OpenOffice 演示(*.odp)）末尾会被切）
            COLS = 3
            row_start = cat_grid.rowCount()
            for idx, (label, ext) in enumerate(items):
                r, c = divmod(idx, COLS)
                cb = QCheckBox(label)
                if ext in COMMONLY_USED_EXTS:
                    cb.setChecked(True)
                cat_grid.addWidget(cb, row_start + r, c)
                self.ext_checkboxes[ext] = cb
                cat_checkbox_list.append(cb)

            # 图片类：原来的橙色说明文案保留（放在复选框最后一行后面）
            if is_image_cat:
                self.lbl_image_note = QLabel()
                self.lbl_image_note.setWordWrap(True)
                r_next = row_start + (len(items) + COLS - 1) // COLS
                cat_grid.addWidget(self.lbl_image_note, r_next, 0, 1, COLS)
                # 存引用，刷新状态时要改标题 / 颜色 / 边框
                self._image_cat_box = cat_box
            else:
                cat_box.setTitle(cat_name)

            self._cat_group_checkboxes.append(cat_checkbox_list)
            type_panel_layout.addWidget(cat_box)

        # 图片类"已启用 / 未启用"标题、颜色、说明文案 一次刷新到位
        self._refresh_image_box_state()

        # 用 ScrollArea 包住（内容多时滚动）
        self.type_scroll = QScrollArea()
        self.type_scroll.setWidget(self.type_panel_container)
        self.type_scroll.setWidgetResizable(True)
        self.type_scroll.setFrameShape(QFrame.NoFrame)
        self.type_scroll.setMaximumHeight(280)  # 展开时最高 280px，防止撑爆窗口
        layout.addWidget(self.type_scroll)
        self.type_panel_container.setVisible(False)  # 默认收起

        # 2.3 状态提示（汇总勾选了多少种）
        self.type_summary = QLabel("当前已勾选：0 种（可点击「✅ 常用」快速恢复默认）")
        self.type_summary.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.type_summary)

        # ---------- 第三行：选择目录 / 文件按钮 ----------
        action_row = QHBoxLayout()
        self.btn_select_dir = QPushButton("📁 选择目录")
        self.btn_select_files = QPushButton("📄 选择文件")
        action_row.addStretch(1)
        action_row.addWidget(self.btn_select_dir)
        action_row.addWidget(self.btn_select_files)
        layout.addLayout(action_row)

        # ---------- 信号连接 ----------
        self.rb_dir_all.toggled.connect(self._update_mode_controls)
        self.rb_dir_filtered.toggled.connect(self._update_mode_controls)
        self.rb_files.toggled.connect(self._update_mode_controls)

        self.btn_select_dir.clicked.connect(self._on_select_dir)
        self.btn_select_files.clicked.connect(self._on_select_files)

        self.btn_type_toggle.toggled.connect(self._toggle_type_panel)
        self.btn_type_select_all.clicked.connect(lambda: self._set_all_checkbox(True))
        self.btn_type_select_none.clicked.connect(lambda: self._set_all_checkbox(False))
        self.btn_type_common.clicked.connect(self._apply_common_preset)
        for cb in self.ext_checkboxes.values():
            cb.stateChanged.connect(self._refresh_type_summary)

        # 初始汇总 & 控件状态
        self._refresh_type_summary()
        return group

    # ------------------------------------------------------------------
    # 文件类型面板辅助方法
    # ------------------------------------------------------------------
    def _style_cat_box(self, cat_box, is_image_cat: bool, enabled: bool):
        """给 QGroupBox 设置样式：图片类根据 enabled 切换为『未启用（橙框）』或『已启用（绿框）』。"""
        if is_image_cat:
            if enabled:
                # 已启用：绿色风格
                cat_box.setStyleSheet(
                    "QGroupBox { padding-top: 8px; margin-top: 6px;"
                    "           border: 1px solid #2e9e5b; border-radius: 4px; }"
                    "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px 0 0;"
                    "                   color: #1e7a43; font-weight: 600; }"
                )
            else:
                # 未启用：橙色虚线警示
                cat_box.setStyleSheet(
                    "QGroupBox { padding-top: 8px; margin-top: 6px;"
                    "           border: 1px dashed #c97b3a; border-radius: 4px; }"
                    "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px 0 0;"
                    "                   color: #b15b1a; font-weight: 600; }"
                )
        else:
            cat_box.setStyleSheet(
                "QGroupBox { padding-top: 8px; margin-top: 6px; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px 0 0; }"
            )

    def _refresh_image_box_state(self):
        """根据本地视觉配置文件，刷新图片分类的标题/状态/颜色/说明文案。

        在 MainWindow 初始化、保存完配置、清除完配置后调用一次即可。
        """
        from .config import VisionConfig
        cfg = VisionConfig.load()
        enabled = cfg.is_valid()

        if hasattr(self, "_image_cat_box") and self._image_cat_box is not None:
            if enabled:
                self._image_cat_box.setTitle(
                    f"图片文件（已启用 ✅  模型：{cfg.model_name}）"
                )
            else:
                self._image_cat_box.setTitle(
                    "图片文件（未启用，需配置多模态视觉模型，点【配置视觉模型】）"
                )
            self._style_cat_box(self._image_cat_box, is_image_cat=True, enabled=enabled)

        if hasattr(self, "lbl_vision_state"):
            if enabled:
                self.lbl_vision_state.setText(
                    f"<b style='color:#1e7a43'>✅ 已启用</b> · "
                    f"Endpoint: {cfg.base_url.rstrip('/')} · "
                    f"模型: {cfg.model_name} · "
                    f"Key: {cfg.masked_api_key()}"
                )
                self.lbl_vision_state.setStyleSheet("color:#1e7a43;")
            else:
                # 局部填了一部分（比如只填了 base_url）也提示用户
                partial = any([cfg.base_url, cfg.api_key, cfg.model_name])
                if partial:
                    self.lbl_vision_state.setText(
                        "<b style='color:#b15b1a'>⚠️ 未完全启用</b>：有部分配置缺失，请点 ⚙️ 补全 Base URL / API Key / 模型名三项。"
                    )
                else:
                    self.lbl_vision_state.setText(
                        "<b style='color:#8a5a2a'>🔒 未启用</b>：图片仅提取 EXIF 元数据；要识别图片内容请配置多模态视觉模型。"
                    )
                self.lbl_vision_state.setStyleSheet("")

        if hasattr(self, "lbl_image_note"):
            if enabled:
                note = (
                    "已通过 OpenAI 兼容协议连接多模态视觉模型，勾选图片后会真的调用 API 理解图片内容（消耗接口额度）。\n"
                    f"想换模型 / 换 Key：点【配置视觉模型】改完保存即可即时生效。"
                )
                self.lbl_image_note.setStyleSheet(
                    "color:#1e7a43; font-size: 11px; padding: 4px 2px 0 2px;"
                )
            else:
                note = (
                    "说明：当前未配置 Azure/OpenAI 等多模态视觉模型。勾选图片仅会提取 EXIF 元数据（尺寸/时间/GPS 等），"
                    "不会真正理解图片内容；点【配置视觉模型】填完 Base URL / API Key / 模型名 三项，保存后即刻启用。"
                )
                self.lbl_image_note.setStyleSheet(
                    "color: #8a5a2a; font-size: 11px; padding: 4px 2px 0 2px;"
                )
            self.lbl_image_note.setText(note)

    def _open_vision_settings(self):
        from .dialog_vision_settings import VisionSettingsDialog
        from app import converter as _converter
        dlg = VisionSettingsDialog(self)
        if dlg.exec_() != dlg.Accepted:
            return
        # 保存后：刷新状态文字 + 强制重建 MarkItDown 单例 & 重新加载视觉 kwargs
        self._refresh_image_box_state()
        try:
            kwargs = _converter.reload_vision_client()
            model = kwargs.get("llm_model") or "(空)"
        except Exception as e:
            model = f"（刷新失败：{e}）"
        # 汇总已勾选的类型，顺便刷新下底部汇总文案
        self._refresh_type_summary()
        QMessageBox.information(
            self,
            "配置已更新 ✅",
            f"视觉模型已切换为：{model}\n\n"
            "下次转换图片时会自动用新的配置调用接口。",
        )

    def _clear_vision_config(self):
        from .config import VisionConfig
        from app import converter as _converter
        ret = QMessageBox.question(
            self,
            "清除视觉配置？",
            "将删除本地文件 ~/.markitdown_tool/vision_config.json\n"
            "删除后图片识别还原为『未启用』状态。确定继续？",
        )
        if ret != QMessageBox.Yes:
            return
        msg = VisionConfig.clear()
        self._refresh_image_box_state()
        try:
            _converter.reload_vision_client()
        except Exception:
            pass
        QMessageBox.information(self, "已清除", msg)

    def _toggle_type_panel(self, expanded: bool):
        """展开/收起 复选框面板，同步切换按钮文本的三角符号。"""
        if expanded:
            self.btn_type_toggle.setText("▲ 收起文件类型清单")
            self.type_panel_container.setVisible(True)
        else:
            self.btn_type_toggle.setText("▼ 展开文件类型清单")
            self.type_panel_container.setVisible(False)

    def _set_all_checkbox(self, checked: bool):
        for cb in self.ext_checkboxes.values():
            cb.setChecked(checked)

    def _apply_common_preset(self):
        for ext, cb in self.ext_checkboxes.items():
            cb.setChecked(ext in COMMONLY_USED_EXTS)

    def _refresh_type_summary(self):
        count = sum(1 for cb in self.ext_checkboxes.values() if cb.isChecked())
        extra_text = self.extra_ext_edit.text().strip()
        extra_hint = ""
        if extra_text:
            extra_list = [p.strip().lstrip(".").lower() for p in extra_text.split(",") if p.strip()]
            if extra_list:
                extra_hint = f" + 自定义 {len(extra_list)} 种"
        self.type_summary.setText(f"当前已勾选：{count} 种{extra_hint}（可点击「✅ 常用」快速恢复默认）")

    def _collect_selected_exts(self) -> list[str]:
        """从复选框 + 自定义追加框里合并出最终的扩展名列表（去重、小写、无点前缀）。"""
        exts: list[str] = []
        seen: set[str] = set()

        for ext, cb in self.ext_checkboxes.items():
            if cb.isChecked() and ext not in seen:
                exts.append(ext)
                seen.add(ext)

        # 自定义追加部分
        raw_extra = self.extra_ext_edit.text().strip()
        if raw_extra:
            for part in raw_extra.split(","):
                ext = part.strip().lower()
                if ext.startswith("."):
                    ext = ext[1:]
                if ext and ext not in seen:
                    exts.append(ext)
                    seen.add(ext)
        return exts

    def _build_file_table(self) -> QWidget:
        """构建中部文件列表表格容器。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(["文件名", "路径", "大小", "状态"])
        # 允许多选以便「移除选中」
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # 列宽自适应内容
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        # 允许用户手动调整
        self.file_table.horizontalHeader().setStretchLastSection(False)
        self.file_table.horizontalHeader().setSectionsMovable(False)
        # 整行选中、禁止编辑
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.verticalHeader().setVisible(False)

        layout.addWidget(self.file_table)
        return container

    def _build_bottom_group(self) -> QWidget:
        """构建底部进度条与操作按钮区。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self.btn_convert = QPushButton("开始转换")
        self.btn_clear = QPushButton("清空列表")
        self.btn_remove = QPushButton("移除选中")
        self.btn_cancel = QPushButton("取消")
        # 取消按钮默认禁用
        self.btn_cancel.setEnabled(False)

        btn_row.addWidget(self.btn_convert)
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(self.btn_remove)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        # 信号连接
        self.btn_convert.clicked.connect(self._on_convert)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_remove.clicked.connect(self._on_remove_selected)
        self.btn_cancel.clicked.connect(self._on_cancel)

        return container

    # ------------------------------------------------------------------
    # 模式切换
    # ------------------------------------------------------------------
    def _update_mode_controls(self):
        """根据当前选中的模式按钮更新控件启用状态。"""
        if self.rb_dir_all.isChecked():
            # 目录全部文件：启用「选择目录」，禁用「选择文件」与类型面板控件
            self.btn_select_dir.setEnabled(True)
            self.btn_select_files.setEnabled(False)
            self._set_type_panel_enabled(False)
        elif self.rb_dir_filtered.isChecked():
            # 目录指定类型：启用「选择目录」与类型面板，禁用「选择文件」
            self.btn_select_dir.setEnabled(True)
            self.btn_select_files.setEnabled(False)
            self._set_type_panel_enabled(True)
        elif self.rb_files.isChecked():
            # 指定文件：启用「选择文件」，禁用「选择目录」与类型面板控件
            self.btn_select_dir.setEnabled(False)
            self.btn_select_files.setEnabled(True)
            self._set_type_panel_enabled(False)

    def _set_type_panel_enabled(self, enabled: bool):
        """批量启用/禁用 文件类型面板上的全部控件（工具栏、复选框、自定义输入、展开按钮、汇总提示）。"""
        self.btn_type_common.setEnabled(enabled)
        self.btn_type_select_all.setEnabled(enabled)
        self.btn_type_select_none.setEnabled(enabled)
        self.btn_type_toggle.setEnabled(enabled)
        self.extra_ext_edit.setEnabled(enabled)
        for cb in self.ext_checkboxes.values():
            cb.setEnabled(enabled)
        # 提示标签颜色灰掉更直观
        if enabled:
            self.type_summary.setStyleSheet("color: #666; font-size: 12px;")
        else:
            self.type_summary.setStyleSheet("color: #aaa; font-size: 12px;")

    def _on_select_dir(self):
        """「选择目录」按钮统一入口，依据当前模式分发。"""
        if self.rb_dir_filtered.isChecked():
            self._on_select_dir_filtered()
        else:
            self._on_select_dir_all()

    # ------------------------------------------------------------------
    # 文件选择逻辑（Task 5）
    # ------------------------------------------------------------------
    def _on_select_dir_all(self):
        """选择目录，扫描该目录下所有文件（不递归子目录）。"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择目录")
        if not dir_path:
            return
        try:
            entries = os.listdir(dir_path)
        except PermissionError as e:
            QMessageBox.warning(self, "无法访问目录", f"无访问权限: {dir_path}\n{e}")
            return
        except Exception as e:
            QMessageBox.warning(self, "读取目录失败", str(e))
            return

        file_paths = []
        for name in entries:
            full = os.path.join(dir_path, name)
            if os.path.isfile(full):
                file_paths.append(full)

        self._add_files(file_paths)

    def _on_select_dir_filtered(self):
        """选择目录，扫描该目录下匹配扩展名的文件。"""
        # 从复选框 + 自定义追加框里收集扩展名
        exts = self._collect_selected_exts()

        if not exts:
            QMessageBox.warning(
                self,
                "未勾选文件类型",
                "请先在文件类型清单中勾选至少一种格式，\n"
                "也可以直接切换到「目录全部文件」模式。",
            )
            return

        dir_path = QFileDialog.getExistingDirectory(self, "选择目录")
        if not dir_path:
            return
        try:
            entries = os.listdir(dir_path)
        except PermissionError as e:
            QMessageBox.warning(self, "无法访问目录", f"无访问权限: {dir_path}\n{e}")
            return
        except Exception as e:
            QMessageBox.warning(self, "读取目录失败", str(e))
            return

        ext_set = set(exts)
        file_paths = []
        for name in entries:
            full = os.path.join(dir_path, name)
            if not os.path.isfile(full):
                continue
            # 取扩展名并去掉点号前缀，转小写比较
            _, ext = os.path.splitext(name)
            ext = ext.lower()
            if ext.startswith("."):
                ext = ext[1:]
            if ext in ext_set:
                file_paths.append(full)

        self._add_files(file_paths)

    def _on_select_files(self):
        """多文件选择对话框。"""
        file_paths, _ = QFileDialog.getOpenFileNames(self, "选择文件")
        if not file_paths:
            return
        self._add_files(file_paths)

    # ------------------------------------------------------------------
    # 列表维护
    # ------------------------------------------------------------------
    def _add_files(self, file_paths):
        """将文件路径加入列表，自动去重。"""
        existing = set(self.file_list)
        added = False
        for p in file_paths:
            if p and p not in existing:
                self.file_list.append(p)
                existing.add(p)
                added = True
        if added:
            self._refresh_table()

    def _refresh_table(self):
        """根据 self.file_list 重新填充表格。"""
        self.file_table.setRowCount(0)
        for row, path in enumerate(self.file_list):
            self.file_table.insertRow(row)
            filename = os.path.basename(path)
            # 文件大小
            try:
                size_bytes = os.path.getsize(path)
                size_str = format_size(size_bytes)
            except OSError:
                size_str = "未知"
            # 文件名
            item_name = QTableWidgetItem(filename)
            item_name.setToolTip(path)
            # 路径
            item_path = QTableWidgetItem(path)
            item_path.setToolTip(path)
            # 大小
            item_size = QTableWidgetItem(size_str)
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # 状态
            item_status = QTableWidgetItem("待转换")

            self.file_table.setItem(row, 0, item_name)
            self.file_table.setItem(row, 1, item_path)
            self.file_table.setItem(row, 2, item_size)
            self.file_table.setItem(row, 3, item_status)

        # 列宽自适应内容
        self.file_table.resizeColumnsToContents()

    def _on_clear(self):
        """清空文件列表与表格，重置统计。"""
        self.file_list.clear()
        self.file_table.setRowCount(0)
        self.success_count = 0
        self.fail_count = 0
        self.progress_bar.setValue(0)
        self._refresh_status_bar()

    def _on_remove_selected(self):
        """删除表格中选中行对应的文件路径。"""
        rows = sorted({idx.row() for idx in self.file_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.file_list):
                del self.file_list[row]
        self._refresh_table()

    # ------------------------------------------------------------------
    # 状态栏
    # ------------------------------------------------------------------
    def _refresh_status_bar(self):
        """刷新状态栏统计信息。"""
        total = len(self.file_list)
        self.statusBar().showMessage(
            f"共 {total} 个文件 | 成功 {self.success_count} | 失败 {self.fail_count}"
        )

    # ------------------------------------------------------------------
    # 转换与取消（Task 6）
    # ------------------------------------------------------------------
    def _on_convert(self):
        """开始转换：校验输入、确定覆盖策略、启动 worker 并连接信号。"""
        # 1. 校验文件列表非空
        if not self.file_list:
            QMessageBox.warning(self, "提示", "请先选择需要转换的文件")
            return

        # 2. 校验 markitdown 是否可用
        if not converter.MARKITDOWN_AVAILABLE:
            QMessageBox.critical(
                self,
                "依赖缺失",
                "MarkItDown 未安装，请运行以下命令安装：\n\npip install 'markitdown[all]'",
            )
            return

        # 3. 预先确定覆盖策略
        overwrite_strategy = self._determine_overwrite_strategy()
        if overwrite_strategy is None:
            # 用户选择取消
            return

        # 4. 创建 ConvertWorker 实例
        self.worker = ConvertWorker(self.file_list, overwrite_strategy, parent=self)

        # 5. 连接信号
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.all_done.connect(self._on_all_done)

        # 6. 重置统计与进度条
        self.success_count = 0
        self.fail_count = 0
        self.progress_bar.setValue(0)

        # 7. 将表格所有行状态列重置为「待转换」
        default_brush = self.palette().windowText()
        for row in range(self.file_table.rowCount()):
            item = self.file_table.item(row, 3)
            if item is not None:
                item.setText("待转换")
                item.setToolTip("")
                item.setForeground(default_brush)

        # 8. 切换按钮状态（转换中）
        self._set_buttons_converting(True)

        # 9. 启动 worker
        self.worker.start()

    def _determine_overwrite_strategy(self):
        """扫描目标 .md 路径，若存在已生成文件则询问用户覆盖策略。

        返回:
            "overwrite"：全部覆盖
            "skip"：全部跳过
            None：用户取消转换
        """
        existing_count = 0
        for path in self.file_list:
            output_path = converter.get_output_md_path(path)
            if os.path.exists(output_path):
                existing_count += 1

        if existing_count == 0:
            # 无已存在目标，直接覆盖（等同写入新文件）
            return "overwrite"

        # 存在已生成文件，询问用户
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("目标文件已存在")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(f"检测到 {existing_count} 个目标 .md 文件已存在，如何处理？")
        btn_overwrite = msg_box.addButton("全部覆盖", QMessageBox.AcceptRole)
        btn_skip = msg_box.addButton("全部跳过", QMessageBox.AcceptRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_overwrite)
        msg_box.exec_()

        clicked = msg_box.clickedButton()
        if clicked is btn_overwrite:
            return "overwrite"
        elif clicked is btn_skip:
            return "skip"
        else:
            return None

    def _on_progress(self, current_1based, total, filename):
        """进度信号槽：更新状态栏、进度条与表格行状态。"""
        # 状态栏
        self.statusBar().showMessage(f"正在转换 ({current_1based}/{total}): {filename}")
        # 进度条
        self.progress_bar.setValue(int(current_1based / total * 100))
        # 表格行状态设为「转换中」
        row = current_1based - 1
        if 0 <= row < self.file_table.rowCount():
            item = self.file_table.item(row, 3)
            if item is not None:
                item.setText("转换中")

    def _on_file_done(self, index, status, message):
        """单文件完成信号槽：更新表格行状态与统计。"""
        if 0 <= index < self.file_table.rowCount():
            item = self.file_table.item(index, 3)
            if item is not None:
                item.setText(status)
                if status == "失败":
                    # 失败时设置 ToolTip 与红色文字
                    item.setToolTip(message)
                    item.setForeground(QBrush(Qt.red))

        # 更新统计
        if status == "成功":
            self.success_count += 1
        elif status == "失败":
            self.fail_count += 1

        # 更新状态栏统计
        self._refresh_status_bar()

    def _on_all_done(self, success, fail):
        """全部转换完成槽：恢复 UI 状态并提示用户。"""
        # 进度条设为 100
        self.progress_bar.setValue(100)
        # 恢复按钮状态
        self._set_buttons_converting(False)
        # 恢复取消按钮文本
        self.btn_cancel.setText("取消")
        # 状态栏显示完成信息
        self.statusBar().showMessage(f"转换完成 | 成功 {success} | 失败 {fail}")
        # 弹出完成提示
        QMessageBox.information(
            self,
            "转换完成",
            f"转换完成！\n成功: {success} 个\n失败: {fail} 个",
        )
        # 释放 worker 引用，便于 GC
        self.worker = None

    def _on_cancel(self):
        """取消正在进行的转换。"""
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            # 禁用取消按钮并提示用户取消请求已收到
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("取消中...")
            self.statusBar().showMessage("正在取消...")
            # worker 会在当前文件处理完后退出循环并发射 all_done，
            # 由 _on_all_done 恢复 UI 状态

    def _set_buttons_converting(self, converting: bool):
        """根据是否正在转换切换按钮启用状态。

        参数:
            converting: True 表示进入转换中状态（禁用相关按钮、启用取消）；
                        False 表示转换结束（恢复按钮、禁用取消）。
        """
        # 模式单选按钮
        self.rb_dir_all.setEnabled(not converting)
        self.rb_dir_filtered.setEnabled(not converting)
        self.rb_files.setEnabled(not converting)
        # 文件选择与列表操作按钮
        self.btn_convert.setEnabled(not converting)
        self.btn_clear.setEnabled(not converting)
        self.btn_remove.setEnabled(not converting)
        self.btn_select_dir.setEnabled(not converting)
        self.btn_select_files.setEnabled(not converting)
        # 文件类型面板（工具栏 + 复选框 + 自定义输入）
        self._set_type_panel_enabled(not converting)
        # 取消按钮（转换中启用，结束后禁用）
        self.btn_cancel.setEnabled(converting)
        # 转换结束后恢复模式相关控件的正确启用状态
        if not converting:
            self._update_mode_controls()
