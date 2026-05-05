"""`python -m scry` entry — delegates to the CLI dispatcher."""
from __future__ import annotations

import sys

from scry.cli import main


if __name__ == "__main__":
    sys.exit(main())
