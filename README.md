# MD 查看器 (Markdown Viewer)

一个 Windows 上看 Markdown（`.md`）文档的小软件，特别适合看「一个文件夹里分成很多章」的长文档，比如小说、笔记、教程。

- **自动排章节**：打开一个 md 文件，同文件夹里的其他 md 会按文件名自然排序成章节（能识别 `第2章` 在 `第10章` 前面，也认「第十章」这种中文数字）。
- **目录树**：左侧显示每章和章内的标题（h1–h3），点一下就跳过去。
- **单章 / 全部连读**：可以一章一章看，也可以把所有章节连成一页往下读。
- **保留排版**：支持表格、代码高亮、任务列表、脚注，以及文档里写的 HTML（字体颜色、`<span style>` 等）。
- **好用的小功能**：拖文件或文件夹进窗口打开、md 之间的链接可以跳转、深色模式、调字号、查找、文件被修改后自动刷新、GBK 编码的旧文件也能正确识别。

## 下载使用

1. 到 [Releases](../../releases/latest) 下载 `MDViewer-win64.zip`。
2. 解压到任意文件夹，双击 `MDViewer.exe`。
3. 把 md 文件或文件夹拖进窗口即可。想双击 md 就用它打开：右键任意 `.md` 文件 → 打开方式 → 选择其他应用 → 浏览到 `MDViewer.exe`，勾选「始终使用此应用」。

只支持 64 位 Windows 10 / 11，不需要安装 Python。程序内置了网页渲染引擎（Qt WebEngine），所以体积比较大。

## 从源码运行 / 自己打包

需要 Python 3.11：

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw viewer.py
```

打包成 exe：

```bat
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build.py
```

用到的开源库：[PySide6 / Qt WebEngine](https://doc.qt.io/qtforpython-6/)（LGPL）、[markdown-it-py](https://github.com/executablebooks/markdown-it-py)（MIT）、[Pygments](https://pygments.org/)（BSD）。

## 许可

[MIT](LICENSE)
