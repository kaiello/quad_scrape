import os
import sys


def pytest_configure():
    # Ensure project 'src' is importable as 'combo'
    root = os.path.dirname(os.path.abspath(__file__))
    proj = os.path.dirname(root)
    src = os.path.join(proj, "src")
    if src not in sys.path:
        sys.path.insert(0, src)

