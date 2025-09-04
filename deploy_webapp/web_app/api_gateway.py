"""
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
