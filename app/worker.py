"""后台转换线程模块。

在独立线程中执行文件批量转换，通过信号向主线程报告进度与结果，
不直接操作任何 UI。
"""
from __future__ import annotations

import os

from PyQt5.QtCore import QThread, pyqtSignal

from app.converter import convert_file, get_output_md_path, write_md_file


class ConvertWorker(QThread):
    """文件批量转换线程。

    覆盖策略说明（简化方案）：
        - overwrite_strategy="overwrite"：目标 .md 已存在则覆盖
        - overwrite_strategy="skip"：目标 .md 已存在则跳过
        UI 在启动 worker 前应预先扫描所有目标文件，若存在则一次性
        弹窗询问「全部覆盖 / 全部跳过 / 取消」，将最终策略传给本 worker。
        因此本 worker 不发射 need_overwrite_decision 信号（保留该信号
        定义仅为兼容前端信号协议）。
    """

    # (current_index_1based, total_count, current_filename)
    progress = pyqtSignal(int, int, str)
    # (index_0based, status_str, message_str)  status_str 取值: "成功"/"失败"/"跳过"
    file_done = pyqtSignal(int, str, str)
    # (success_count, fail_count)
    all_done = pyqtSignal(int, int)
    # (index_0based, file_path) - 简化方案下不发射，保留以兼容信号协议
    need_overwrite_decision = pyqtSignal(int, str)

    def __init__(self, file_list: list, overwrite_strategy: str = "ask", parent=None):
        super().__init__(parent)
        self.file_list = file_list
        self.overwrite_strategy = overwrite_strategy
        # 取消标志，由主线程通过 cancel() 设置
        self._cancel = False

    def cancel(self):
        """请求取消转换，下一次循环开始时生效。"""
        self._cancel = True

    def run(self):
        total = len(self.file_list)
        success_count = 0
        fail_count = 0

        for i, file_path in enumerate(self.file_list):
            # 每次循环开始检查取消标志
            if self._cancel:
                break

            filename = os.path.basename(file_path)
            # 发射进度信号（1-based 索引）
            self.progress.emit(i + 1, total, filename)

            output_path = get_output_md_path(file_path)

            # 目标已存在时的处理
            if os.path.exists(output_path):
                # 仅 "overwrite" 策略继续执行；"skip" 与 "ask"
                # （简化方案下 ask 按 skip 安全处理）均跳过
                if self.overwrite_strategy != "overwrite":
                    self.file_done.emit(i, "跳过", "目标文件已存在")
                    continue
                # overwrite 策略：直接覆盖，继续向下执行转换与写入

            # 调用 converter 转换
            ok, msg = convert_file(file_path)
            if not ok:
                self.file_done.emit(i, "失败", msg)
                fail_count += 1
                continue

            # 写入 Markdown 文件
            wok, wmsg = write_md_file(output_path, msg)
            if not wok:
                self.file_done.emit(i, "失败", wmsg)
                fail_count += 1
                continue

            self.file_done.emit(i, "成功", "")
            success_count += 1

        # 全部完成（或被取消），发射汇总信号
        self.all_done.emit(success_count, fail_count)
