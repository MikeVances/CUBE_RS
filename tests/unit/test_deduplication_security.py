"""
Security tests for module deduplication.
Ensures that the alias system doesn't introduce security vulnerabilities.
"""
import ast
import importlib
import sys
from pathlib import Path
from typing import List, Set

import pytest


class TestDeduplicationSecurity:
    """Test security aspects of the deduplication system."""

    def test_no_arbitrary_code_execution_in_aliases(self):
        """Test that alias files don't contain arbitrary code execution."""
        project_root = Path(__file__).parent.parent.parent
        
        alias_files = [
            "deploy_gateway/modbus/__init__.py",
            "deploy_gateway/modbus/gateway.py",
        ]
        
        for alias_file in alias_files:
            full_path = project_root / alias_file
            if not full_path.exists():
                continue
                
            content = full_path.read_text()
            
            # Parse as AST to check for dangerous constructs
            try:
                tree = ast.parse(content)
            except SyntaxError:
                pytest.fail(f"Invalid syntax in alias file: {alias_file}")
            
            # Check for potentially dangerous constructs
            dangerous_calls = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', '__import__']:
                            dangerous_calls.append(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        if node.func.attr in ['system', 'popen']:
                            dangerous_calls.append(node.func.attr)
            
            assert not dangerous_calls, f"Dangerous calls in {alias_file}: {dangerous_calls}"

    def test_alias_modules_only_import_known_modules(self):
        """Test that alias modules only import from known safe locations."""
        project_root = Path(__file__).parent.parent.parent
        
        # Known safe import prefixes
        safe_imports = {
            'modbus',
            'core', 
            'web_app',
            'telegram_bot',
            'security',
            'monitoring',
            'dashboard'
        }
        
        alias_files = []
        for deploy_dir in ['deploy_gateway', 'deploy_webapp', 'deploy_server']:
            deploy_path = project_root / deploy_dir
            if deploy_path.exists():
                alias_files.extend(deploy_path.rglob("*.py"))
        
        for alias_file in alias_files:
            if alias_file.name == "__init__.py" and len(alias_file.read_text().strip()) == 0:
                continue  # Skip empty __init__.py files
                
            content = alias_file.read_text()
            
            # Parse imports
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue  # Skip files with syntax issues
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        module_name = node.module.split('.')[0]
                        if module_name not in safe_imports:
                            # Check if it's a standard library import
                            if module_name in sys.stdlib_module_names:
                                continue  # Standard library is safe
                            
                            pytest.fail(
                                f"Unsafe import in {alias_file}: {node.module}"
                            )

    def test_no_file_system_operations_in_aliases(self):
        """Test that alias files don't perform file system operations."""
        project_root = Path(__file__).parent.parent.parent
        
        alias_files = []
        for deploy_dir in ['deploy_gateway', 'deploy_webapp', 'deploy_server']:
            deploy_path = project_root / deploy_dir
            if deploy_path.exists():
                alias_files.extend(deploy_path.rglob("*.py"))
        
        for alias_file in alias_files:
            content = alias_file.read_text()
            
            # Check for file operations
            dangerous_patterns = [
                'open(',
                'file(',
                'os.system',
                'subprocess',
                'shutil.',
                'os.remove',
                'os.rmdir',
                'os.unlink',
                'pathlib.Path.unlink',
                'pathlib.Path.rmdir',
            ]
            
            for pattern in dangerous_patterns:
                assert pattern not in content, \
                    f"Dangerous file operation in {alias_file}: {pattern}"

    def test_backup_files_not_in_python_path(self):
        """Test that backup files are not accessible via Python imports."""
        project_root = Path(__file__).parent.parent.parent
        backup_dir = project_root / "backup_duplicated_modules"
        
        if not backup_dir.exists():
            pytest.skip("Backup directory not found")
        
        # Backup directory should not be in Python path
        backup_str = str(backup_dir.absolute())
        for path in sys.path:
            assert backup_str not in path, \
                "Backup directory is in Python path - security risk"
        
        # Test that backup modules can't be imported
        backup_modules = [
            "backup_duplicated_modules.deploy_gateway.modbus.gateway",
            "backup_duplicated_modules.deploy_webapp.web_app.app",
        ]
        
        for module_name in backup_modules:
            with pytest.raises(ImportError):
                importlib.import_module(module_name)

    def test_alias_files_have_correct_permissions(self):
        """Test that alias files have appropriate file permissions."""
        project_root = Path(__file__).parent.parent.parent
        
        alias_files = []
        for deploy_dir in ['deploy_gateway', 'deploy_webapp', 'deploy_server']:
            deploy_path = project_root / deploy_dir
            if deploy_path.exists():
                alias_files.extend(deploy_path.rglob("*.py"))
        
        for alias_file in alias_files:
            stat_info = alias_file.stat()
            mode = stat_info.st_mode & 0o777
            
            # Should be readable by owner and group, not world-writable
            assert mode & 0o044 != 0, f"File not readable: {alias_file}"
            assert mode & 0o002 == 0, f"File is world-writable: {alias_file}"

    def test_no_secrets_in_alias_files(self):
        """Test that alias files don't contain hardcoded secrets."""
        project_root = Path(__file__).parent.parent.parent
        
        alias_files = []
        for deploy_dir in ['deploy_gateway', 'deploy_webapp', 'deploy_server']:
            deploy_path = project_root / deploy_dir
            if deploy_path.exists():
                alias_files.extend(deploy_path.rglob("*.py"))
        
        # Common secret patterns
        secret_patterns = [
            r'password\s*=\s*["\'][^"\']+["\']',
            r'token\s*=\s*["\'][^"\']+["\']',
            r'key\s*=\s*["\'][^"\']+["\']',
            r'secret\s*=\s*["\'][^"\']+["\']',
            r'api_key\s*=\s*["\'][^"\']+["\']',
        ]
        
        import re
        
        for alias_file in alias_files:
            content = alias_file.read_text()
            
            for pattern in secret_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Skip obvious placeholders
                    if any(placeholder in match.lower() for placeholder in 
                           ['placeholder', 'example', 'your_', 'xxx', '***', 'test']):
                        continue
                    
                    pytest.fail(f"Potential secret in {alias_file}: {match}")


class TestAliasSystemIntegrity:
    """Test integrity of the alias system."""

    def test_circular_imports_prevented(self):
        """Test that alias system doesn't create circular imports."""
        # Try importing various combinations
        import_combinations = [
            ("modbus.gateway", "deploy_gateway.modbus"),
            ("core.types", "modbus.gateway_typed"),
            ("web_app.api_gateway", "deploy_webapp.web_app.api_gateway"),
        ]
        
        for original, alias_module in import_combinations:
            try:
                # Clear any cached imports
                if original in sys.modules:
                    del sys.modules[original]
                if alias_module in sys.modules:
                    del sys.modules[alias_module]
                
                # Import in both orders
                importlib.import_module(original)
                try:
                    importlib.import_module(alias_module)
                except ImportError:
                    # Alias might not exist yet
                    continue
                
                # Should not raise RecursionError or similar
                assert True  # If we get here, no circular import
                
            except RecursionError:
                pytest.fail(f"Circular import detected: {original} <-> {alias_module}")

    def test_alias_consistency(self):
        """Test that aliases are consistent with original modules."""
        # Test known aliases
        alias_mapping = {
            'deploy_gateway.modbus.ModbusGateway': 'modbus.gateway.ModbusGateway',
            'deploy_gateway.modbus.TypedModbusGateway': 'modbus.gateway_typed.TypedModbusGateway',
            'deploy_gateway.modbus.AsyncModbusClient': 'modbus.async_client.AsyncModbusClient',
        }
        
        for alias_path, original_path in alias_mapping.items():
            try:
                # Get original class
                original_module, original_class = original_path.rsplit('.', 1)
                original_obj = getattr(
                    importlib.import_module(original_module), 
                    original_class
                )
                
                # Get aliased class
                alias_module, alias_class = alias_path.rsplit('.', 1) 
                try:
                    alias_obj = getattr(
                        importlib.import_module(alias_module),
                        alias_class
                    )
                    
                    # Should be the same object
                    assert original_obj is alias_obj, \
                        f"Alias inconsistency: {alias_path} != {original_path}"
                        
                except ImportError:
                    # Alias might not be implemented yet
                    continue
                    
            except ImportError:
                # Original might not exist
                continue

    def test_memory_usage_not_excessive(self):
        """Test that alias system doesn't cause excessive memory usage."""
        import gc
        import tracemalloc
        
        # Start memory tracking
        tracemalloc.start()
        
        # Import original modules
        from modbus import gateway_typed, async_client  # noqa: F401
        from core import types, security_manager  # noqa: F401
        
        # Get baseline memory
        gc.collect()
        current, peak = tracemalloc.get_traced_memory()
        baseline_memory = current
        
        # Import aliases (if available)
        try:
            from deploy_gateway import modbus  # noqa: F401
            
            # Memory shouldn't increase significantly
            gc.collect()
            current, peak = tracemalloc.get_traced_memory()
            alias_memory = current
            
            # Allow up to 50% increase (aliases should be lightweight)
            memory_increase = alias_memory - baseline_memory
            assert memory_increase < baseline_memory * 0.5, \
                f"Excessive memory usage from aliases: {memory_increase} bytes"
                
        except ImportError:
            # Aliases not available yet
            pass
        
        tracemalloc.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])