"""程序入口。

负责：
1. 在最前面做 ffmpeg "自带注入"（通过 imageio-ffmpeg），使音频（mp3 / m4a / wav 等）
   转换无需用户再手动安装 ffmpeg 与配置 PATH；
2. 创建 QApplication 并启动主窗口。

MarkItDown 的导入可用性检查在 app.converter 模块中处理。
"""
from __future__ import annotations

import os
import sys


def _ensure_ffmpeg_shim(ffmpeg_exe: str) -> str:
    """imageio-ffmpeg 发布的二进制名带平台 + 版本号（如 ffmpeg-win-x86_64-v7.1.exe），
    导致 `subprocess.run(['ffmpeg', ...])` / `shutil.which('ffmpeg')` 无法命中。

    在同目录下创建一个真正叫 `ffmpeg.exe` 的 shim：优先级
      1) os.link 硬链接（最快，不占空间）
      2) shutil.copy2 复制副本（硬链接失败兜底，约 ~90MB，在 PyInstaller onedir / 开发环境里也 OK）

    返回 shim 的完整路径。
    """
    folder = os.path.abspath(os.path.dirname(ffmpeg_exe))
    real_name = os.path.basename(ffmpeg_exe)

    # 已经是标准名就不用做 shim 了
    if real_name.lower() == "ffmpeg.exe":
        return ffmpeg_exe

    shim = os.path.join(folder, "ffmpeg.exe")
    if os.path.isfile(shim):
        # 已经存在就直接复用（大概率是上次做好的 shim 或用户自己放的）
        try:
            # 若 shim 大小和目标不一致（imageio 升级了二进制但老 shim 还在）就重建
            if os.path.getsize(shim) != os.path.getsize(ffmpeg_exe):
                os.remove(shim)
            else:
                return shim
        except OSError:
            # 读不到大小就当它坏了，重建
            try:
                os.remove(shim)
            except OSError:
                pass

    if not os.path.isfile(shim):
        # 1) 硬链接（同分区才支持；Python 3.2+ Windows NTFS 没问题）
        try:
            os.link(ffmpeg_exe, shim)
            return shim
        except OSError:
            pass

        # 2) 复制兜底（硬链接失败时用）
        try:
            import shutil
            shutil.copy2(ffmpeg_exe, shim)
            return shim
        except Exception:
            # 连复制都失败（文件夹只读？）—— 直接返回原长文件名，
            # 后面会通过 pydub.AudioSegment.converter 直接给完整路径
            return ffmpeg_exe
    return shim


def _bootstrap_ffmpeg() -> tuple[bool, str]:
    """尝试把 imageio-ffmpeg 自带的静态 ffmpeg 注入 PATH & pydub 全局属性。

    返回:
        (是否成功注入, 最终 ffmpeg.exe 完整路径（或失败原因）)
    """
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        return False, "imageio-ffmpeg 未安装，音频格式（mp3/m4a 等）需要系统自带 ffmpeg"

    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        return False, f"获取 imageio-ffmpeg 二进制失败: {e}"

    if not ffmpeg_exe or not os.path.isfile(ffmpeg_exe):
        return False, f"imageio-ffmpeg 返回的 ffmpeg 路径无效: {ffmpeg_exe!r}"

    # 关键：imageio 发布的二进制名带版本号和平台前缀，确保有个叫 ffmpeg.exe 的 shim
    ffmpeg_shim = _ensure_ffmpeg_shim(ffmpeg_exe)
    ffmpeg_dir = os.path.abspath(os.path.dirname(ffmpeg_shim))

    # 1) 插入 PATH 最前面：所有子进程（pydub.subprocess / markitdown 内部 shell 调用）
    #    都优先用这份 ffmpeg，避免依赖系统已安装的 ffmpeg
    old_path = os.environ.get("PATH", "")
    path_parts = old_path.split(os.pathsep) if old_path else []
    if ffmpeg_dir not in path_parts:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + old_path

    # 2) 显式告诉 pydub ffmpeg 在哪里（优先级最高，直接跳过 PATH 查找）
    #    用 imageio 给的原始长文件名（不走 shim），绕过 shim 创建失败的边缘情况
    try:
        from pydub import AudioSegment  # type: ignore

        AudioSegment.converter = ffmpeg_exe          # pydub 内部统一属性
        AudioSegment.ffmpeg = ffmpeg_exe             # 兼容某些旧写法
        # AudioSegment.ffprobe 不设置：markitdown 音频转写链路只用 ffmpeg，
        # 不依赖 ffprobe；万一将来用到了，PATH 兜底也够用
    except Exception:
        # pydub 未装（不应该，markitdown[all] 已带），这里静默忽略
        pass

    return True, ffmpeg_exe


# 必须在 QApplication / markitdown / pydub 任何真正干活的 import 之前完成注入
FFMPEG_OK, FFMPEG_INFO = _bootstrap_ffmpeg()


# 尝试导入 PyQt5，若缺失则给出友好提示并退出
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
except ImportError:
    print("未检测到 PyQt5，请先运行: pip install PyQt5>=5.15")
    sys.exit(1)

# 启用高 DPI 缩放支持，必须在创建 QApplication 之前调用
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)


def main():
    app = QApplication(sys.argv)

    # ui_main.py 由后续步骤实现（UI 层）；当前若尚未创建会给出提示
    try:
        from app.ui_main import MainWindow
    except ImportError:
        print("UI 模块 app/ui_main.py 尚未实现，请由后续步骤创建。")
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
