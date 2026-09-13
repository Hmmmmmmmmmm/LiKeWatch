"""Installed entry point: manager code comes from this installation, not app source."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from likewatch_manager.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
