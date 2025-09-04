#!/usr/bin/env python3
"""
Complete deduplication script for CUBE_RS.
Handles remaining duplicated files identified by tests.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple, Dict

# Additional duplicated files found by tests
ADDITIONAL_DUPLICATES = [
    # Dashboard files
    ("deploy_gateway/modbus/dashboard_reader.py", "modbus/dashboard_reader.py"),
    
    # Tools - these are deployment-specific, so we'll create lightweight wrappers
    ("deploy_webapp/tools/init_telegram_db.py", "tools/init_telegram_db.py"),
    ("deploy_webapp/tools/certificate_manager_cli.py", "tools/certificate_manager_cli.py"),
    ("deploy_webapp/tools/production_cli.py", "tools/production_cli.py"),
    ("deploy_webapp/tools/start_all_services.py", "tools/start_all_services.py"),
    ("deploy_webapp/tools/admin_cli.py", "tools/admin_cli.py"),
    ("deploy_webapp/tools/stop_all_services.py", "tools/stop_all_services.py"),
    ("deploy_webapp/tools/production_audit.py", "tools/production_audit.py"),
    ("deploy_webapp/tools/create_base_db.py", "tools/create_base_db.py"),
    
    # Monitoring
    ("deploy_server/monitoring/network_security_monitor.py", "monitoring/network_security_monitor.py"),
    ("deploy_server/monitoring/security_monitor.py", "monitoring/security_monitor.py"),
    
    # Web app production specific
    ("deploy_webapp/web_app/production_device_registry.py", "web_app/production_device_registry.py"),
    
    # Gateway auto registration 
    ("deploy_gateway/gateway/auto_registration_client.py", "gateway/auto_registration_client.py"),
]

def create_tool_wrapper(deploy_file: Path, original_file: Path) -> None:
    """Create a lightweight wrapper for deployment tools."""
    if not original_file.exists():
        print(f"   ⚠️  Original tool not found: {original_file}, keeping deploy version")
        return
    
    # Create a wrapper that imports and runs the original
    wrapper_content = f'''#!/usr/bin/env python3
"""
Deployment wrapper for {original_file.name}
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
        from tools.{original_file.stem} import main
        main()
    except ImportError:
        # Fallback: run original script directly
        import subprocess
        result = subprocess.run([
            sys.executable, 
            str(project_root / "{original_file}")
        ], cwd=project_root)
        sys.exit(result.returncode)
'''
    
    # Backup original deploy file
    backup_dir = Path("backup_duplicated_modules")
    backup_path = backup_dir / deploy_file
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if deploy_file.exists():
        shutil.copy2(deploy_file, backup_path)
        print(f"   📦 Backed up: {deploy_file}")
    
    # Write wrapper
    deploy_file.parent.mkdir(parents=True, exist_ok=True)
    with open(deploy_file, 'w', encoding='utf-8') as f:
        f.write(wrapper_content)
    
    # Make executable
    deploy_file.chmod(0o755)
    print(f"   🔗 Created wrapper: {deploy_file}")

def create_simple_alias(deploy_file: Path, original_file: Path) -> None:
    """Create a simple import alias."""
    if not original_file.exists():
        print(f"   ⚠️  Original file not found: {original_file}, keeping deploy version")
        return
        
    # Get import path
    import_path = str(original_file.with_suffix('')).replace(os.sep, '.')
    
    alias_content = f'''"""
Alias for {original_file}
"""
from {import_path} import *  # noqa: F403,F401
'''
    
    # Backup and replace
    backup_dir = Path("backup_duplicated_modules")
    backup_path = backup_dir / deploy_file
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if deploy_file.exists():
        shutil.copy2(deploy_file, backup_path)
        print(f"   📦 Backed up: {deploy_file}")
    
    deploy_file.parent.mkdir(parents=True, exist_ok=True)
    with open(deploy_file, 'w', encoding='utf-8') as f:
        f.write(alias_content)
    
    print(f"   🔗 Created alias: {deploy_file}")

def handle_special_cases() -> None:
    """Handle special cases that need custom logic."""
    # Fix webapp api_gateway alias to handle flask dependency gracefully
    webapp_api_alias = Path("deploy_webapp/web_app/api_gateway.py")
    if webapp_api_alias.exists():
        improved_alias = '''"""
API Gateway alias with graceful flask handling
"""
try:
    from web_app.api_gateway import *  # noqa: F403,F401
except ImportError as e:
    if "flask" in str(e).lower():
        # Flask not available - provide stub
        def create_app(*args, **kwargs):
            raise RuntimeError("Flask not available in this environment")
        
        __all__ = ['create_app']
    else:
        raise
'''
        with open(webapp_api_alias, 'w', encoding='utf-8') as f:
            f.write(improved_alias)
        print("   🔧 Fixed webapp API gateway alias")

def main():
    """Main deduplication completion process."""
    print("🔄 Completing CUBE_RS module deduplication...")
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"📂 Working directory: {project_root}")
    
    # Handle additional duplicates
    for deploy_path, original_path in ADDITIONAL_DUPLICATES:
        deploy_file = Path(deploy_path)
        original_file = Path(original_path)
        
        if not deploy_file.exists():
            print(f"   ⏭️  Already handled: {deploy_path}")
            continue
        
        print(f"   Processing: {deploy_path} -> {original_path}")
        
        # Tools get wrappers, everything else gets aliases
        if "tools/" in deploy_path:
            create_tool_wrapper(deploy_file, original_file)
        else:
            create_simple_alias(deploy_file, original_file)
    
    # Handle special cases
    handle_special_cases()
    
    print("✅ Deduplication completion finished!")
    print("🧪 Run tests to verify everything works correctly")

if __name__ == "__main__":
    main()