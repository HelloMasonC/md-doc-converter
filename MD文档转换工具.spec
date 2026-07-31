# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

hiddenimports += collect_submodules('app')

tmp_ret = collect_all('magika')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('markitdown')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('imageio_ffmpeg')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# 视觉模型对话框相关（按钮点击时才第一次 import，必须显式收集）
hiddenimports += [
    'app.dialog_vision_settings',
    'app.vision_client',
    'app.config',
    'app.converter',
    'app.ui_main',
    'app.worker',
    'ssl',
    '_ssl',
    'urllib.request',
    'urllib.error',
    'urllib.parse',
    'mimetypes',
    'base64',
    'json',
    'dataclasses',
]

# ---------------------------------------------------------------
# 显式把 Conda Miniforge 的 OpenSSL DLL + _ssl.pyd 强塞进 exe 根目录
# 根因（点击"配置视觉模型"按钮闪退 / ImportError: DLL load failed while importing _ssl）：
#   打包用的 Python 是 D:\Programs\Miniforge\python.exe（base conda env），
#   base 根目录里并没有 libcrypto-3-x64.dll / libssl-3-x64.dll，
#   PyInstaller 通过 markitdown 的钩子收集到了一对它从自己别的路径里找来的
#   同名的 OpenSSL DLL，把它们标为 "b"(binary) 塞进了 PKG，但这两个 DLL 
#   **没有被 bootloader 解压到 _MEI 临时根目录**（实际是在某个子归档里），
#   加上 _ssl.pyd 又被压进 base_library.zip 而不是落地的文件，
#   导致最终 _ssl.pyd 在被 exec_module 时 LoadLibrary 找不到 OpenSSL DLL，进程崩溃。
# 修法：
#   1) 直接把完整版的 libcrypto-3-x64.dll / libssl-3-x64.dll 用绝对路径
#      塞到 binaries 根目录（目标位置 '.'）,确保 _MEI 根目录有它们；
#   2) 把 _ssl.pyd 也显式列到 binaries 根目录，绕开 base_library.zip 的形式；
#   3) 保持 hiddenimports 里的 'ssl' 不变，ssl.py 是纯 Python 模块。
# 这些路径在使用其他 Miniconda/Anaconda 环境时可能不同；如果换机器打包，
# 用 `python -c "import ssl,os; print(os.path.dirname(ssl._ssl.__file__))"` 
# 找 _ssl.pyd 所在位置，把目录里的 libcrypto/libssl 名单列到这。
_OPENSSL_DLL_CANDIDATES = [
    # 优先使用与打包当前 _ssl.pyd 同版本的库
    r'D:\Programs\Miniforge\envs\ssw3\Library\bin\libcrypto-3-x64.dll',
    r'D:\Programs\Miniforge\envs\fastapiwebadmin\Library\bin\libcrypto-3-x64.dll',
    r'D:\Programs\Miniforge\envs\fa\Library\bin\libcrypto-3-x64.dll',
]
_LIBSSL_DLL_CANDIDATES = [
    r'D:\Programs\Miniforge\envs\ssw3\Library\bin\libssl-3-x64.dll',
    r'D:\Programs\Miniforge\envs\fastapiwebadmin\Library\bin\libssl-3-x64.dll',
    r'D:\Programs\Miniforge\envs\fa\Library\bin\libssl-3-x64.dll',
]
_SSL_PYD_CANDIDATES = [
    r'D:\Programs\Miniforge\DLLs\_ssl.pyd',
]

def _first_exists(paths):
    for p in paths:
        if os.path.isfile(p):
            return p
    return None

_libcrypto = _first_exists(_OPENSSL_DLL_CANDIDATES)
_libssl = _first_exists(_LIBSSL_DLL_CANDIDATES)
_ssl_pyd = _first_exists(_SSL_PYD_CANDIDATES)
if _libcrypto:
    binaries.append((_libcrypto, '.'))
if _libssl:
    binaries.append((_libssl, '.'))
if _ssl_pyd:
    binaries.append((_ssl_pyd, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MD文档转换工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,             # 关闭 UPX：压缩 Qt5/OpenSSL DLL 极易造成点按钮时进程闪退
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
