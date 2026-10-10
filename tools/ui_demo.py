"""Offline terminal preview: python -m tools.ui_demo [snapshot.html]."""
import sys

from ui import demo


if __name__ == "__main__":
    demo(sys.argv[1] if len(sys.argv) > 1 else None)
