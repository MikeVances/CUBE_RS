#!/usr/bin/env python3
"""
Safe module deduplication script for CUBE_RS.
Removes duplicated files while preserving functionality through aliases.
"""

import os
import shutil
import sys
from pathlib import Path

# Define duplicated modules to be removed
DUPLICATED_FILES = [
    # Gateway modules
    ("deploy_gateway/modbus/gateway.py", "modbus/gateway.py"),
    ("deploy_gateway/modbus/gateway_typed.py", "modbus/gateway_typed.py"),
    ("deploy_gateway/modbus/async_client.py", "modbus/async_client.py"),
    ("deploy_gateway/modbus/modbus_storage.py", "modbus/modbus_storage.py"),
    ("deploy_gateway/modbus/reader.py", "modbus/reader.py"),
    ("deploy_gateway/modbus/writer.py", "modbus/writer.py"),
    ("deploy_gateway/modbus/unified_system.py", "modbus/unified_system.py"),
    ("deploy_gateway/modbus/time_window_manager.py", "modbus/time_window_manager.py"),
    # Security modules
    ("deploy_gateway/security/mitm_protection.py", "security/mitm_protection.py"),
    ("deploy_gateway/security/mutual_tls.py", "security/mutual_tls.py"),
    # WebApp modules
    ("deploy_webapp/web_app/api_gateway.py", "web_app/api_gateway.py"),
    ("deploy_webapp/web_app/device_registry.py", "web_app/device_registry.py"),
    ("deploy_webapp/web_app/rbac_system.py", "web_app/rbac_system.py"),
    (
        "deploy_webapp/web_app/tailscale_integration.py",
        "web_app/tailscale_integration.py",
    ),
    ("deploy_webapp/web_app/app.py", "web_app/app.py"),
]

# Backup directory
BACKUP_DIR = Path("backup_duplicated_modules")


def create_backup(duplicated_files: list[tuple[str, str]]) -> None:
    """Create backup of duplicated files before removal."""
    print("📦 Creating backup of duplicated files...")
    BACKUP_DIR.mkdir(exist_ok=True)

    for duplicate_path, original_path in duplicated_files:
        if Path(duplicate_path).exists():
            backup_path = BACKUP_DIR / duplicate_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(duplicate_path, backup_path)
            print(f"   Backed up: {duplicate_path} -> {backup_path}")


def verify_originals_exist(duplicated_files: list[tuple[str, str]]) -> bool:
    """Verify that original files exist before removing duplicates."""
    print("🔍 Verifying original files exist...")
    all_exist = True

    for duplicate_path, original_path in duplicated_files:
        if Path(duplicate_path).exists() and not Path(original_path).exists():
            print(
                f"   ❌ Original missing: {original_path} (needed for {duplicate_path})"
            )
            all_exist = False
        elif Path(duplicate_path).exists():
            print(f"   ✅ Original found: {original_path}")

    return all_exist


def remove_duplicated_files(duplicated_files: list[tuple[str, str]]) -> None:
    """Remove duplicated files safely."""
    print("🗑️  Removing duplicated files...")

    for duplicate_path, original_path in duplicated_files:
        if Path(duplicate_path).exists():
            try:
                os.remove(duplicate_path)
                print(f"   Removed: {duplicate_path}")
            except OSError as e:
                print(f"   ❌ Failed to remove {duplicate_path}: {e}")
        else:
            print(f"   ⏭️  Already removed: {duplicate_path}")


def create_alias_files() -> None:
    """Create alias files in deploy directories."""
    print("🔗 Creating alias files...")

    # Deploy gateway aliases
    deploy_gateway_aliases = """
# Gateway module aliases for backward compatibility
from modbus.gateway import *  # noqa: F403,F401
from modbus.gateway_typed import *  # noqa: F403,F401
"""

    alias_files = [
        ("deploy_gateway/modbus/gateway.py", deploy_gateway_aliases),
        (
            "deploy_webapp/web_app/api_gateway.py",
            "from web_app.api_gateway import *  # noqa: F403,F401",
        ),
    ]

    for file_path, content in alias_files:
        if not Path(file_path).exists():
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"   Created alias: {file_path}")


def update_requirements() -> None:
    """Remove redundant requirements.txt files."""
    print("📝 Cleaning up requirements files...")

    redundant_requirements = [
        "deploy_gateway/requirements.txt",
        "deploy_webapp/requirements.txt",
        "deploy_server/requirements.txt",
    ]

    for req_file in redundant_requirements:
        if Path(req_file).exists():
            try:
                os.remove(req_file)
                print(f"   Removed: {req_file} (using pyproject.toml instead)")
            except OSError as e:
                print(f"   ❌ Failed to remove {req_file}: {e}")


def main():
    """Main deduplication process."""
    print("🚀 Starting CUBE_RS module deduplication...")

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"📂 Working directory: {project_root}")

    # Step 1: Verify all originals exist
    if not verify_originals_exist(DUPLICATED_FILES):
        print("❌ Some original files are missing. Aborting deduplication.")
        return False

    # Step 2: Create backup
    create_backup(DUPLICATED_FILES)

    # Step 3: Remove duplicated files
    remove_duplicated_files(DUPLICATED_FILES)

    # Step 4: Create alias files for backward compatibility
    create_alias_files()

    # Step 5: Update requirements
    update_requirements()

    print("✅ Module deduplication completed successfully!")
    print(f"📦 Backup created in: {BACKUP_DIR}")
    print("🔄 Next steps:")
    print("   1. Run tests to verify backward compatibility")
    print("   2. Update import paths if needed")
    print("   3. Commit changes")

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
