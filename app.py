"""MARUTI Application Entry Point.

Convenience launcher supporting direct invocation:
    python app.py          # Interactive text mode
    python app.py --gui    # Launch PySide6 GUI
    python app.py --voice  # Launch voice mode
"""
import sys
from main import main

if __name__ == "__main__":
    main()
