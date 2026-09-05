"""
Entry point for the packaged application.

    fsoc-pat                     launch the GUI on the default scenario
    fsoc-pat scenario.yaml       launch the GUI on a scenario
    fsoc-pat --headless s.yaml   run headless and print the performance report
"""
import sys


def main() -> int:
    argv = sys.argv[1:]
    if "--headless" in argv:
        argv.remove("--headless")
        from fsoc_pat.runner import main as headless
        return headless(argv)
    from fsoc_pat.gui.app import main as gui
    return gui(argv)


if __name__ == "__main__":
    raise SystemExit(main())
