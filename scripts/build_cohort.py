#!/usr/bin/env python3
"""Build the cohort-1 database. See scripts/cohort/build.py for the details."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import build

if __name__ == "__main__":
    sys.exit(build.main())
