import os
import json
import requests
from core.env_manager import EnvironmentManager

class NodeInstaller(EnvironmentManager):
    def __init__(self):
        super().__init__()
        self.env_var_name = "NODE_HOME"
        self.node_dist_url = "https://nodejs.org/dist/index.json"
        self.versions = {} # Cache for version -> download info

    def get_version_list(self):
        """Fetch remote LTS versions from nodejs.org"""
        try:
            self.logger.info("Fetching Node.js version list...")
            # Use a short timeout to not block UI too long, handle exception if offline
            response = requests.get(self.node_dist_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Filter for LTS versions and create a mapping
            # Format: "v20.11.0 (Iron)" -> "v20.11.0"
            self.versions = {}
            for item in data:
                if item.get('lts'):
                    version = item['version'] # e.g., "v20.11.0"
                    lts_name = item['lts']    # e.g., "Iron"
                    display_name = f"{version} ({lts_name})"
                    
                    # Store metadata needed for download
                    # We need to know if win-x64 files exist, but usually they do for recent LTS
                    self.versions[display_name] = {
                        "version": version,
                        "files": item.get('files', [])
                    }
            
            # Return top 10 recent LTS versions to avoid a huge list
            return list(self.versions.keys())[:10]
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Node.js versions: {e}")
            # Fallback to basic hardcoded LTS if fetch fails
            fallback = ["v20.11.0 (Iron)", "v18.19.0 (Hydrogen)"]
            self.versions = {
                "v20.11.0 (Iron)": {"version": "v20.11.0"},
                "v18.19.0 (Hydrogen)": {"version": "v18.19.0"}
            }
            return fallback

    def install(self, version_name, install_path, progress_callback=None, extra_config=None):
        # Ensure we have version data (in case this is a fresh instance)
        if not self.versions or version_name not in self.versions:
            self.logger.info("Version info not found locally, refreshing version list...")
            self.get_version_list()

        if version_name not in self.versions:
            raise ValueError(f"Unknown version: {version_name}")
            
        version_data = self.versions[version_name]
        version_str = version_data['version'] # e.g., "v20.11.0"
        
        self.logger.info(f"Preparing to install Node.js {version_str}...")
        
        # 1. Construct Download URL
        # https://nodejs.org/dist/v20.11.0/node-v20.11.0-win-x64.zip
        filename = f"node-{version_str}-win-x64.zip"
        url = f"https://nodejs.org/dist/{version_str}/{filename}"
        
        # 2. Download
        self.logger.info("Step 1/4: Downloading Node.js...")
        if progress_callback: progress_callback(10)
        
        zip_path = self.download_file(url, filename, lambda p: progress_callback(10 + int(p * 0.4)))
        
        # 3. Extract
        self.logger.info("Step 2/4: Extracting files...")
        if progress_callback: progress_callback(50)
        
        extract_root = self.extract_zip(zip_path, install_path, lambda p: progress_callback(50 + int(p * 0.3)))
        
        # Node zip usually extracts to 'node-v20.11.0-win-x64' folder
        node_home = os.path.join(install_path, f"node-{version_str}-win-x64")
        
        # Verify
        if not os.path.exists(os.path.join(node_home, "node.exe")):
             # Try to find it if name is different
             items = os.listdir(install_path)
             found = False
             for item in items:
                 candidate = os.path.join(install_path, item)
                 if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "node.exe")):
                     node_home = candidate
                     found = True
                     break
             if not found:
                 raise Exception("Could not find node.exe after extraction")

        self.logger.info(f"Node.js Home detected at: {node_home}")
        
        # 4. Configure NODE_HOME (Optional but good practice) and PATH
        self.logger.info("Step 3/4: Configuring Environment...")
        if progress_callback: progress_callback(85)

        # Node doesn't strictly require NODE_HOME, but it's useful.
        # Main thing is adding to PATH.
        
        # Create 'node_global' and 'node_cache' folders for npm to avoid permission issues in default locations?
        # Standard zip install just gives node and npm.
        # Let's set NODE_HOME and add to PATH.
        
        self.sys_config.set_env_variable("NODE_HOME", node_home)
        
        # 5. Add to PATH
        self.logger.info("Step 4/4: Updating PATH...")
        if not self.sys_config.add_to_path(node_home):
            self.logger.warning("Failed to add Node to PATH")
            
        # 6. Special: Configure NPM global paths? 
        # For a portable/zip install, npm might try to install globals to AppData or inside the node folder.
        # If inside node folder, it's fine. 
        # Let's just ensure basic 'node' and 'npm' commands work.
        
        if progress_callback: progress_callback(100)
        self.logger.info(f"Node.js {version_str} installed successfully!")

    def uninstall(self, install_path, progress_callback=None):
        # First, try to find the actual Node.js root directory
        node_home = None
        
        # Check if the provided path is already a Node.js root
        if os.path.exists(os.path.join(install_path, "node.exe")):
            node_home = install_path
        else:
            # Try to find Node.js in subdirectories (common case after extraction)
            self.logger.info(f"Path {install_path} is not Node.js root, searching for Node.js in subdirectories...")
            for root, dirs, files in os.walk(install_path):
                if "node.exe" in files:
                    node_home = root
                    break
            
            # If still not found, check NODE_HOME environment variable
            if not node_home:
                node_home_env = self.sys_config.get_env_variable("NODE_HOME")
                if node_home_env and os.path.normpath(node_home_env).startswith(os.path.normpath(install_path)):
                    if os.path.exists(os.path.join(node_home_env, "node.exe")):
                        node_home = node_home_env
                        self.logger.info(f"Found Node.js via NODE_HOME: {node_home}")
        
        if not node_home or not os.path.exists(os.path.join(node_home, "node.exe")):
            raise Exception(f"Selected directory is not a valid Node.js installation (node.exe not found in {install_path} or subdirectories).")

        self.logger.info(f"Uninstalling Node.js from {node_home}...")
        if progress_callback: progress_callback(10)

        node_home_env = self.sys_config.get_env_variable("NODE_HOME")
        if node_home_env:
            node_home_env_normalized = os.path.normpath(node_home_env)
            node_home_normalized = os.path.normpath(node_home)
            if node_home_env_normalized == node_home_normalized:
                self.sys_config.remove_env_variable("NODE_HOME")
        
        self.sys_config.remove_from_path(node_home)
        
        if progress_callback: progress_callback(50)
        
        # Remove the Node.js directory
        self.remove_directory(node_home)
        
        # If Node.js was in a subdirectory of install_path, try to remove empty parent directories
        if node_home != install_path:
            try:
                current_dir = os.path.dirname(node_home)
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
        self.logger.info("Node.js uninstalled successfully.")

