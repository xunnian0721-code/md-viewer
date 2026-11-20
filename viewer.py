# -*- coding: utf-8 -*-
"""MD 查看器：渲染 Markdown（保留加粗/斜体/内嵌 HTML 字体等），同文件夹内的 md 排成章节。"""
import os
import re
import sys
import tempfile
import html as htmlmod
from urllib.parse import urlsplit, unquote

from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from mdit_py_plugins.footnote import footnote_plugin
from pygments import highlight as pyg_highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound

from PySide6.QtCore import Qt, QUrl, QSettings, QTimer, QFileSystemWatcher, QEvent, QObject, QRectF
from PySide6.QtGui import (QAction, QDesktopServices, QFont, QIcon, QPixmap, QPainter, QColor,
                           QKeySequence, QShortcut, QPainterPath)
from PySide6.QtWidgets import (QApplication, QMainWindow, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QToolBar, QLineEdit, QFileDialog, QLabel, QWidget, QSizePolicy, QMessageBox)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings

APP_NAME = "MD 查看器"
MD_EXTS = (".md", ".markdown", ".mdown", ".mkd")

# ---------------------------------------------------------------- 排序
CN_DIGIT = {'零': 0, '〇': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9}
CN_UNIT = {'十': 10, '百': 100, '千': 1000}
NUM_RE = re.compile(r'(\d+|[零〇一二两三四五六七八九十百千]+)')


def cn_to_int(s):
    total, num = 0, 0
    for ch in s:
        if ch in CN_DIGIT:
            num = CN_DIGIT[ch]
        else:
            total += (num or 1) * CN_UNIT[ch]
            num = 0
    return total + num


def chapter_sort_key(path):
    name = os.path.splitext(os.path.basename(path))[0].lower()
    first = 0 if name in ("readme", "index", "目录", "序", "序言", "前言") else 1
    key = [(first, 0, '')]
    for part in NUM_RE.split(name):
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part), ''))
        elif NUM_RE.fullmatch(part):
            key.append((0, cn_to_int(part), ''))
        else:
            key.append((1, 0, part))
    return key


def list_md_files(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    files = [os.path.join(folder, n) for n in names
             if n.lower().endswith(MD_EXTS) and os.path.isfile(os.path.join(folder, n))]
    return sorted(files, key=chapter_sort_key)


def read_text(path):
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- Markdown 渲染
_formatter = HtmlFormatter(nowrap=True)


def _highlight(code, lang, _attrs):
    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang.strip().split()[0])
    except ClassNotFound:
        return ""
    return ('<pre class="hl"><code class="language-%s">%s</code></pre>'
            % (htmlmod.escape(lang), pyg_highlight(code, lexer, _formatter)))


def make_md():
    md = MarkdownIt("commonmark", {"html": True, "highlight": _highlight})
    md.enable(["table", "strikethrough"])
    md.use(front_matter_plugin).use(tasklists_plugin).use(footnote_plugin)
    return md


MD = make_md()


def slugify(text):
    s = text.strip().lower()
    s = re.sub(r'[^\w\- ]', '', s)
    return re.sub(r'\s', '-', s)


def plain_text(inline_token):
    parts = []
    for c in inline_token.children or []:
        if c.type in ("text", "code_inline"):
            parts.append(c.content)
    return "".join(parts).strip() or inline_token.content.strip()


def resolve_url(href, base_dir):
    """把相对路径（图片、链接）换成绝对 file:/// 地址；网址、#锚点原样保留。"""
    if not href or href.startswith("#"):
        return href
    sp = urlsplit(href)
    if sp.scheme and len(sp.scheme) > 1:
        return href  # http:, https:, mailto:, data:, file: …
    path = unquote(href.split("#", 1)[0].split("?", 1)[0])
    frag = href.split("#", 1)[1] if "#" in href else ""
    full = path if os.path.isabs(path) else os.path.normpath(os.path.join(base_dir, path))
    url = QUrl.fromLocalFile(full).toString(QUrl.FullyEncoded)
    return url + ("#" + frag if frag else "")


