"""PyInstaller entry point for the fsoc_pat operator GUI.

app.py itself uses relative imports (it's meant to run as
`python -m fsoc_pat.gui.app`), which breaks when a frozen .exe executes it
directly as __main__. This tiny wrapper imports the package properly instead,
so PyInstaller has something with plain absolute imports to point at.
"""
import sys

from fsoc_pat.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
