#!/usr/bin/env python3

from setuptools import setup, find_packages
import os

# Читаем README
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Читаем requirements
def read_requirements():
    requirements = []
    if os.path.exists("requirements.txt"):
        with open("requirements.txt", "r", encoding="utf-8") as fh:
            requirements = [line.strip() for line in fh 
                          if line.strip() and not line.startswith("#")]
    return requirements

setup(
    name="stienen-rs485-gateway",
    version="1.0.0",
    author="Stienen Gateway Team",
    author_email="team@company.com",
    description="RS485 Gateway for Stienen Controllers - Python Migration from C#/.NET",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/company/stienen-gateway",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Manufacturing",
        "Topic :: System :: Hardware",
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", 
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Framework :: AsyncIO",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "pylint>=2.17.0",
            "mypy>=1.5.0",
            "pre-commit>=3.3.0",
        ],
        "web": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.23.0",
            "websockets>=11.0",
        ],
        "mqtt": [
            "paho-mqtt>=1.6.0",
            "asyncio-mqtt>=0.13.0",
        ],
        "database": [
            "asyncpg>=0.28.0",
            "sqlalchemy>=2.0.0",
        ],
        "monitoring": [
            "prometheus-client>=0.17.0",
            "psutil>=5.9.0",
            "coloredlogs>=15.0",
        ],
        "all": [
            "fastapi>=0.100.0",
            "uvicorn[standard]>=0.23.0",
            "websockets>=11.0",
            "paho-mqtt>=1.6.0",
            "asyncio-mqtt>=0.13.0",
            "asyncpg>=0.28.0",
            "sqlalchemy>=2.0.0",
            "prometheus-client>=0.17.0",
            "psutil>=5.9.0",
            "coloredlogs>=15.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "stienen-gateway=main:main",
            "stienen-web=web_interface:run_web_interface",
            "stienen-monitor=monitoring_utilities:main",
            "stienen-test=tests.test_protocol:main",
        ],
    },
    include_package_data=True,
    package_data={
        "stienen": [
            "config/*.json",
            "templates/*.html",
            "static/css/*.css",
            "static/js/*.js",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/company/stienen-gateway/issues",
        "Source": "https://github.com/company/stienen-gateway",
        "Documentation": "https://stienen-gateway.readthedocs.io/",
    },
    keywords="rs485 stienen gateway industrial automation scada iot modbus",
    platforms=["any"],
    zip_safe=False,
)
