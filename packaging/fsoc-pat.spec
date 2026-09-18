# -*- mode: python -*-
# PyInstaller spec for the FSOC-PAT standalone application.
#
# Build (from the repository root):
#   Windows:  packaging\build.bat
#   Linux:    packaging/build.sh
#
# One folder rather than one file: onefile unpacks a few hundred megabytes of
# Qt to a temp directory on every launch, which reads as "the demo is frozen"
# on a judge's laptop. Onedir starts instantly and zips just as small.
import pathlib

root = pathlib.Path(SPECPATH).parent

a = Analysis(
    [str(root / "src" / "fsoc_pat" / "__main__.py")],
    pathex=[str(root / "src")],
    datas=[
        (str(root / "scenarios"), "scenarios"),
        (str(root / "models"), "models"),
    ],
    hiddenimports=[
        "fsoc_pat.gui.app",
        "pyqtgraph",
        "PySide6.QtSvg",
    ],
    excludes=[
        # Qt ships far more than a single-window app uses.
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D",
        "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.QtDesigner",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors",
        "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtSql",
        "tkinter", "matplotlib",
    ],
    noarchive=False,
)
# opencv-python ships its own Qt: if its plugins dir is bundled it shadows
# PySide6's platform plugins and the GUI dies on launch ("could not load the
# Qt platform plugin"). Strip cv2's Qt entirely — fsoc_pat uses cv2 only for
# image ops, never its GUI.
a.binaries = [b for b in a.binaries if "cv2/qt" not in b[0].replace("\\", "/")]
a.datas = [d for d in a.datas if "cv2/qt" not in d[0].replace("\\", "/")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts,
    exclude_binaries=True,
    name="fsoc-pat",
    console=False,          # GUI app; --headless still works from a terminal
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="fsoc-pat")
