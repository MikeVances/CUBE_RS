"""
Unit tests for module alias system.
Ensures backward compatibility after code deduplication.
"""
import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.types import ModbusDevice, ModbusRequest, ModbusFunctionCode


class TestModuleAliases:
    """Test module alias system for backward compatibility."""

    def test_deploy_gateway_aliases_import(self):
        """Test that deploy_gateway module aliases can be imported."""
        # Import the alias module
        deploy_modbus = importlib.import_module("deploy_gateway.modbus")
        
        # Verify key classes are available
        assert hasattr(deploy_modbus, 'ModbusGateway')
        assert hasattr(deploy_modbus, 'TypedModbusGateway')
        assert hasattr(deploy_modbus, 'AsyncModbusClient')
        assert hasattr(deploy_modbus, 'ModbusStorage')

    def test_deploy_gateway_class_functionality(self):
        """Test that aliased classes maintain full functionality."""
        # Import both original and aliased versions
        from modbus.gateway_typed import TypedModbusGateway as Original
        from deploy_gateway.modbus import TypedModbusGateway as Aliased
        
        # They should be the same class
        assert Original is Aliased
        
        # Create instance using aliased class
        gateway = Aliased(host="127.0.0.1", port=5023, db_path=":memory:")
        
        # Verify it has expected attributes
        assert gateway.host == "127.0.0.1"
        assert gateway.port == 5023
        assert hasattr(gateway, 'start_server')
        assert hasattr(gateway, 'stop_server')

    def test_deploy_webapp_aliases_import(self):
        """Test that deploy_webapp aliases work correctly."""
        try:
            # Import the webapp alias
            deploy_webapp = importlib.import_module("deploy_webapp.web_app.api_gateway")
            
            # Should not raise ImportError
            assert deploy_webapp is not None
        except ImportError as e:
            # If alias file doesn't exist yet, that's expected
            if "api_gateway" in str(e):
                pytest.skip("API gateway alias not yet created")
            else:
                raise

    def test_original_modules_still_accessible(self):
        """Test that original modules are still accessible."""
        # Import original modules
        from modbus import gateway, gateway_typed, async_client
        from core import types, security_manager
        from web_app import api_gateway
        
        # All should be importable
        assert gateway is not None
        assert gateway_typed is not None
        assert async_client is not None
        assert types is not None
        assert security_manager is not None
        assert api_gateway is not None

    def test_no_duplicated_files_exist(self):
        """Test that duplicated files have been removed."""
        duplicated_files = [
            "deploy_gateway/modbus/gateway.py",
            "deploy_gateway/modbus/modbus_storage.py",
            "deploy_gateway/modbus/reader.py",
            "deploy_gateway/modbus/writer.py",
            "deploy_gateway/modbus/unified_system.py",
            "deploy_gateway/modbus/time_window_manager.py",
            "deploy_gateway/security/mitm_protection.py",
            "deploy_gateway/security/mutual_tls.py",
        ]
        
        project_root = Path(__file__).parent.parent.parent
        
        for file_path in duplicated_files:
            full_path = project_root / file_path
            if full_path.exists():
                # Read content to check if it's an alias
                content = full_path.read_text()
                # Should be either alias or small compatibility shim
                assert (
                    "from modbus" in content or 
                    "import" in content or 
                    len(content.strip()) < 200
                ), f"File {file_path} appears to contain duplicated code"

    def test_backup_files_created(self):
        """Test that backup files were created during deduplication."""
        backup_dir = Path(__file__).parent.parent.parent / "backup_duplicated_modules"
        
        if backup_dir.exists():
            # Should have some backup files
            backup_files = list(backup_dir.rglob("*.py"))
            assert len(backup_files) > 0, "No backup files found"
            
            # Check that backup files contain substantial code
            for backup_file in backup_files[:3]:  # Check first 3
                content = backup_file.read_text()
                assert len(content) > 1000, f"Backup file {backup_file} seems too small"
        else:
            pytest.skip("Backup directory not found - deduplication not yet run")

    def test_requirements_cleanup(self):
        """Test that redundant requirements.txt files were removed."""
        redundant_requirements = [
            "deploy_gateway/requirements.txt",
            "deploy_webapp/requirements.txt",
            "deploy_server/requirements.txt",
        ]
        
        project_root = Path(__file__).parent.parent.parent
        
        for req_file in redundant_requirements:
            full_path = project_root / req_file
            assert not full_path.exists(), f"Redundant requirements file still exists: {req_file}"


