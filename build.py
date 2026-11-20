"""打包成 exe：python build.py  →  dist/MDViewer/MDViewer.exe 以及 dist/MDViewer-win64.zip
需要先 pip install -r requirements.txt pyinstaller"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'MDViewer'
DIST = os.path.join(HERE, 'dist')
WORK = os.path.join(HERE, 'build')
KEEP_LOCALES = {'zh-CN.pak', 'zh-TW.pak', 'en-US.pak'}


def make_ico(path):
    """用程序里同一个图标（金色圆角方块 + MD）生成 256px 的 ico。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter, QPainterPath, QColor, QFont
    from PySide6.QtCore import Qt, QRectF
    app = QApplication.instance() or QApplication([])
    img = QImage(256, 256, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    pp = QPainterPath()
    pp.addRoundedRect(QRectF(8, 8, 240, 240), 56, 56)
    p.fillPath(pp, QColor('#C9A227'))
    p.setPen(QColor('white'))
    p.setFont(QFont('Segoe UI', 88, QFont.Bold))
    p.drawText(img.rect(), Qt.AlignCenter, 'MD')
    p.end()
    img.save(path)
    del app


def main():
    ico = os.path.join(HERE, 'md-viewer.ico')
    if not os.path.exists(ico):
        make_ico(ico)
    subprocess.check_call([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--name', NAME, '--icon', ico, '--exclude-module', 'tkinter',
        '--distpath', DIST, '--workpath', WORK, '--specpath', WORK,
        os.path.join(HERE, 'viewer.py')])
    app = os.path.join(DIST, NAME)
    internal = os.path.join(app, '_internal')
    # 网页引擎的界面语言包只留中文和英文
    for p in glob.glob(os.path.join(internal, '**', 'qtwebengine_locales', '*.pak'), recursive=True):
        if os.path.basename(p) not in KEEP_LOCALES:
            os.remove(p)
    # 用不到的：网页开发者工具资源、3D / QML 界面组件、PDF 模块、其他语言翻译
    for pat in (r'PySide6\translations\qt_*.qm', r'PySide6\translations\qtbase_*.qm',
                r'PySide6\resources\qtwebengine_devtools_resources*.pak',
                r'PySide6\Qt6Quick3D*.dll', r'PySide6\Qt6QuickControls2*.dll', r'PySide6\Qt6QuickTemplates2.dll',
                r'PySide6\Qt6QuickDialogs2*.dll', r'PySide6\Qt6QuickShapes.dll', r'PySide6\Qt6ShaderTools.dll',
                r'PySide6\Qt6Pdf*.dll', r'PySide6\plugins\imageformats\qpdf.dll', r'PySide6\qml'):
        for p in glob.glob(os.path.join(internal, pat)):
            if not os.path.basename(p).startswith(('qt_zh', 'qtbase_zh')):
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    zip_base = os.path.join(DIST, f'{NAME}-win64')
    shutil.make_archive(zip_base, 'zip', DIST, NAME)
    print('done:', zip_base + '.zip')


if __name__ == '__main__':
    main()
