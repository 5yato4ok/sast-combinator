import os
import sys
import pytest

PROJECT_ROOT = os.getenv("PROJECT_ROOT") or os.getcwd()
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)