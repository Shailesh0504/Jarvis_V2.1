#!/usr/bin/env python3
# setup.py
"""
Setup & Deployment Orchestrator for JARVIS V2.1.
================================================
Enables one-command setup, dependency configuration, database initialization,
portable launcher generation, and packaging for any Windows PC.

Dual-Mode Architecture:
1. Direct Runner Mode (Fresh System / User Installation):
   - python setup.py             (Full automated setup wizard)
   - python setup.py --check     (System & dependency health diagnostics)
   - python setup.py --install   (Install pip dependencies automatically)
   - python setup.py --init-db   (Initialize SQLite database and schema)
   - python setup.py --launchers (Generate portable Windows .bat launchers)

2. Standard Setuptools / Pip Mode (Packaging & Virtualenv):
   - pip install .
   - pip install -e .
   - python setup.py develop
   - python setup.py install
   - python setup.py bdist_wheel
"""

import os
import sys
import subprocess
import platform
from typing import List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_FILE = os.path.join(PROJECT_ROOT, "requirements.txt")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIO_CACHE_DIR = os.path.join(DATA_DIR, "audio_cache")


def get_requirements() -> List[str]:
    """Reads non-comment requirements from requirements.txt."""
    if not os.path.exists(REQUIREMENTS_FILE):
        return []
    reqs = []
    with open(REQUIREMENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("#"):
                reqs.append(cleaned)
    return reqs


def get_package_name_from_req(req: str) -> str:
    """Extracts base package name from requirement line (e.g. 'PySide6>=6.5.0' -> 'pyside6')."""
    import re
    m = re.match(r"^([a-zA-Z0-9_\-\.]+)", req)
    return m.group(1).lower().replace("-", "_") if m else req.lower()


# ==============================================================================
# SECTION 1: WIZARD & ENVIRONMENT DEPLOYMENT LOGIC
# ==============================================================================

def print_banner() -> None:
    banner = """
======================================================================
     JARVIS V2.1 - AUTONOMOUS AI ASSISTANT SETUP & DEPLOYMENT
======================================================================
"""
    print(banner)


def check_python_environment() -> bool:
    """Verifies Python version and architecture."""
    py_version = sys.version_info
    print(f"[*] Python Version: {py_version.major}.{py_version.minor}.{py_version.micro} ({platform.architecture()[0]})")
    print(f"[*] Operating System: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"[*] Project Location: {PROJECT_ROOT}")

    if py_version < (3, 10):
        print("[!] ERROR: JARVIS requires Python 3.10 or higher.")
        print("    Please install Python 3.10+ from https://www.python.org/downloads/")
        return False

    is_venv = sys.prefix != sys.base_prefix
    if is_venv:
        print(f"[+] Virtual Environment: Active ({sys.prefix})")
    else:
        print("[*] Virtual Environment: None detected (Using global/system Python).")
        venv_path = os.path.join(PROJECT_ROOT, ".venv")
        if os.path.exists(venv_path):
            print(f"    Notice: A local virtual environment exists at '{venv_path}'.")
            print(f"    You can activate it with: .\\.venv\\Scripts\\Activate.ps1")
    return True


def ensure_directories() -> None:
    """Creates required data and runtime directories."""
    dirs = [DATA_DIR, LOGS_DIR, AUDIO_CACHE_DIR]
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
            print(f"[+] Created directory: {os.path.relpath(d, PROJECT_ROOT)}")
        else:
            print(f"[+] Verified directory: {os.path.relpath(d, PROJECT_ROOT)}")


def ensure_config() -> None:
    """Verifies default config.yaml is present."""
    config_path = os.path.join(PROJECT_ROOT, "config.yaml")
    if os.path.exists(config_path):
        print(f"[+] Configuration file verified: config.yaml")
    else:
        print(f"[!] Warning: config.yaml not found at {config_path}. Default configurations will be loaded at runtime.")


def initialize_database() -> bool:
    """Pre-initializes the SQLite database and schema."""
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from memory.database import DatabaseManager
        db_path = os.path.join(DATA_DIR, "jarvis.db")
        db = DatabaseManager(db_path=db_path)
        # Run a test query to verify integrity
        db.execute_query("SELECT 1")
        print(f"[+] SQLite database schema initialized: {os.path.relpath(db_path, PROJECT_ROOT)}")
        return True
    except Exception as e:
        print(f"[!] Database initialization note: {e} (Will auto-initialize on first launch)")
        return False


def check_installed_packages() -> Tuple[List[str], List[str]]:
    """Checks which requirements are satisfied vs missing."""
    import importlib.metadata
    reqs = get_requirements()
    installed = []
    missing = []

    # Map package names that differ in importlib metadata
    canonical_map = {
        "pyyaml": "yaml",
        "opencv_python": "cv2",
        "pillow": "PIL",
        "pypdf": "pypdf",
        "speechrecognition": "speech_recognition",
    }

    for req in reqs:
        pkg_name = get_package_name_from_req(req)
        try:
            importlib.metadata.version(pkg_name.replace("_", "-"))
            installed.append(req)
        except importlib.metadata.PackageNotFoundError:
            # Secondary check: can it be imported?
            import_name = canonical_map.get(pkg_name, pkg_name)
            try:
                __import__(import_name)
                installed.append(req)
            except ImportError:
                missing.append(req)

    return installed, missing


def install_dependencies(upgrade_pip: bool = True) -> bool:
    """Installs required packages from requirements.txt using pip."""
    print("\n[*] Checking dependencies...")
    installed, missing = check_installed_packages()

    if not missing:
        print(f"[+] All {len(installed)} required packages are already installed!")
        return True

    print(f"[*] Found {len(installed)} installed packages, {len(missing)} missing packages.")
    print(f"[*] Installing dependencies from requirements.txt...")

    if upgrade_pip:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
        except Exception:
            pass

    # Ensure setuptools and wheel are installed for building packages
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "setuptools", "wheel"], check=False)
    except Exception:
        pass

    cmd = [sys.executable, "-m", "pip", "install", "-r", REQUIREMENTS_FILE]
    try:
        res = subprocess.run(cmd)
        if res.returncode == 0:
            print("[+] Successfully installed all dependencies!")
            return True
        else:
            print(f"[!] Warning: pip exited with return code {res.returncode}.")
            return False
    except Exception as e:
        print(f"[!] Error installing dependencies: {e}")
        return False


