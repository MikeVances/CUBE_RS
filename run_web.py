#!/usr/bin/env python3
"""
Startup script for CUBE_RS Web Interface
"""

import uvicorn
from web_interface.main import app
from web_interface.config import config

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        log_level=config.LOG_LEVEL.lower()
    )