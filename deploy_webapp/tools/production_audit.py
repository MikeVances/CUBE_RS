#!/usr/bin/env python3
"""
Deployment wrapper for production_audit.py
Imports and runs the original tool with deployment-specific setup.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import and run original tool
if __name__ == "__main__":
    try:
        from tools.production_audit import main
        main()
    except ImportError:
        # Fallback: run original script directly
        import subprocess
        result = subprocess.run([
            sys.executable, 
            str(project_root / "tools/production_audit.py")
        ], cwd=project_root)
        sys.exit(result.returncode)