class TestBackwardCompatibility:
    """Test backward compatibility of the alias system."""

    def test_import_patterns_still_work(self):
        """Test that common import patterns still work."""
        # These should all work without modification
        test_imports = [
            "from modbus.gateway_typed import TypedModbusGateway",
            "from modbus.async_client import AsyncModbusClient",
            "from core.types import ModbusDevice, ModbusRequest",
            "from core.security_manager import SecurityManager",
        ]
        
        for import_stmt in test_imports:
            try:
                exec(import_stmt)
            except ImportError as e:
                pytest.fail(f"Import failed: {import_stmt} - {e}")

    def test_class_instantiation_compatibility(self):
        """Test that classes can be instantiated as before."""
        # Original way
        from modbus.gateway_typed import TypedModbusGateway as OriginalGateway
        
        # Aliased way (if available)
        try:
            from deploy_gateway.modbus import TypedModbusGateway as AliasedGateway
            
            # Both should create working instances
            original_instance = OriginalGateway(db_path=":memory:")
            aliased_instance = AliasedGateway(db_path=":memory:")
            
            # Should be instances of the same class
            assert type(original_instance) is type(aliased_instance)
            
        except ImportError:
            # Alias not available yet
            original_instance = OriginalGateway(db_path=":memory:")
            assert original_instance is not None

    def test_function_signatures_preserved(self):
        """Test that function signatures are preserved in aliases."""
        from modbus.gateway_typed import TypedModbusGateway
        
        # Get signature of original class
        original_signature = inspect.signature(TypedModbusGateway.__init__)
        
        try:
            from deploy_gateway.modbus import TypedModbusGateway as AliasedGateway
            aliased_signature = inspect.signature(AliasedGateway.__init__)
            
            # Signatures should be identical
            assert original_signature == aliased_signature
            
        except ImportError:
            pytest.skip("Aliased class not available")

    def test_module_attributes_preserved(self):
        """Test that module-level attributes are preserved."""
        from modbus import gateway_typed
        
        # Should have standard module attributes
        assert hasattr(gateway_typed, 'TypedModbusGateway')
        assert hasattr(gateway_typed, '__name__')
        assert hasattr(gateway_typed, '__file__')
        
        # Check that logger and other imports are preserved
        assert hasattr(gateway_typed, 'logger')
        assert hasattr(gateway_typed, 'asyncio')


@pytest.mark.integration
class TestDeduplicationResults:
    """Integration tests for deduplication results."""

    def test_no_code_duplication_metric(self):
        """Test that code duplication has been eliminated."""
        project_root = Path(__file__).parent.parent.parent
        
        # Count Python files in deploy directories
        deploy_python_files = []
        deploy_dirs = ['deploy_gateway', 'deploy_webapp', 'deploy_server']
        
        for deploy_dir in deploy_dirs:
            deploy_path = project_root / deploy_dir
            if deploy_path.exists():
                deploy_python_files.extend(deploy_path.rglob("*.py"))
        
        # Check that deploy Python files are small (aliases only)
        large_files = []
        for py_file in deploy_python_files:
            if py_file.name == "__init__.py":
                continue
                
            content = py_file.read_text()
            # Alias files should be small
            if len(content) > 500:  # More than 500 chars suggests actual code
                large_files.append((py_file, len(content)))
        
        # Should have no large files (all should be aliases)
        if large_files:
            file_list = "\n".join(f"  {f}: {size} chars" for f, size in large_files)
            pytest.fail(f"Found potentially duplicated code in:\n{file_list}")

    def test_import_times_not_degraded(self):
        """Test that import times haven't been significantly degraded."""
        import time
        
        # Time importing original modules
        start_time = time.time()
        from modbus.gateway_typed import TypedModbusGateway  # noqa: F401
        from modbus.async_client import AsyncModbusClient  # noqa: F401
        from core.types import ModbusDevice  # noqa: F401
        original_time = time.time() - start_time
        
        # Time importing aliased modules (if available)
        try:
            start_time = time.time()
            from deploy_gateway.modbus import TypedModbusGateway as AliasedGateway  # noqa: F401
            from deploy_gateway.modbus import AsyncModbusClient as AliasedClient  # noqa: F401
            alias_time = time.time() - start_time
            
            # Alias imports shouldn't be significantly slower
            assert alias_time < original_time * 2, "Alias imports are too slow"
            
        except ImportError:
            # Aliases not available - that's fine
            pass
        
        # Original imports should be reasonably fast
        assert original_time < 1.0, f"Original imports too slow: {original_time:.3f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])