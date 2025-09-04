#!/usr/bin/env python3
"""
Validation script for code deduplication.
Ensures deduplication is maintained and no new duplicates are introduced.
"""

import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
import hashlib


def get_file_hash(file_path: Path) -> str:
    """Get SHA256 hash of file content."""
    with open(file_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def find_large_deploy_files(threshold: int = 1000) -> List[Tuple[Path, int]]:
    """Find deployment files larger than threshold (potential duplicates)."""
    large_files = []
    
    deploy_dirs = ['deploy_gateway', 'deploy_webapp', 'deploy_server']
    for deploy_dir in deploy_dirs:
        deploy_path = Path(deploy_dir)
        if deploy_path.exists():
            for py_file in deploy_path.rglob("*.py"):
                if py_file.name == "__init__.py":
                    continue
                
                size = py_file.stat().st_size
                if size > threshold:
                    large_files.append((py_file, size))
    
    return large_files


def check_duplicate_content() -> Dict[str, List[Path]]:
    """Check for files with identical content."""
    hash_to_files: Dict[str, List[Path]] = {}
    
    # Check all Python files
    for py_file in Path('.').rglob("*.py"):
        # Skip backup directory
        if 'backup_duplicated_modules' in str(py_file):
            continue
        
        # Skip __pycache__ and other build artifacts
        if '__pycache__' in str(py_file) or '.pytest_cache' in str(py_file):
            continue
        
        # Skip symlinks (they're expected)
        if py_file.is_symlink():
            continue
        
        try:
            file_hash = get_file_hash(py_file)
            if file_hash not in hash_to_files:
                hash_to_files[file_hash] = []
            hash_to_files[file_hash].append(py_file)
        except (IOError, OSError):
            continue
    
    # Return only hashes with multiple files, excluding expected duplicates
    duplicates = {}
    for file_hash, files in hash_to_files.items():
        if len(files) > 1:
            # Filter out expected duplicates
            main_files = []
            deploy_files = []
            
            for f in files:
                if str(f).startswith(('deploy_gateway/', 'deploy_webapp/', 'deploy_server/')):
                    deploy_files.append(f)
                else:
                    main_files.append(f)
            
            # Only report if we have duplicates within the same category
            # or if deploy files are too large (indicating they're not aliases)
            problematic = False
            if len(main_files) > 1:
                problematic = True  # Multiple originals
            elif deploy_files:
                # Check if deploy files are suspiciously large
                for df in deploy_files:
                    if df.stat().st_size > 2000:  # Larger than expected for alias
                        problematic = True
                        break
            
            if problematic:
                duplicates[file_hash] = files
    
    return duplicates


def validate_alias_imports() -> List[str]:
    """Validate that alias files only contain imports."""
    errors = []
    
    deploy_dirs = ['deploy_gateway', 'deploy_webapp', 'deploy_server']
    for deploy_dir in deploy_dirs:
        deploy_path = Path(deploy_dir)
        if deploy_path.exists():
            for py_file in deploy_path.rglob("*.py"):
                if py_file.stat().st_size > 2000:  # Large files should be investigated
                    errors.append(f"Large file in deploy directory: {py_file} ({py_file.stat().st_size} bytes)")
                
                # Check that files contain imports/minimal code
                content = py_file.read_text()
                lines = [line.strip() for line in content.split('\n') if line.strip() and not line.strip().startswith('#')]
                
                # Count non-import, non-trivial lines
                significant_lines = 0
                for line in lines:
                    if not (
                        line.startswith('from ') or 
                        line.startswith('import ') or
                        line.startswith('"""') or line.startswith("'''") or
                        line.startswith('__') or
                        line == 'pass' or
                        'noqa' in line or
                        line.startswith('class ') or  # Simple class definitions for wrappers
                        line.startswith('def ') or   # Simple function definitions
                        line.startswith('    ') or   # Indented lines (class/function content)
                        '=' in line and len(line) < 100 or  # Simple assignments
                        line.startswith('__all__') or  # __all__ lists
                        line.startswith('[') or line.startswith(']') or  # List contents
                        line.startswith("'") or line.startswith('"')  # String literals
                    ):
                        significant_lines += 1
                
                # Be more lenient with wrapper files
                threshold = 20 if any(word in py_file.name.lower() for word in ['wrapper', 'tool', 'cli']) else 10
                if significant_lines > threshold:
                    errors.append(f"Potentially duplicated code in: {py_file} ({significant_lines} non-import lines)")
    
    return errors


def calculate_deduplication_stats() -> Dict[str, int]:
    """Calculate deduplication statistics."""
    backup_dir = Path("backup_duplicated_modules")
    
    stats = {
        'backup_files': 0,
        'backup_size': 0,
        'deploy_files': 0,
        'deploy_size': 0,
        'space_saved': 0,
        'percent_saved': 0
    }
    
    if backup_dir.exists():
        backup_files = list(backup_dir.rglob("*.py"))
        stats['backup_files'] = len(backup_files)
        stats['backup_size'] = sum(f.stat().st_size for f in backup_files)
    
    # Count current deploy files
    deploy_dirs = ['deploy_gateway', 'deploy_webapp', 'deploy_server']
    for deploy_dir in deploy_dirs:
        deploy_path = Path(deploy_dir)
        if deploy_path.exists():
            deploy_files = list(deploy_path.rglob("*.py"))
            stats['deploy_files'] += len(deploy_files)
            stats['deploy_size'] += sum(f.stat().st_size for f in deploy_files)
    
    stats['space_saved'] = stats['backup_size'] - stats['deploy_size']
    if stats['backup_size'] > 0:
        stats['percent_saved'] = (stats['space_saved'] * 100) // stats['backup_size']
    
    return stats


def main() -> int:
    """Main validation function."""
    print("🔍 Validating code deduplication...")
    
    errors = []
    warnings = []
    
    # Check for large files in deploy directories
    large_files = find_large_deploy_files(1000)
    if large_files:
        for file_path, size in large_files:
            warnings.append(f"Large deploy file: {file_path} ({size} bytes)")
    
    # Check for duplicate content
    duplicates = check_duplicate_content()
    if duplicates:
        for file_hash, files in duplicates.items():
            if len(files) > 1:
                # Filter out expected duplicates (like empty __init__.py)
                significant_files = [f for f in files if f.stat().st_size > 50]
                if len(significant_files) > 1:
                    errors.append(f"Duplicate content found in: {[str(f) for f in significant_files]}")
    
    # Validate alias imports
    alias_errors = validate_alias_imports()
    errors.extend(alias_errors)
    
    # Calculate stats
    stats = calculate_deduplication_stats()
    
    # Report results
    print(f"\n📊 Deduplication Statistics:")
    print(f"   📦 Backup files: {stats['backup_files']} ({stats['backup_size']:,} bytes)")
    print(f"   🔗 Deploy files: {stats['deploy_files']} ({stats['deploy_size']:,} bytes)")
    print(f"   💾 Space saved: {stats['space_saved']:,} bytes ({stats['percent_saved']}%)")
    
    if warnings:
        print(f"\n⚠️  Warnings ({len(warnings)}):")
        for warning in warnings[:5]:  # Show first 5 warnings
            print(f"   {warning}")
        if len(warnings) > 5:
            print(f"   ... and {len(warnings) - 5} more")
    
    if errors:
        print(f"\n❌ Errors ({len(errors)}):")
        for error in errors[:5]:  # Show first 5 errors
            print(f"   {error}")
        if len(errors) > 5:
            print(f"   ... and {len(errors) - 5} more")
        
        print(f"\n❌ Deduplication validation failed!")
        return 1
    
    print(f"\n✅ Deduplication validation passed!")
    
    # Success thresholds
    if stats['percent_saved'] < 80:
        print(f"⚠️  Warning: Space savings below 80% threshold ({stats['percent_saved']}%)")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())