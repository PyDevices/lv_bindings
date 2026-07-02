#!/usr/bin/env python3
"""Shell entry point invoked by regenerate_*.sh; delegates to binding.cli."""
from __future__ import print_function

import os
import sys

_LV_BINDINGS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _LV_BINDINGS_DIR)

from binding.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
