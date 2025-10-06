"""
EDGE Security Module - Защита от MITM атак
"""

from .mitm_protection import (
    CertificateManager,
    SecureHTTPSClient,
    MITMDetector,
    create_mitm_protected_client,
    SecurityError
)

from .mutual_tls import (
    CertificateAuthority,
    MutualTLSClient,
    MTLSAdapter,
    setup_device_mtls
)

__all__ = [
    'CertificateManager',
    'SecureHTTPSClient', 
    'MITMDetector',
    'create_mitm_protected_client',
    'SecurityError',
    'CertificateAuthority',
    'MutualTLSClient',
    'MTLSAdapter', 
    'setup_device_mtls'
]