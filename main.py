import sys
import os
from gui.main_window import MainWindow

# Explicit imports for PyInstaller to detect dynamic imports
# These are not used directly but ensure modules are included in the bundle
if False:  # Never executed, but PyInstaller will scan these
    from impl.jdk import JDKInstaller
    from impl.node import NodeInstaller
    from impl.maven import MavenInstaller
    from impl.redis import RedisInstaller
    from impl.python import PythonInstaller
    from core.env_manager import EnvironmentManager
    from core.history import HistoryManager

def main():
    app = MainWindow()
    app.run()

if __name__ == "__main__":
    main()
