# MarkItDown 使用说明

MarkItDown 是微软开源的文档转 Markdown 工具（GitHub: microsoft/markitdown）。

## 一、命令行用法（最常用）

```bash
# 1. 转换并直接输出到屏幕
markitdown 文件.xlsx

# 2. 转换并保存到指定文件（-o / --output）
markitdown 文件.xlsx -o 文件.md

# 3. 批量转换一个目录下所有文件（-d / --directory，配合 -o 输出目录）
markitdown -d "D:\Library\资源知识库" -o "D:\Library\资源知识库\md_output"

# 4. 加上 --extract-media 参数即可完整保留图文；去掉 --extract-media 参数，转换速度更快，仅文字内容
markitdown 文档.docx -o 输出.md --extract-media=./media

# 5. 查看帮助与所有参数
markitdown --help
```

批量目录转换（第 3 条）是官方内置的，比用 PowerShell 循环更简洁。常用参数：

- `-d, --directory` 目录批量转换
- `-o, --output` 输出文件/目录
- `-x, --extension` 仅转换指定扩展名（如 `-x xlsx -x xls`）
- `--preserve-sheets`（表格专用）保留每个工作表为独立 Markdown 表格

## 二、Python API 用法

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("文件.xlsx")   # 返回 DocumentConverterResult 对象
print(result.text_content)         # 转换后的 Markdown 文本
print(result.title)                # 文档标题（若有）

# 也可直接转成文件
with open("文件.md", "w", encoding="utf-8") as f:
    f.write(result.text_content)
```

适合需要二次处理、过滤特定 sheet、或集成到自动化脚本里的场景。

## 三、支持的文件类型

| 类型 | 格式                                                                   |
| ---- | ---------------------------------------------------------------------- |
| 表格 | .xlsx / .xls / .csv                                                    |
| 文档 | .docx / .pdf / .html / .txt / .xml                                     |
| 演示 | .pptx                                                                  |
| 音频 | .mp3 / .wav（需 ffmpeg，转写为文字）                                   |
| 图片 | .jpg / .png（需配置 Azure 视觉模型，可提取文字/描述）                  |
| 其他 | .json / .yaml / .zip（遍历内容）/ YouTube 字幕 / Word .doc（旧格式）等 |

## 四、常见注意事项

1. **大表格慢**：包含大量行列的表格文件转换耗时较长属正常。
2. **多 sheet**：默认每个 sheet 输出为一段独立表格，以 sheet 名作为标题分隔。
3. **公式/格式**：MarkItDown 提取的是计算后的值，不保留公式与单元格样式。
4. **.xls 旧格式**：依赖 `xlrd`，注意 xlrd 2.0 仅支持 .xls，.xlsx 由 openpyxl 处理。

## 五、安装方式

```bash
# 安装完整版（包含所有可选依赖）
pip install 'markitdown[all]'

# 安装基础版（仅核心功能）
pip install markitdown
```

## 六、实际使用示例

转换 `D:\Library\资源知识库` 目录下所有 xlsx/xls 文件：

```powershell
$srcDir = "D:\Library\资源知识库"
$outDir = "D:\Library\资源知识库\md_output"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Get-ChildItem -Path $srcDir -File | Where-Object { $_.Extension -in '.xlsx','.xls' } | ForEach-Object {
    $outFile = Join-Path $outDir ($_.BaseName + ".md")
    markitdown $_.FullName -o $outFile
}
```
