import os
import shutil
from core.env_manager import EnvironmentManager

class JDKInstaller(EnvironmentManager):
    def __init__(self):
        super().__init__()
        self.env_var_name = "JAVA_HOME"
        # Initial default versions
        self.versions = {
            "JDK 21 (LTS)": 21,
            "JDK 17 (LTS)": 17,
            "JDK 11 (LTS)": 11,
            "JDK 8 (LTS)": 8
        }
        self.api_url = "https://api.adoptium.net/v3/info/available_releases"

    def get_version_list(self):
        try:
            import requests
            self.logger.info("Fetching available JDK versions from Adoptium...")
            response = requests.get(self.api_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            available = data.get('available_releases', [])
            # Sort descending
            available.sort(reverse=True)
            
            # Common LTS versions for highlighting
            lts_versions = [8, 11, 17, 21, 25]
            
            new_versions = {}
            version_keys = []
            
            for v in available:
                if v < 8: continue # Skip very old ones
                name = f"JDK {v}"
                if v in lts_versions:
                    name += " (LTS)"
                new_versions[name] = v
                version_keys.append(name)
                
            if new_versions:
                self.versions = new_versions
                return version_keys
                
        except Exception as e:
            self.logger.warning(f"Failed to fetch JDK versions: {e}. Using default list.")
            
        return list(self.versions.keys())

    def install(self, version_name, install_path, progress_callback=None, extra_config=None):
        version = self.versions.get(version_name)
        if not version:
            raise ValueError(f"Unknown version: {version_name}")

        self.logger.info(f"Preparing to install JDK {version}...")

        # 1. Get Download URL (Using Adoptium API direct binary link)
        # https://api.adoptium.net/v3/binary/latest/{feature_version}/ga/windows/x64/jdk/hotspot/normal/eclipse
        url = f"https://api.adoptium.net/v3/binary/latest/{version}/ga/windows/x64/jdk/hotspot/normal/eclipse"
        filename = f"jdk-{version}-windows-x64.zip"
        
        # 2. Download
        self.logger.info("Step 1/4: Downloading JDK...")
        if progress_callback: progress_callback(10)
        
        zip_path = self.download_file(url, filename, lambda p: progress_callback(10 + int(p * 0.4))) # 10-50%
        
        # 3. Extract
        self.logger.info("Step 2/4: Extracting files...")
        if progress_callback: progress_callback(50)
        
        # Create a temporary extraction path first
        extract_root = self.extract_zip(zip_path, install_path, lambda p: progress_callback(50 + int(p * 0.3))) # 50-80%
        
        # The zip usually contains a root folder like 'jdk-17.0.1+12'. 
        # We need to find it and maybe rename or just point JAVA_HOME there.
        # Let's look for 'bin/javac.exe' to confirm the actual JDK root.
        
        jdk_home = self._find_jdk_home(install_path)
        if not jdk_home:
            # If we extracted to install_path, maybe install_path IS the home?
            if self._is_jdk_root(install_path):
                jdk_home = install_path
            else:
                # Try to find the single directory inside
                items = os.listdir(install_path)
                if len(items) == 1 and os.path.isdir(os.path.join(install_path, items[0])):
                    jdk_home = os.path.join(install_path, items[0])
                else:
                    raise Exception("Could not determine JDK home directory after extraction.")
        
        self.logger.info(f"JDK Home detected at: {jdk_home}")

        # 4. Configure JAVA_HOME
        self.logger.info("Step 3/4: Configuring JAVA_HOME...")
        if progress_callback: progress_callback(85)
        
        if not self.sys_config.set_env_variable("JAVA_HOME", jdk_home):
             raise Exception("Failed to set JAVA_HOME")

        # 5. Configure PATH
        self.logger.info("Step 4/4: Updating PATH...")
        bin_path = os.path.join("%JAVA_HOME%", "bin") 
        # Note: We use %JAVA_HOME% for portability in registry, but some apps might need expanded path.
        # SystemConfig handles generic adding. 
        # Actually, for PATH, it's better to resolve %JAVA_HOME% or use the absolute path 
        # if we want to be safe with simple append logic, BUT using %JAVA_HOME% is cleaner.
        # Let's use absolute path for PATH to ensure it works immediately without reboot/re-login issues sometimes associated with variable expansion.
        # Wait, standard practice is %JAVA_HOME%\bin. Windows handles it if type is REG_EXPAND_SZ.
        # My SystemConfig implementation should support it if I pass it. 
        # However, `add_to_path` implementation currently reads existing, splits, and joins. 
        # If I pass "%JAVA_HOME%\bin", it will be added. 
        
        # Let's use the absolute path for safety in this version, or the variable if we trust our SystemConfig.
        # Using absolute path ensures immediate visibility.
        bin_path_abs = os.path.join(jdk_home, "bin")
        
        if not self.sys_config.add_to_path(bin_path_abs):
             self.logger.warning("Failed to add to PATH (might need manual addition)")

        if progress_callback: progress_callback(100)
        self.logger.info(f"JDK {version} installed successfully!")

    def _find_jdk_home(self, root_dir):
        # Recursively search for bin/javac.exe
        for root, dirs, files in os.walk(root_dir):
            if "bin" in dirs:
                bin_dir = os.path.join(root, "bin")
                if "javac.exe" in os.listdir(bin_dir) or "java.exe" in os.listdir(bin_dir):
                    return root
        return None

    def _is_jdk_root(self, path):
        bin_dir = os.path.join(path, "bin")
        return os.path.exists(bin_dir) and (os.path.exists(os.path.join(bin_dir, "java.exe")))

    def uninstall(self, install_path, progress_callback=None):
        # First, try to find the actual JDK root directory
        jdk_home = None
        
        # Check if the provided path is already a JDK root
        if self._is_jdk_root(install_path):
            jdk_home = install_path
        else:
            # Try to find JDK in subdirectories (common case after extraction)
            self.logger.info(f"Path {install_path} is not JDK root, searching for JDK in subdirectories...")
            jdk_home = self._find_jdk_home(install_path)
            
            # If still not found, check JAVA_HOME environment variable
            if not jdk_home:
                java_home_env = self.sys_config.get_env_variable("JAVA_HOME")
                if java_home_env and os.path.normpath(java_home_env).startswith(os.path.normpath(install_path)):
                    if self._is_jdk_root(java_home_env):
                        jdk_home = java_home_env
                        self.logger.info(f"Found JDK via JAVA_HOME: {jdk_home}")
        
        if not jdk_home:
            raise Exception(f"Selected directory is not a valid JDK installation (bin/java.exe not found in {install_path} or subdirectories).")
        
        self.logger.info(f"Uninstalling JDK from {jdk_home}...")
        if progress_callback: progress_callback(10)
        
        # Remove Env Vars
        java_home = self.sys_config.get_env_variable("JAVA_HOME")
        if java_home:
            java_home_normalized = os.path.normpath(java_home)
            jdk_home_normalized = os.path.normpath(jdk_home)
            if java_home_normalized == jdk_home_normalized:
                self.sys_config.remove_env_variable("JAVA_HOME")
                self.sys_config.remove_from_path(os.path.join("%JAVA_HOME%", "bin"))
                self.sys_config.remove_from_path(os.path.join(java_home, "bin"))

        self.sys_config.remove_from_path(os.path.join(jdk_home, "bin"))
        
        if progress_callback: progress_callback(50)
        
        # Remove the JDK directory
        self.remove_directory(jdk_home)
        
        # If JDK was in a subdirectory of install_path, try to remove empty parent directories
        if jdk_home != install_path:
            try:
                # Walk up from jdk_home to install_path, removing empty directories
                current_dir = os.path.dirname(jdk_home)
                install_path_normalized = os.path.normpath(install_path)
                
                while current_dir and os.path.normpath(current_dir) != install_path_normalized:
                    if os.path.exists(current_dir):
                        try:
                            if not os.listdir(current_dir):
                                os.rmdir(current_dir)
                                self.logger.info(f"Removed empty directory: {current_dir}")
                                current_dir = os.path.dirname(current_dir)
                            else:
                                break  # Directory not empty, stop
                        except Exception as e:
                            self.logger.warning(f"Could not remove directory {current_dir}: {e}")
                            break
                    else:
                        break
                
                # Also check if install_path itself is now empty
                if os.path.exists(install_path) and not os.listdir(install_path):
                    try:
                        os.rmdir(install_path)
                        self.logger.info(f"Removed empty install directory: {install_path}")
                    except Exception as e:
                        self.logger.warning(f"Could not remove install directory: {e}")
            except Exception as e:
                self.logger.warning(f"Error cleaning up parent directories: {e}")
        
        if progress_callback: progress_callback(100)
        self.logger.info("JDK uninstalled successfully.")