class Chapter:
    """一个 md 文件解析后的结果。"""

    def __init__(self, path, index):
        self.path = path
        self.index = index
        self.mtime = os.path.getmtime(path)
        text = read_text(path)
        base_dir = os.path.dirname(path)
        env = {}
        tokens = MD.parse(text, env)
        self.headings = []  # (level, text, element_id)
        used = {}
        n = 0
        for i, tok in enumerate(tokens):
            if tok.type == "heading_open":
                title = plain_text(tokens[i + 1])
                slug = slugify(title) or "h"
                if slug in used:
                    used[slug] += 1
                    slug = "%s-%d" % (slug, used[slug])
                else:
                    used[slug] = 0
                eid = "c%d-h%d" % (index, n)
                n += 1
                tok.attrSet("id", eid)
                tok.attrSet("data-slug", slug)
                self.headings.append((int(tok.tag[1]), title, eid))
            elif tok.type == "inline":
                for c in tok.children or []:
                    if c.type == "image":
                        c.attrSet("src", resolve_url(c.attrGet("src"), base_dir))
                    elif c.type == "link_open":
                        c.attrSet("href", resolve_url(c.attrGet("href"), base_dir))
        self.html = MD.renderer.render(tokens, MD.options, env)
        stem = os.path.splitext(os.path.basename(path))[0]
        if self.headings and self.headings[0][0] == 1:
            self.title = self.headings[0][1]
            self.title_from_h1 = True
        else:
            self.title = stem
            self.title_from_h1 = False