def create_portable_launchers() -> None:
    """Generates portable Windows launchers using dynamic relative paths."""
    # 1. Main GUI Launcher
    run_gui_bat = os.path.join(PROJECT_ROOT, "run_jarvis.bat")
    gui_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "title JARVIS V2.1\r\n"
        "cd /d \"%~dp0\"\r\n"
        "if exist \"%~dp0.venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0.venv\\Scripts\\python.exe\"\r\n"
        ") else if exist \"%~dp0venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0venv\\Scripts\\python.exe\"\r\n"
        ") else (\r\n"
        "    set \"PYTHON_CMD=python\"\r\n"
        ")\r\n"
        "\"%PYTHON_CMD%\" main.py %*\r\n"
        "if %ERRORLEVEL% neq 0 (\r\n"
        "    echo.\r\n"
        "    echo [!] Jarvis exited with code %ERRORLEVEL%.\r\n"
        "    pause\r\n"
        ")\r\n"
        "endlocal\r\n"
    )
    with open(run_gui_bat, "w", encoding="utf-8") as f:
        f.write(gui_content)
    print(f"[+] Generated portable GUI launcher: run_jarvis.bat")

    # 2. Interactive CLI Launcher
    run_cli_bat = os.path.join(PROJECT_ROOT, "run_jarvis_cli.bat")
    cli_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "title JARVIS V2.1 - Interactive CLI\r\n"
        "cd /d \"%~dp0\"\r\n"
        "if exist \"%~dp0.venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0.venv\\Scripts\\python.exe\"\r\n"
        ") else if exist \"%~dp0venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0venv\\Scripts\\python.exe\"\r\n"
        ") else (\r\n"
        "    set \"PYTHON_CMD=python\"\r\n"
        ")\r\n"
        "\"%PYTHON_CMD%\" main.py --cli %*\r\n"
        "endlocal\r\n"
    )
    with open(run_cli_bat, "w", encoding="utf-8") as f:
        f.write(cli_content)
    print(f"[+] Generated portable CLI launcher: run_jarvis_cli.bat")

    # 3. No-Auth Quick Launcher (Bypasses biometric face auth for testing)
    run_no_auth_bat = os.path.join(PROJECT_ROOT, "run_jarvis_no_auth.bat")
    no_auth_content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "title JARVIS V2.1 - GUI (No Auth)\r\n"
        "cd /d \"%~dp0\"\r\n"
        "if exist \"%~dp0.venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0.venv\\Scripts\\python.exe\"\r\n"
        ") else if exist \"%~dp0venv\\Scripts\\python.exe\" (\r\n"
        "    set \"PYTHON_CMD=%~dp0venv\\Scripts\\python.exe\"\r\n"
        ") else (\r\n"
        "    set \"PYTHON_CMD=python\"\r\n"
        ")\r\n"
        "\"%PYTHON_CMD%\" main.py --no-auth %*\r\n"
        "endlocal\r\n"
    )
    with open(run_no_auth_bat, "w", encoding="utf-8") as f:
        f.write(no_auth_content)
    print(f"[+] Generated portable dev launcher: run_jarvis_no_auth.bat")

    # 4. Update tools/start_jarvis.bat with dynamic paths
    tools_start_bat = os.path.join(PROJECT_ROOT, "tools", "start_jarvis.bat")
    if os.path.exists(os.path.dirname(tools_start_bat)):
        tools_content = (
            "@echo off\r\n"
            "setlocal\r\n"
            "rem Dynamic startup launcher for Windows Startup folder\r\n"
            "for %%I in (\"%~dp0..\") do set \"JARVIS_ROOT=%%~fI\"\r\n"
            "if exist \"%JARVIS_ROOT%\\.venv\\Scripts\\pythonw.exe\" (\r\n"
            "    set \"JARVIS_PYTHON=%JARVIS_ROOT%\\.venv\\Scripts\\pythonw.exe\"\r\n"
            ") else (\r\n"
            "    set \"JARVIS_PYTHON=pythonw.exe\"\r\n"
            ")\r\n"
            "set \"JARVIS_MAIN=%JARVIS_ROOT%\\main.py\"\r\n"
            "cd /d \"%JARVIS_ROOT%\"\r\n"
            "start \"Jarvis V2\" /min \"%JARVIS_PYTHON%\" \"%JARVIS_MAIN%\"\r\n"
            "endlocal\r\n"
        )
        with open(tools_start_bat, "w", encoding="utf-8") as f:
            f.write(tools_content)
        print(f"[+] Updated dynamic startup launcher: tools/start_jarvis.bat")


