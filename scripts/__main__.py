#!/usr/bin/env python3
"""Allow running as: python -m skills.ui_audit_pro.scripts.audit full ..."""
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from audit import main

if __name__ == "__main__":
    main()
