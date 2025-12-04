import os
from core.env_manager import EnvironmentManager

class RedisInstaller(EnvironmentManager):
    def __init__(self):
        super().__init__()
        self.env_var_name = "REDIS_HOME"
        # Redis for Windows is officially discontinued by Microsoft Open Tech.
        # However, there are two main sources:
        # 1. MicrosoftArchive (Old, up to 3.0.504) - Stable but very old.
        # 2. tporadowski/redis (Community fork, up to 5.0.14) - Recommended for dev.
        # 3. Memurai (Commercial, developer free edition) - Not open source zip directly.
        # We will use tporadowski/redis as it is the de facto standard for "native" Windows Redis dev.
        
        self.versions = {
            "Redis 5.0.14 (tporadowski)": {
                "version": "5.0.14.1",
                "url": "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"
            },
            "Redis 4.0.14 (MicrosoftArchive)": {
                "version": "4.0.14",
                # Note: MicrosoftArchive doesn't have 4.0, max is 3.2.100. 
                # Let's stick to the 5.0.14 which is most useful.
                # Actually let's just support the latest stable 5.0 from tporadowski.
                "url": None
            }
        }
        # Clean up dictionary to only valid ones
        self.versions = {
             "Redis 5.0.14 (Recommended)": {
                "version": "5.0.14.1",
                "url": "https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip"
            }
        }

    def get_version_list(self):
        return list(self.versions.keys())

    def install(self, version_name, install_path, progress_callback=None, extra_config=None):
        if version_name not in self.versions:
            raise ValueError(f"Unknown version: {version_name}")
            
        info = self.versions[version_name]
        url = info['url']
        version = info['version']
        filename = f"Redis-x64-{version}.zip"
        
        self.logger.info(f"Preparing to install Redis {version}...")

        # 2. Download
        self.logger.info("Step 1/5: Downloading Redis...")
        if progress_callback: progress_callback(10)
        
        zip_path = self.download_file(url, filename, lambda p: progress_callback(10 + int(p * 0.4)))
        
        # 3. Extract
        self.logger.info("Step 2/5: Extracting files...")
        if progress_callback: progress_callback(50)
        
        # Redis zip usually extracts flatly (no root folder), so we MUST create a folder for it.
        # install_path usually is "D:\Softwares". 
        # We want "D:\Softwares\Redis-5.0.14".
        
        redis_home = os.path.join(install_path, f"Redis-{version}")
        if not os.path.exists(redis_home):
            os.makedirs(redis_home)
            
        # Extract directly to redis_home
        self.extract_zip(zip_path, redis_home, lambda p: progress_callback(50 + int(p * 0.2)))
        
        # Verify
        if not os.path.exists(os.path.join(redis_home, "redis-server.exe")):
             raise Exception("Could not find redis-server.exe after extraction")

        self.logger.info(f"Redis Home detected at: {redis_home}")

        # 4. Configure Redis
        self.logger.info("Step 3/5: Configuring Redis...")
        if progress_callback: progress_callback(70)
        self._configure_redis(redis_home, extra_config)

        # 5. Configure REDIS_HOME and PATH
        self.logger.info("Step 4/5: Configuring Environment...")
        if progress_callback: progress_callback(85)
        
        self.sys_config.set_env_variable("REDIS_HOME", redis_home)
        
        # 6. Add to PATH
        self.logger.info("Step 5/5: Updating PATH...")
        if not self.sys_config.add_to_path(redis_home):
            self.logger.warning("Failed to add Redis to PATH")

        if progress_callback: progress_callback(100)
        self.logger.info(f"Redis {version} installed successfully!")

    def _configure_redis(self, redis_home, config):
        if not config: return
        
        conf_path = os.path.join(redis_home, "redis.windows.conf")
        if not os.path.exists(conf_path):
            self.logger.warning("redis.windows.conf not found")
            return
            
        try:
            with open(conf_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            import re
            
            # Port
            port = config.get('port', '6379')
            if port:
                content = re.sub(r'^port \d+', f'port {port}', content, flags=re.MULTILINE)
            
            # Username (Note: Redis 5.0.14 doesn't support ACL, but we'll add it as comment for future reference)
            username = config.get('username', '').strip()
            password = config.get('password', '').strip()
            
            # Password configuration
            if password:
                # Uncomment requirepass if it is commented
                if re.search(r'#\s*requirepass', content):
                    content = re.sub(r'#\s*requirepass .*', f'requirepass {password}', content)
                # Replace existing if not commented
                elif re.search(r'^requirepass', content, flags=re.MULTILINE):
                    content = re.sub(r'^requirepass .*', f'requirepass {password}', content, flags=re.MULTILINE)
                else:
                    # Append if not found
                    content += f"\nrequirepass {password}"
            
            # Add username as comment (for Redis 6.0+ ACL support in future)
            if username:
                # Check if there's already a user directive (for future Redis 6.0+)
                if not re.search(r'^user\s+', content, flags=re.MULTILINE):
                    # Add as comment for now (Redis 5.0.14 doesn't support ACL)
                    user_comment = f"\n# User: {username} (ACL not supported in Redis 5.0.14, upgrade to 6.0+ for ACL support)"
                    if password:
                        user_comment += f"\n# For Redis 6.0+: user {username} on >{password} ~* &* +@all"
                    content += user_comment
                    self.logger.info(f"Username configured (as comment for future ACL support): {username}")
            
            with open(conf_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            self.logger.info(f"Configured Redis: Port={port}, Username={'Yes' if username else 'No'}, Password={'Yes' if password else 'No'}")

            # Service
            if config.get('service'):
                self._install_service(redis_home, conf_path)
                
        except Exception as e:
            self.logger.error(f"Failed to configure Redis: {e}")

    def _install_service(self, redis_home, conf_path):
        self.logger.info("Registering Redis as a Windows Service...")
        server_exe = os.path.join(redis_home, "redis-server.exe")
        
        import subprocess
        try:
            # redis-server --service-install redis.windows.conf --loglevel verbose
            cmd = [server_exe, "--service-install", conf_path, "--loglevel", "verbose"]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info("Redis Service installed successfully.")
                # Start it
                subprocess.run([server_exe, "--service-start"], capture_output=True)
                self.logger.info("Redis Service started.")
            else:
                self.logger.error(f"Failed to install service: {result.stdout} {result.stderr}")
                self.logger.warning("Note: Service installation requires Administrator privileges.")
                
        except Exception as e:
             self.logger.error(f"Service installation error: {e}")

    def uninstall(self, install_path, progress_callback=None):
        # First, try to find the actual Redis root directory
        redis_home = None
        
        # Check if the provided path is already a Redis root
        if os.path.exists(os.path.join(install_path, "redis-server.exe")):
            redis_home = install_path
        else:
            # Try to find Redis in subdirectories (common case after extraction)
            self.logger.info(f"Path {install_path} is not Redis root, searching for Redis in subdirectories...")
            for root, dirs, files in os.walk(install_path):
                if "redis-server.exe" in files:
                    redis_home = root
                    break
            
            # If still not found, check REDIS_HOME environment variable
            if not redis_home:
                redis_home_env = self.sys_config.get_env_variable("REDIS_HOME")
                if redis_home_env and os.path.normpath(redis_home_env).startswith(os.path.normpath(install_path)):
                    if os.path.exists(os.path.join(redis_home_env, "redis-server.exe")):
                        redis_home = redis_home_env
                        self.logger.info(f"Found Redis via REDIS_HOME: {redis_home}")
        
        if not redis_home or not os.path.exists(os.path.join(redis_home, "redis-server.exe")):
            raise Exception(f"Selected directory is not a valid Redis installation (redis-server.exe not found in {install_path} or subdirectories).")

        self.logger.info(f"Uninstalling Redis from {redis_home}...")
        if progress_callback: progress_callback(10)

        # Stop/Uninstall Service if exists
        self._uninstall_service(redis_home)

        if progress_callback: progress_callback(30)

        redis_home_env = self.sys_config.get_env_variable("REDIS_HOME")
        if redis_home_env:
            redis_home_env_normalized = os.path.normpath(redis_home_env)
            redis_home_normalized = os.path.normpath(redis_home)
            if redis_home_env_normalized == redis_home_normalized:
                self.sys_config.remove_env_variable("REDIS_HOME")
        
        self.sys_config.remove_from_path(redis_home)

        if progress_callback: progress_callback(60)
        
        # Remove the Redis directory
        self.remove_directory(redis_home)
        
        # If Redis was in a subdirectory of install_path, try to remove empty parent directories
        if redis_home != install_path:
            try:
                current_dir = os.path.dirname(redis_home)
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
        self.logger.info("Redis uninstalled successfully.")

    def _uninstall_service(self, redis_home):
        server_exe = os.path.join(redis_home, "redis-server.exe")
        if not os.path.exists(server_exe): return
        
        import subprocess
        try:
            self.logger.info("Attempting to stop and uninstall Redis service...")
            # Stop
            subprocess.run([server_exe, "--service-stop"], capture_output=True)
            # Uninstall
            subprocess.run([server_exe, "--service-uninstall"], capture_output=True)
            self.logger.info("Redis service command executed.")
        except Exception as e:
            self.logger.warning(f"Failed to uninstall Redis service (ignore if not installed): {e}")