def run_diagnostics() -> bool:
    """Runs a health check on core subsystems."""
    print("\n[*] Running Core Health Diagnostics...")
    all_ok = True

    checks = [
        ("PySide6 GUI Framework", "from PySide6 import QtCore, QtWidgets"),
        ("PyYAML Configuration", "import yaml"),
        ("psutil Process & System", "import psutil"),
        ("RapidFuzz String Matching", "import rapidfuzz"),
        ("pyttsx3 Offline TTS", "import pyttsx3"),
        ("edge-tts Neural TTS", "import edge_tts"),
        ("SpeechRecognition STT", "import speech_recognition"),
        ("Pygame Audio Engine", "import pygame"),
        ("Core Application Subsystems", "from core.app import JarvisCore"),
    ]

    sys.path.insert(0, PROJECT_ROOT)
    for name, imp_stmt in checks:
        try:
            exec(imp_stmt, {})
            print(f"  [PASS] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            all_ok = False

    return all_ok


def run_full_setup() -> None:
    """Executes the complete setup workflow."""
    print_banner()

    # 1. Environment check
    if not check_python_environment():
        sys.exit(1)

    # 2. Directories
    print("\n[*] Initializing storage directories...")
    ensure_directories()
    ensure_config()

    # 3. Dependencies
    install_dependencies(upgrade_pip=True)

    # 4. Database
    print("\n[*] Checking database schema...")
    initialize_database()

    # 5. Launchers
    print("\n[*] Generating portable launchers...")
    create_portable_launchers()

    # 6. Diagnostics
    diag_ok = run_diagnostics()

    print("\n" + "=" * 70)
    if diag_ok:
        print(" [SUCCESS] JARVIS V2.1 is fully configured and ready to run!")
    else:
        print(" [NOTE] Setup completed with warnings. Some optional modules may need attention.")
    print("=" * 70)
    print("\nHow to launch Jarvis:")
    print("  1. Modern GUI Interface:        run_jarvis.bat  (or python main.py)")
    print("  2. Interactive CLI Mode:        run_jarvis_cli.bat  (or python main.py --cli)")
    print("  3. Bypass Face Authentication:  run_jarvis_no_auth.bat  (or python main.py --no-auth)")
    print("  4. Run Test Suite:              pytest tests/ -v\n")


# ==============================================================================
# SECTION 2: STANDARD SETUPTOOLS INTEGRATION
# ==============================================================================

SETUPTOOLS_COMMANDS = {
    "install", "develop", "bdist_wheel", "sdist", "build",
    "egg_info", "dist_info", "clean", "check", "--editable"
}

def is_setuptools_invoked() -> bool:
    """Detects whether pip or a developer invoked standard setuptools commands."""
    if len(sys.argv) > 1:
        first_arg = sys.argv[1].lower()
        if first_arg in SETUPTOOLS_COMMANDS or any(arg in SETUPTOOLS_COMMANDS for arg in sys.argv[1:]):
            return True
        if first_arg.startswith("-") and first_arg not in ("--setup", "--install", "--check", "--init-db", "--launchers"):
            return True
    return False


def run_setuptools_setup() -> None:
    """Executes standard setuptools packaging."""
    try:
        import setuptools
        from setuptools import setup, find_packages
    except ImportError:
        print("[*] Installing setuptools...")
        subprocess.run([sys.executable, "-m", "pip", "install", "setuptools"], check=True)
        import setuptools
        from setuptools import setup, find_packages

    reqs = get_requirements()

    setup(
        name="jarvis-assistant",
        version="2.1.0",
        description="JARVIS V2.1 - Autonomous Local AI Voice & Desktop Assistant",
        author="Jarvis Team",
        python_requires=">=3.10",
        packages=find_packages(exclude=["tests*", "scratch*"]),
        include_package_data=True,
        package_data={
            "": ["*.yaml", "*.json", "*.bat", "*.ico", "*.png", "*.txt"],
        },
        install_requires=reqs,
        entry_points={
            "console_scripts": [
                "jarvis=main:main",
                "jarvis-assistant=main:main",
            ],
        },
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Intended Audience :: End Users/Desktop",
            "Operating System :: Microsoft :: Windows",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Topic :: Desktop Environment",
            "Topic :: Scientific/Engineering :: Artificial Intelligence",
        ],
    )


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def main():
    if is_setuptools_invoked():
        run_setuptools_setup()
        return

    # Handle custom flags
    if len(sys.argv) > 1:
        flag = sys.argv[1].lower()
        if flag in ("--check", "check"):
            print_banner()
            check_python_environment()
            ensure_directories()
            run_diagnostics()
            return
        elif flag in ("--install", "install-deps"):
            install_dependencies()
            return
        elif flag in ("--init-db", "init-db"):
            ensure_directories()
            initialize_database()
            return
        elif flag in ("--launchers", "launchers"):
            create_portable_launchers()
            return

    # Default: Full Setup Wizard
    run_full_setup()


if __name__ == "__main__":
    main()
