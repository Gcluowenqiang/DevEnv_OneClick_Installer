import os
import sys
import shutil
from core.env_manager import EnvironmentManager

class PythonInstaller(EnvironmentManager):
    def __init__(self):
        super().__init__()
        self.env_var_name = "PYTHON_HOME"
        # Using Python Embeddable Zip packages
        # These are lightweight and don't require admin rights, perfect for our "green" install philosophy.
        # However, they need extra config to enable pip.
        self.versions = {
            "Python 3.12.1": {
                "version": "3.12.1",
                "url": "https://www.python.org/ftp/python/3.12.1/python-3.12.1-embed-amd64.zip"
            },
            "Python 3.11.7": {
                "version": "3.11.7",
                "url": "https://www.python.org/ftp/python/3.11.7/python-3.11.7-embed-amd64.zip"
            },
            "Python 3.10.11": {
                "version": "3.10.11",
                "url": "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
            },
            "Python 3.9.13": {
                "version": "3.9.13",
                "url": "https://www.python.org/ftp/python/3.9.13/python-3.9.13-embed-amd64.zip"
            },
            "Python 3.8.10": {
                "version": "3.8.10",
                "url": "https://www.python.org/ftp/python/3.8.10/python-3.8.10-embed-amd64.zip"
            }
        }
        self.get_pip_url = "https://bootstrap.pypa.io/get-pip.py"

    def get_version_list(self):
        return list(self.versions.keys())

    def install(self, version_name, install_path, progress_callback=None, extra_config=None):
        if version_name not in self.versions:
            raise ValueError(f"Unknown version: {version_name}")
            
        info = self.versions[version_name]
        version = info['version']
        url = info['url']
        filename = f"python-{version}-embed-amd64.zip"
        
        self.logger.info(f"Preparing to install Python {version}...")

        # 1. Download Python Embed Zip
        self.logger.info("Step 1/5: Downloading Python...")
        if progress_callback: progress_callback(10)
        
        zip_path = self.download_file(url, filename, lambda p: progress_callback(10 + int(p * 0.2))) # 10-30%
        
        # 2. Extract
        self.logger.info("Step 2/5: Extracting files...")
        if progress_callback: progress_callback(30)
        
        python_home = os.path.join(install_path, f"Python-{version}")
        if not os.path.exists(python_home):
            os.makedirs(python_home)
            
        self.extract_zip(zip_path, python_home, lambda p: progress_callback(30 + int(p * 0.2))) # 30-50%
        
        # 3. Configure .pth file to allow pip/site-packages
        # By default, embeddable python ignores site-packages unless we modify python3xx._pth
        self.logger.info("Step 3/5: Configuring Python environment...")
        if progress_callback: progress_callback(50)
        
        self._enable_site_packages(python_home, version)
        
        # 4. Install pip
        self.logger.info("Step 4/5: Installing pip...")
        if progress_callback: progress_callback(60)
        
        self._install_pip(python_home, lambda p: progress_callback(60 + int(p * 0.2))) # 60-80%
        
        # 5. Configure Environment
        self.logger.info("Step 5/5: Updating PATH...")
        if progress_callback: progress_callback(85)
        
        self.sys_config.set_env_variable("PYTHON_HOME", python_home)
        
        # Add python_home and Scripts to PATH
        if not self.sys_config.add_to_path(python_home):
             self.logger.warning("Failed to add Python to PATH")
             
        scripts_path = os.path.join(python_home, "Scripts")
        if not self.sys_config.add_to_path(scripts_path):
             self.logger.warning("Failed to add Python Scripts to PATH")

        if progress_callback: progress_callback(100)
        self.logger.info(f"Python {version} installed successfully!")

    def _enable_site_packages(self, python_home, version):
        """
        Modify python3xx._pth to uncomment 'import site'
        This is required for pip to work and install packages to Lib/site-packages
        """
        # File is named python311._pth, python310._pth etc.
        major_minor = version.split('.')[0] + version.split('.')[1] # 3.11.7 -> 311
        pth_file = os.path.join(python_home, f"python{major_minor}._pth")
        
        if os.path.exists(pth_file):
            try:
                with open(pth_file, 'r') as f:
                    content = f.read()
                
                # Uncomment 'import site'
                if "#import site" in content:
                    content = content.replace("#import site", "import site")
                    with open(pth_file, 'w') as f:
                        f.write(content)
                    self.logger.info("Enabled 'import site' in .pth file")
                elif "import site" not in content:
                    # Append if missing (unlikely in official embed zip but safety check)
                    with open(pth_file, 'a') as f:
                        f.write("\nimport site")
            except Exception as e:
                self.logger.error(f"Failed to modify .pth file: {e}")
        else:
            self.logger.warning(f"Could not find .pth file at {pth_file}")

    def _install_pip(self, python_home, progress_callback=None):
        """Download get-pip.py and run it"""
        get_pip_path = self.download_file(self.get_pip_url, "get-pip.py", progress_callback)
        
        python_exe = os.path.join(python_home, "python.exe")
        if not os.path.exists(python_exe):
            raise Exception("python.exe not found")
            
        import subprocess
        try:
            # Run: python.exe get-pip.py
            # We use --no-warn-script-location because we handle PATH manually
            cmd = [python_exe, get_pip_path, "--no-warn-script-location"]
            
            # Create process without showing window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Pip installation failed: {stderr}")
                raise Exception("Pip installation failed")
                
            self.logger.info("Pip installed successfully.")
            
        except Exception as e:
            self.logger.error(f"Error running get-pip.py: {e}")
            raise e

    def uninstall(self, install_path, progress_callback=None):
        # First, try to find the actual Python root directory
        python_home = None
        
        # Check if the provided path is already a Python root
        if os.path.exists(os.path.join(install_path, "python.exe")):
            python_home = install_path
        elif os.path.exists(install_path) and (os.path.exists(os.path.join(install_path, "Scripts")) or os.path.exists(os.path.join(install_path, "Lib"))):
            # Looks like a Python directory even without python.exe (incomplete install)
            python_home = install_path
            self.logger.warning("python.exe not found, but directory looks like a Python install. Proceeding.")
        else:
            # Try to find Python in subdirectories (common case after extraction)
            self.logger.info(f"Path {install_path} is not Python root, searching for Python in subdirectories...")
            for root, dirs, files in os.walk(install_path):
                if "python.exe" in files:
                    python_home = root
                    break
            
            # If still not found, check PYTHON_HOME environment variable
            if not python_home:
                python_home_env = self.sys_config.get_env_variable("PYTHON_HOME")
                if python_home_env and os.path.normpath(python_home_env).startswith(os.path.normpath(install_path)):
                    if os.path.exists(python_home_env):
                        python_home = python_home_env
                        self.logger.info(f"Found Python via PYTHON_HOME: {python_home}")
        
        if not python_home:
            raise Exception(f"Selected directory is not a valid Python installation (python.exe not found in {install_path} or subdirectories).")

        self.logger.info(f"Uninstalling Python from {python_home}...")
        if progress_callback: progress_callback(10)

        python_home_env = self.sys_config.get_env_variable("PYTHON_HOME")
        if python_home_env:
            python_home_env_normalized = os.path.normpath(python_home_env)
            python_home_normalized = os.path.normpath(python_home)
            if python_home_env_normalized == python_home_normalized:
                self.sys_config.remove_env_variable("PYTHON_HOME")
        
        self.sys_config.remove_from_path(python_home)
        self.sys_config.remove_from_path(os.path.join(python_home, "Scripts"))

        if progress_callback: progress_callback(50)
        
        # Remove the Python directory
        self.remove_directory(python_home)
        
        # If Python was in a subdirectory of install_path, try to remove empty parent directories
        if python_home != install_path:
            try:
                current_dir = os.path.dirname(python_home)
                install_path_normalized = os.path.normpath(install_path)
                
                while current_dir and os.path.normpath(current_dir) != install_path_normalized:
                    if os.path.exists(current_dir):
                        try:
                            if not os.listdir(current_dir):
                                os.rmdir(current_dir)
                                self.logger.info(f"Removed empty directory: {current_dir}")
                                current_dir = os.path.dirname(current_dir)
                            else:
                                break
                        except Exception as e:
                            self.logger.warning(f"Could not remove directory {current_dir}: {e}")
                            break
                    else:
                        break
                
                if os.path.exists(install_path) and not os.listdir(install_path):
                    try:
                        os.rmdir(install_path)
                        self.logger.info(f"Removed empty install directory: {install_path}")
                    except Exception as e:
                        self.logger.warning(f"Could not remove install directory: {e}")
            except Exception as e:
                self.logger.warning(f"Error cleaning up parent directories: {e}")
        
        if progress_callback: progress_callback(100)
        self.logger.info("Python uninstalled successfully.")
