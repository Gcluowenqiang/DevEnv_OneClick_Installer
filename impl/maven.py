import os
from core.env_manager import EnvironmentManager

class MavenInstaller(EnvironmentManager):
    def __init__(self):
        super().__init__()
        self.env_var_name = "MAVEN_HOME"
        # Apache Maven versions
        self.versions = {
            "Maven 3.9.6": "3.9.6",
            "Maven 3.9.5": "3.9.5", 
            "Maven 3.9.4": "3.9.4",
            "Maven 3.8.8": "3.8.8",
            "Maven 3.8.7": "3.8.7",
            "Maven 3.6.3": "3.6.3",
            "Maven 3.5.4": "3.5.4",
            "Maven 3.3.9": "3.3.9"
        }

    def get_version_list(self):
        """Return list of available Maven versions"""
        return list(self.versions.keys())

    def install(self, version_name, install_path, progress_callback=None, extra_config=None):
        version = self.versions.get(version_name)
        if not version:
            raise ValueError(f"Unknown version: {version_name}")

        self.logger.info(f"Preparing to install Maven {version}...")

        # 1. Construct Download URL
        # Use Apache Archive for stability: https://archive.apache.org/dist/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.zip
        # Or current mirror: https://dlcdn.apache.org/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.zip (only works for latest)
        # Archive is safer for older versions.
        url = f"https://archive.apache.org/dist/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.zip"
        filename = f"apache-maven-{version}-bin.zip"
        
        # 2. Download
        self.logger.info("Step 1/4: Downloading Maven...")
        if progress_callback: progress_callback(10)
        
        zip_path = self.download_file(url, filename, lambda p: progress_callback(10 + int(p * 0.4)))
        
        # 3. Extract
        self.logger.info("Step 2/4: Extracting files...")
        if progress_callback: progress_callback(50)
        
        extract_root = self.extract_zip(zip_path, install_path, lambda p: progress_callback(50 + int(p * 0.3)))
        
        # Maven zip extracts to 'apache-maven-{version}'
        maven_home = os.path.join(install_path, f"apache-maven-{version}")
        
        # Verify
        if not os.path.exists(os.path.join(maven_home, "bin", "mvn.cmd")):
             # Try to find it
             items = os.listdir(install_path)
             found = False
             for item in items:
                 candidate = os.path.join(install_path, item)
                 if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "bin", "mvn.cmd")):
                     maven_home = candidate
                     found = True
                     break
             if not found:
                 raise Exception("Could not find mvn.cmd after extraction")

        self.logger.info(f"Maven Home detected at: {maven_home}")

        # 4. Configure MAVEN_HOME and PATH
        self.logger.info("Step 3/4: Configuring Environment...")
        if progress_callback: progress_callback(80)
        
        # Configure Local Repo if provided
        if extra_config and extra_config.get('local_repo'):
            self._configure_settings(maven_home, extra_config['local_repo'])

        if progress_callback: progress_callback(85)
        
        # Set MAVEN_HOME (Standard) and M2_HOME (Old but still used by some tools)
        self.sys_config.set_env_variable("MAVEN_HOME", maven_home)
        self.sys_config.set_env_variable("M2_HOME", maven_home)
        
        # 5. Add to PATH
        self.logger.info("Step 4/4: Updating PATH...")
        bin_path = os.path.join(maven_home, "bin")
        if not self.sys_config.add_to_path(bin_path):
            self.logger.warning("Failed to add Maven to PATH")

        if progress_callback: progress_callback(100)
        self.logger.info(f"Maven {version} installed successfully!")

    def _configure_settings(self, maven_home, local_repo):
        """Update settings.xml with custom local repository path"""
        settings_path = os.path.join(maven_home, "conf", "settings.xml")
        if not os.path.exists(settings_path):
            self.logger.warning(f"settings.xml not found at {settings_path}")
            return
            
        try:
            self.logger.info(f"Configuring local repository: {local_repo}")
            with open(settings_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import re
            # Insert <localRepository> after <settings ...>
            # Use regex to find the opening <settings> tag which might have attributes
            if "<localRepository>" not in content:
                new_content = re.sub(
                    r'(<settings.*?>)', 
                    f'\\1\n  <!-- Configured by DevEnvInstaller -->\n  <localRepository>{local_repo}</localRepository>', 
                    content, 
                    count=1
                )
                
                # Fallback if regex didn't match (unlikely)
                if new_content == content:
                    new_content = content.replace('<settings>', f'<settings>\n  <localRepository>{local_repo}</localRepository>', 1)

                with open(settings_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            else:
                 # If it exists (unlikely for fresh install), we might want to replace it?
                 # For now, let's assume fresh install.
                 pass
                 
        except Exception as e:
            self.logger.error(f"Failed to update settings.xml: {e}")

    def uninstall(self, install_path, progress_callback=None):
        # First, try to find the actual Maven root directory
        maven_home = None
        
        # Check if the provided path is already a Maven root
        if os.path.exists(os.path.join(install_path, "bin", "mvn.cmd")):
            maven_home = install_path
        else:
            # Try to find Maven in subdirectories (common case after extraction)
            self.logger.info(f"Path {install_path} is not Maven root, searching for Maven in subdirectories...")
            for root, dirs, files in os.walk(install_path):
                if "bin" in dirs and os.path.exists(os.path.join(root, "bin", "mvn.cmd")):
                    maven_home = root
                    break
            
            # If still not found, check MAVEN_HOME environment variable
            if not maven_home:
                maven_home_env = self.sys_config.get_env_variable("MAVEN_HOME")
                if maven_home_env and os.path.normpath(maven_home_env).startswith(os.path.normpath(install_path)):
                    if os.path.exists(os.path.join(maven_home_env, "bin", "mvn.cmd")):
                        maven_home = maven_home_env
                        self.logger.info(f"Found Maven via MAVEN_HOME: {maven_home}")
        
        if not maven_home or not os.path.exists(os.path.join(maven_home, "bin", "mvn.cmd")):
            raise Exception(f"Selected directory is not a valid Maven installation (bin/mvn.cmd not found in {install_path} or subdirectories).")

        self.logger.info(f"Uninstalling Maven from {maven_home}...")
        if progress_callback: progress_callback(10)

        maven_home_env = self.sys_config.get_env_variable("MAVEN_HOME")
        if maven_home_env:
            maven_home_env_normalized = os.path.normpath(maven_home_env)
            maven_home_normalized = os.path.normpath(maven_home)
            if maven_home_env_normalized == maven_home_normalized:
                self.sys_config.remove_env_variable("MAVEN_HOME")
                self.sys_config.remove_env_variable("M2_HOME") # Also remove M2_HOME
        
        self.sys_config.remove_from_path(os.path.join(maven_home, "bin"))

        if progress_callback: progress_callback(50)
        
        # Remove the Maven directory
        self.remove_directory(maven_home)
        
        # If Maven was in a subdirectory of install_path, try to remove empty parent directories
        if maven_home != install_path:
            try:
                current_dir = os.path.dirname(maven_home)
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
        self.logger.info("Maven uninstalled successfully.")

