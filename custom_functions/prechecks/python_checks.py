import sys
import os
import subprocess
import venv

def version_check():
    major_version = sys.version_info.major
    minor_version = sys.version_info.minor

    if major_version >= 3:
        if minor_version >= 12:
            return
        else:
            exit("Python version 3.12 or higher is required")
    else:
        exit("Python 2 detected, Python version 3.12 or higher is required")

def pip_check():
    try:
        import pip
        return
    except ImportError:
        exit("Pip is not installed")

def venv_check():
    # hacky fix
    return # skip, this should be run from Docker


    # Check if we're already inside a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        return

    venv_path = os.path.join(os.getcwd(), 'cdrm-venv')
    venv_python = os.path.join(venv_path, 'bin', 'python') if os.name != 'nt' else os.path.join(venv_path, 'Scripts', 'python.exe')

    # If venv already exists, restart script using its Python
    if os.path.exists(venv_path):
        subprocess.call([venv_python] + sys.argv)
        sys.exit()

    # Ask user for permission to create a virtual environment
    answer = ''
    while not answer or answer[0].upper() not in {'Y', 'N'}:
        answer = input(
            'Program is not running from a venv. To maintain compatibility and dependencies, this program must be run from one.\n'
            'Would you like me to create one for you? (Y/N): '
        )

    if answer[0].upper() == 'Y':
        print("Creating virtual environment...")
        venv.create(venv_path, with_pip=True)
        subprocess.call([venv_python] + sys.argv)
        sys.exit()
    else:
        print("Exiting program. Please run it from a virtual environment next time.")
        sys.exit(1)


def requirements_check():
    try:
        import pywidevine
        import pyplayready
        import flask
        import flask_cors
        import yaml
        import mysql.connector
        return
    except ImportError:
        while True:
            user_input = input("Missing packages. Do you want to install them? (Y/N): ").strip().upper()
            if user_input == 'Y':
                print("Installing packages from requirements.txt...")
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
                print("Installation complete.")
                break
            elif user_input == 'N':
                print("Dependencies required, please install them and run again.")
                sys.exit()
            else:
                print("Invalid input. Please enter 'Y' to install or 'N' to exit.")

def run_python_checks():
    if getattr(sys, 'frozen', False):  # Check if running from PyInstaller
        return
    version_check()
    pip_check()
    venv_check()
    requirements_check()