# ---------------------------------------------------------------- 页面模板
PYG_LIGHT = HtmlFormatter(style="friendly").get_style_defs("body:not(.dark) .hl")
PYG_DARK = HtmlFormatter(style="monokai").get_style_defs("body.dark .hl")

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<base href="__BASE__">
<title>__TITLE__</title>
<style>
:root { --fs: __FS__px; }
body { --bg:#ffffff; --fg:#24292f; --muted:#6a737d; --line:#d8dee4; --code-bg:#f3f4f6;
       --quote:#57606a; --link:#0969da; --th:#f6f8fa; --mark:#fff3a3; }
body.dark { --bg:#1e1f22; --fg:#d7dae0; --muted:#8b949e; --line:#3a3d42; --code-bg:#2b2d31;
       --quote:#9ea7b3; --link:#58a6ff; --th:#26282c; --mark:#665c00; }
html, body { background: var(--bg); }
body { color: var(--fg); margin: 0;
  font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif;
  font-size: var(--fs); line-height: 1.75; word-wrap: break-word; }
.wrap { max-width: 920px; margin: 0 auto; padding: 28px 44px 90px; }
section.chapter + section.chapter { margin-top: 56px; padding-top: 28px; border-top: 3px double var(--line); }
.chapter-file { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
h1,h2,h3,h4,h5,h6 { line-height: 1.35; margin: 1.4em 0 .6em; font-weight: 700; }
h1 { font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid var(--line); }
h2 { font-size: 1.5em; padding-bottom: .25em; border-bottom: 1px solid var(--line); }
h3 { font-size: 1.25em; } h4 { font-size: 1.1em; } h5 { font-size: 1em; } h6 { font-size: .9em; color: var(--muted); }
section > h1:first-of-type, .chapter > :first-child { margin-top: 0; }
p, ul, ol, blockquote, table, pre, dl { margin: 0 0 1em; }
a { color: var(--link); text-decoration: none; } a:hover { text-decoration: underline; }
strong, b { font-weight: 700; } em, i { font-style: italic; } del, s { opacity: .75; }
mark { background: var(--mark); color: inherit; }
u, ins { text-decoration: underline; }
blockquote { padding: .2em 1em; color: var(--quote); border-left: 4px solid var(--line); }
code, kbd, samp { font-family: "Cascadia Mono", Consolas, "Microsoft YaHei UI", monospace; font-size: .9em; }
:not(pre) > code { background: var(--code-bg); padding: .15em .4em; border-radius: 5px; }
kbd { border: 1px solid var(--line); border-bottom-width: 2px; border-radius: 4px; padding: 0 .35em; }
pre { background: var(--code-bg); padding: 14px 16px; border-radius: 8px; overflow: auto; line-height: 1.5; }
pre code { background: none; padding: 0; font-size: .88em; }
table { border-collapse: collapse; display: block; overflow: auto; max-width: 100%; }
th, td { border: 1px solid var(--line); padding: 6px 13px; }
th { background: var(--th); font-weight: 700; }
hr { border: 0; border-top: 1px solid var(--line); margin: 1.6em 0; }
img { max-width: 100%; }
li > p { margin: 0; } li + li { margin-top: .2em; }
ul.contains-task-list { list-style: none; padding-left: 1.2em; }
.task-list-item-checkbox { margin-right: .45em; }
.footnotes { font-size: .88em; color: var(--muted); }
.navbar { display: flex; justify-content: space-between; margin-top: 48px; padding-top: 16px;
          border-top: 1px solid var(--line); font-size: .95em; }
.navbar a { cursor: pointer; }
.navbar .off { color: var(--muted); }
.hl { background: var(--code-bg) !important; }
__PYG__
</style></head>
<body class="__THEME__"><div class="wrap">
__BODY__
</div>
<script>
function findIn(root, key) {
  if (!root || !key) return null;
  var k = CSS.escape(key);
  return root.querySelector('[data-slug="' + k + '"]') || root.querySelector('[id="' + k + '"]')
      || root.querySelector('a[name="' + k + '"]');
}
function jumpSlug(ch, slug) {
  var sec = document.getElementById('ch-' + ch);
  var el = findIn(sec, slug) || findIn(document, slug) || sec;
  if (el) el.scrollIntoView();
}
function goId(id) { var el = document.getElementById(id); if (el) el.scrollIntoView(); }
function setFs(px) { document.documentElement.style.setProperty('--fs', px + 'px'); }
function setDark(on) { document.body.classList.toggle('dark', on); }
function nav(what) { document.title = 'nav:' + what + ':' + Date.now(); }
document.addEventListener('click', function (e) {
  var a = e.target.closest ? e.target.closest('a') : null;
  if (!a) return;
  var h = a.getAttribute('href') || '';
  if (h.charAt(0) === '#') {
    e.preventDefault();
    var key = decodeURIComponent(h.slice(1));
    var el = findIn(a.closest('section.chapter'), key) || findIn(document, key);
    if (el) el.scrollIntoView();
  }
});
var curCh = null;
function track() {
  var secs = document.querySelectorAll('section.chapter'), idx = 0;
  if (!secs.length) return;
  for (var i = 0; i < secs.length; i++) if (secs[i].getBoundingClientRect().top <= 120) idx = i;
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) idx = secs.length - 1;
  var c = secs[idx].getAttribute('data-ch');
  if (c !== curCh) { curCh = c; document.title = 'ch:' + c; }
}
window.addEventListener('scroll', track);
</script>
</body></html>"""

WELCOME = """<div style="text-align:center;margin-top:18vh;color:var(--muted)">
<div style="font-size:46px;font-weight:700;color:var(--fg)">MD 查看器</div>
<p style="margin-top:18px">把 <b>.md 文件</b> 或 <b>文件夹</b> 拖到这个窗口里，<br>
或点左上角「打开文件」「打开文件夹」。</p>
<p>同一文件夹里的所有 md 会按文件名顺序排成章节，显示在左边目录里。</p></div>"""


# ---------------------------------------------------------------- 浏览页
class Page(QWebEnginePage):
    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def acceptNavigationRequest(self, url, nav_type, is_main):
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            return True
        scheme = url.scheme().lower()
        if scheme == "file":
            local = url.toLocalFile()
            frag = unquote(url.fragment())
            if local.lower().endswith(MD_EXTS) and os.path.isfile(local):
                QTimer.singleShot(0, lambda: self.win.open_path(local, frag))
            elif os.path.exists(local):
                QDesktopServices.openUrl(url)
            return False
        QDesktopServices.openUrl(url)  # 网址交给系统浏览器
        return False


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    p.fillPath(path, QColor("#C9A227"))
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 22, QFont.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "MD")
    p.end()
    return QIcon(pm)


def accepted_paths(mime):
    out = []
    if mime.hasUrls():
        for u in mime.urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if os.path.isdir(p) or p.lower().endswith(MD_EXTS):
                    out.append(os.path.normpath(p))
    return out


class DropFilter(QObject):
    """整个程序范围拦截拖放（网页控件本身会吞掉拖放事件）。"""

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t in (QEvent.DragEnter, QEvent.DragMove):
            if accepted_paths(ev.mimeData()):
                ev.acceptProposedAction()
                return True
        elif t == QEvent.Drop:
            paths = accepted_paths(ev.mimeData())
            if paths:
                ev.acceptProposedAction()
                QTimer.singleShot(0, lambda: self.win.open_dropped(paths))
                return True
        return False


# ---------------------------------------------------------------- 主窗口
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("ClaudeTools", "md-viewer")
        self.files = []  # 章节文件列表
        self.chapters = {}  # path -> Chapter
        self.cur = 0
        self.folder = ""
        self.all_mode = self.settings.value("all_mode", False, type=bool)
        self.dark = self.settings.value("dark", False, type=bool)
        self.fs = self.settings.value("font_size", 16, type=int)
        self.pending_js = None
        self.page_seq = 0
        self.cache_dir = os.path.join(tempfile.gettempdir(), "md-viewer")
        os.makedirs(self.cache_dir, exist_ok=True)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_icon())
        self.resize(1200, 820)
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.setAcceptDrops(True)

        # 左：章节目录
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemClicked.connect(self.on_tree_click)
        self.tree.setStyleSheet("QTreeWidget{border:none;font-size:13px;} QTreeWidget::item{padding:3px 2px;}")

        # 右：正文
        self.view = QWebEngineView()
        self.view.setAcceptDrops(False)
        self.page = Page(self)
        self.view.setPage(self.page)
        s = self.page.settings()
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.page.loadFinished.connect(self.on_load_finished)
        self.page.titleChanged.connect(self.on_title_changed)

        split = QSplitter()
        split.addWidget(self.tree)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 940])
        self.setCentralWidget(split)

        self.build_toolbar()

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(lambda _p: self.reload_timer.start())
        self.watcher.directoryChanged.connect(lambda _p: self.reload_timer.start())
        self.reload_timer = QTimer(self, singleShot=True, interval=400)
        self.reload_timer.timeout.connect(self.reload_from_disk)

        self.drop_filter = DropFilter(self)
        QApplication.instance().installEventFilter(self.drop_filter)

    # ---------- 工具栏
    def build_toolbar(self):
        tb = QToolBar()
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        tb.setStyleSheet("QToolBar{spacing:4px;padding:4px;} QToolButton{padding:4px 8px;}")
        self.addToolBar(tb)

        def act(text, slot, tip="", key=None, checkable=False):
            a = QAction(text, self)
            a.setToolTip(tip or text)
            a.setCheckable(checkable)
            if key:
                a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("打开文件", self.choose_file, "打开一个 md 文件（同文件夹的 md 自动排成章节）  Ctrl+O", "Ctrl+O")
        act("打开文件夹", self.choose_folder, "打开文件夹，里面所有 md 排成章节")
        tb.addSeparator()
        act("◀ 上一章", self.prev_chapter, "上一章  Ctrl+PgUp", "Ctrl+PgUp")
        act("下一章 ▶", self.next_chapter, "下一章  Ctrl+PgDown", "Ctrl+PgDown")
        self.act_all = act("全部连读", self.toggle_all, "勾选：所有章节连成一页往下翻；不勾：一次只看一章",
                           checkable=True)
        self.act_all.setChecked(self.all_mode)
        tb.addSeparator()
        act("A-", lambda: self.change_fs(-1), "字体变小  Ctrl+-", "Ctrl+-")
        act("A+", lambda: self.change_fs(+1), "字体变大  Ctrl+=", "Ctrl+=")
        self.act_dark = act("深色", self.toggle_dark, "深色 / 浅色背景", checkable=True)
        self.act_dark.setChecked(self.dark)
        act("刷新", self.reload_from_disk, "重新读取文件  F5", "F5")

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        self.find_box = QLineEdit()
        self.find_box.setPlaceholderText("查找（回车下一个，Shift+回车上一个）")
        self.find_box.setFixedWidth(260)
        self.find_box.setClearButtonEnabled(True)
        self.find_box.returnPressed.connect(self.find_next)
        self.find_box.textChanged.connect(lambda t: self.page.findText(t))
        tb.addWidget(self.find_box)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.find_box.setFocus(), self.find_box.selectAll()))
        QShortcut(QKeySequence("Shift+Return"), self.find_box,
                  activated=lambda: self.page.findText(self.find_box.text(), QWebEnginePage.FindBackward))
        QShortcut(QKeySequence("Escape"), self.find_box,
                  activated=lambda: (self.find_box.clear(), self.view.setFocus()))

        self.path_label = QLabel()
        self.path_label.setStyleSheet("color:#666;padding:0 6px;")
        self.statusBar().addWidget(self.path_label, 1)

    def find_next(self):
        self.page.findText(self.find_box.text())

    # ---------- 打开
    def choose_file(self):
        start = self.folder or self.settings.value("last_dir", "")
        p, _ = QFileDialog.getOpenFileName(self, "打开 Markdown 文件", start,
                                           "Markdown 文件 (*.md *.markdown *.mdown *.mkd);;所有文件 (*.*)")
        if p:
            self.open_path(p)

    def choose_folder(self):
        start = self.folder or self.settings.value("last_dir", "")
        p = QFileDialog.getExistingDirectory(self, "打开包含 md 文件的文件夹", start)
        if p:
            self.open_path(p)

    def open_dropped(self, paths):
        md_files = [p for p in paths if os.path.isfile(p)]
        if len(md_files) > 1:
            # 拖进来好几个 md：就把这几个当章节
            self.load_file_list(sorted(md_files, key=chapter_sort_key), "（拖入的 %d 个文件）" % len(md_files), 0)
        else:
            self.open_path(paths[0])

    def open_path(self, path, fragment=""):
        path = os.path.normpath(path)
        if os.path.isdir(path):
            files = list_md_files(path)
            if not files:
                QMessageBox.information(self, APP_NAME, "这个文件夹里没有 md 文件：\n" + path)
                return
            self.load_file_list(files, path, 0)
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, APP_NAME, "找不到文件：\n" + path)
            return
        folder = os.path.dirname(path)
        if path in self.files and self.folder == folder:
            self.go_chapter(self.files.index(path), fragment)
            return
        files = list_md_files(folder)
        if path not in files:
            files.append(path)
        self.load_file_list(files, folder, files.index(path), fragment)

    def load_file_list(self, files, folder, index, fragment=""):
        self.files = files
        self.folder = folder
        self.chapters = {}
        self.cur = index
        if os.path.isdir(folder):
            self.settings.setValue("last_dir", folder)
        self.settings.setValue("last_path", files[index])
        self.parse_all()
        self.rebuild_tree()
        self.watch()
        self.render(self.fragment_js(index, fragment))

    def parse_all(self):
        for i, p in enumerate(self.files):
            c = self.chapters.get(p)
            try:
                mtime = os.path.getmtime(p)
                if c is None or c.mtime != mtime or c.index != i:
                    self.chapters[p] = Chapter(p, i)
            except OSError:
                self.chapters.pop(p, None)
        self.files = [p for p in self.files if p in self.chapters]
        self.cur = max(0, min(self.cur, len(self.files) - 1))

    def watch(self):
        old = self.watcher.files() + self.watcher.directories()
        if old:
            self.watcher.removePaths(old)
        paths = list(self.files)
        if os.path.isdir(self.folder):
            paths.append(self.folder)
        if paths:
            self.watcher.addPaths(paths)

    def reload_from_disk(self):
        if not self.files:
            return
        if os.path.isdir(self.folder) and self.folder != "" and not self.folder.startswith("（"):
            cur_path = self.files[self.cur] if self.files else None
            new_files = list_md_files(self.folder)
            for p in self.files:  # 用户单独打开的、不在列表里的文件保留
                if p not in new_files and os.path.isfile(p):
                    new_files.append(p)
            self.files = new_files
            if cur_path in self.files:
                self.cur = self.files.index(cur_path)
        self.parse_all()
        if not self.files:
            self.tree.clear()
            self.show_welcome()
            return
        self.rebuild_tree()
        self.watch()
        # 保留滚动位置
        self.page.runJavaScript("window.scrollY", lambda y: self.render("window.scrollTo(0,%d)" % int(y or 0)))

    # ---------- 目录
    def rebuild_tree(self):
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        self.tree_items = []
        for i, p in enumerate(self.files):
            c = self.chapters[p]
            top = QTreeWidgetItem([c.title])
            top.setFont(0, bold)
            top.setToolTip(0, p)
            top.setData(0, Qt.UserRole, (i, ""))
            self.tree.addTopLevelItem(top)
            self.tree_items.append(top)
            stack = [(0, top)]
            heads = c.headings[1:] if c.title_from_h1 else c.headings
            for level, text, eid in heads:
                if level > 3:
                    continue
                while len(stack) > 1 and stack[-1][0] >= level:
                    stack.pop()
                it = QTreeWidgetItem([text])
                it.setToolTip(0, text)
                it.setData(0, Qt.UserRole, (i, eid))
                stack[-1][1].addChild(it)
                stack.append((level, it))
        self.select_tree(self.cur)

    def select_tree(self, i):
        if 0 <= i < len(getattr(self, "tree_items", [])):
            item = self.tree_items[i]
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(item)
            if not self.all_mode:
                for j, it in enumerate(self.tree_items):
                    it.setExpanded(j == i)
            self.tree.blockSignals(False)
            self.tree.scrollToItem(item)
        self.update_titles()

    def on_tree_click(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        i, eid = data
        js = ("goId(%r)" % eid) if eid else ("document.getElementById('ch-%d').scrollIntoView()" % i
                                              if self.all_mode else "window.scrollTo(0,0)")
        if self.all_mode or i == self.cur:
            self.cur = i
            self.page.runJavaScript(js)
            self.update_titles()
        else:
            self.cur = i
            self.select_tree(i)
            self.render(js)

    def update_titles(self):
        if not self.files:
            self.setWindowTitle(APP_NAME)
            self.path_label.setText("")
            return
        c = self.chapters[self.files[self.cur]]
        self.setWindowTitle("%s - %s" % (c.title, APP_NAME))
        self.path_label.setText("第 %d / %d 章    %s" % (self.cur + 1, len(self.files), c.path))

    # ---------- 章节切换
    def fragment_js(self, i, fragment):
        if fragment:
            return "jumpSlug(%d, %r)" % (i, fragment)
        if self.all_mode:
            return "document.getElementById('ch-%d').scrollIntoView()" % i
        return None

    def go_chapter(self, i, fragment=""):
        if not self.files or not (0 <= i < len(self.files)):
            return
        self.cur = i
        self.select_tree(i)
        js = self.fragment_js(i, fragment)
        if self.all_mode:
            self.page.runJavaScript(js)
        else:
            self.render(js)

    def prev_chapter(self):
        self.go_chapter(self.cur - 1)

    def next_chapter(self):
        self.go_chapter(self.cur + 1)

    def toggle_all(self, on):
        self.all_mode = on
        self.settings.setValue("all_mode", on)
        if self.files:
            self.select_tree(self.cur)
            self.render(self.fragment_js(self.cur, ""))

    # ---------- 外观
    def change_fs(self, d):
        self.fs = max(10, min(40, self.fs + d))
        self.settings.setValue("font_size", self.fs)
        self.page.runJavaScript("setFs(%d)" % self.fs)

    def toggle_dark(self, on):
        self.dark = on
        self.settings.setValue("dark", on)
        self.page.setBackgroundColor(QColor("#1e1f22" if on else "#ffffff"))
        self.page.runJavaScript("setDark(%s)" % ("true" if on else "false"))

    # ---------- 渲染
    def chapter_section(self, i):
        c = self.chapters[self.files[i]]
        label = ""
        if self.all_mode and len(self.files) > 1:
            label = '<div class="chapter-file">第 %d 章 · %s</div>' % (i + 1, htmlmod.escape(os.path.basename(c.path)))
        return '<section class="chapter" id="ch-%d" data-ch="%d">%s%s</section>' % (i, i, label, c.html)

    def nav_html(self):
        def link(cond, what, text):
            return ('<a onclick="nav(\'%s\')">%s</a>' % (what, text)) if cond else '<span class="off">%s</span>' % text
        prev_t = next_t = ""
        if self.cur > 0:
            prev_t = "：" + htmlmod.escape(self.chapters[self.files[self.cur - 1]].title)
        if self.cur < len(self.files) - 1:
            next_t = "：" + htmlmod.escape(self.chapters[self.files[self.cur + 1]].title)
        return '<div class="navbar">%s%s</div>' % (
            link(self.cur > 0, "prev", "← 上一章" + prev_t),
            link(self.cur < len(self.files) - 1, "next", "下一章" + next_t + " →"))

    def build_page(self, body, base_dir):
        base = QUrl.fromLocalFile(base_dir.rstrip("\\/") + "/").toString(QUrl.FullyEncoded) if base_dir else ""
        return (PAGE.replace("__PYG__", PYG_LIGHT + "\n" + PYG_DARK)
                .replace("__BASE__", base)
                .replace("__TITLE__", "")
                .replace("__FS__", str(self.fs))
                .replace("__THEME__", "dark" if self.dark else "")
                .replace("__BODY__", body))

    def render(self, js=None):
        if not self.files:
            self.show_welcome()
            return
        if self.all_mode:
            body = "\n".join(self.chapter_section(i) for i in range(len(self.files)))
        else:
            body = self.chapter_section(self.cur)
            if len(self.files) > 1:
                body += self.nav_html()
        self.load_html(self.build_page(body, os.path.dirname(self.files[self.cur])), js)

    def show_welcome(self):
        self.load_html(self.build_page(WELCOME, ""), None)
        self.update_titles()

    def load_html(self, page_html, js):
        self.pending_js = js
        self.page_seq = (self.page_seq + 1) % 2  # 两个文件轮换，避免读写冲突
        out = os.path.join(self.cache_dir, "view%d.html" % self.page_seq)
        with open(out, "w", encoding="utf-8") as f:
            f.write(page_html)
        self.page.setBackgroundColor(QColor("#1e1f22" if self.dark else "#ffffff"))
        self.view.load(QUrl.fromLocalFile(out))

    def on_load_finished(self, ok):
        js = self.pending_js
        self.pending_js = None
        if ok:
            self.page.runJavaScript("setDark(%s);setFs(%d)" % ("true" if self.dark else "false", self.fs))
        if ok and js:
            self.page.runJavaScript(js)
        if ok and self.all_mode:
            self.page.runJavaScript("setTimeout(track, 50)")

    def on_title_changed(self, title):
        if title.startswith("nav:"):
            what = title.split(":")[1]
            self.prev_chapter() if what == "prev" else self.next_chapter()
        elif title.startswith("ch:") and self.all_mode:
            try:
                i = int(title[3:])
            except ValueError:
                return
            if 0 <= i < len(self.files) and i != self.cur:
                self.cur = i
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(self.tree_items[i])
                self.tree.blockSignals(False)
                self.update_titles()

    def closeEvent(self, ev):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(ev)


def main():
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-logging")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    win = MainWindow()
    win.show()
    target = next((a for a in sys.argv[1:] if os.path.exists(a)), None)
    if target is None:
        last = win.settings.value("last_path", "")
        if last and os.path.exists(last):
            target = last
    if target:
        win.open_path(target)
    else:
        win.show_welcome()
    snap = os.environ.get("MDV_SNAPSHOT")  # 测试用：自动截图后退出
    if snap:
        QTimer.singleShot(int(os.environ.get("MDV_SNAPSHOT_DELAY", "3000")),
                          lambda: (win.grab().save(snap), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
