from abc import ABC, abstractmethod
import os
import shutil
import urllib.request
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import zipfile
import certifi
import time
import stat
import json
from core.logger import Logger
from core.system_config import SystemConfig

class EnvironmentManager(ABC):
    def __init__(self):
        self.logger = Logger()
        self.sys_config = SystemConfig()
        self.env_var_name = None # To be set by subclasses (e.g., "JAVA_HOME")
        # 使用统一管理文件夹下的downloads目录
        from core.config import ConfigManager
        config_manager = ConfigManager()
        self.download_dir = config_manager.get_downloads_dir()
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def check_existing(self):
        """
        Check if environment already exists.
        Returns dict with details or None.
        """
        if not self.env_var_name:
            return None
            
        current_home = self.sys_config.get_env_variable(self.env_var_name)
        if current_home:
             # Even if directory doesn't exist, the env var is set, which is a conflict/state we should know about.
             return {
                 'exists': True,
                 'path': current_home,
                 'source': f'Environment Variable ({self.env_var_name})'
             }
        return None

    @abstractmethod
    def get_version_list(self):
        """Return list of available versions"""
        pass

    def download_file(self, url, filename, progress_callback=None, retries=5):
        """Generic download with progress tracking and RESUMABLE retry logic"""
        filepath = os.path.join(self.download_dir, filename)
        
        # If file exists and is complete? We don't know if it's complete without checking size.
        # But for simplicity in this "installer", if it exists, we often assume it's cached.
        # However, to fix the "corrupt/partial file" issue, we should probably try to resume it
        # if we can verify it. 
        # For now, let's assume if it exists from a previous *successful* run, it's fine.
        # But if this run failed previously, it might be partial. 
        # Let's NOT assume it's done unless we verified it.
        # Since we don't have a checksum, we'll use the temp file approach or just append.
        # To keep it simple: we will try to download. If server says 206, we resume.
        
        self.logger.info(f"Downloading {url} to {filepath}")
        
        session = requests.Session()
        # Basic retry for connection setup
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        temp_filepath = filepath + ".part"
        
        # Check if we have a partial download
        resume_byte_pos = 0
        if os.path.exists(temp_filepath):
            resume_byte_pos = os.path.getsize(temp_filepath)
            self.logger.info(f"Found partial download, resuming from {resume_byte_pos} bytes...")

        last_error = None
        
        for attempt in range(retries):
            try:
                headers = {}
                if resume_byte_pos > 0:
                    headers["Range"] = f"bytes={resume_byte_pos}-"
                
                # Timeout: (connect, read)
                with session.get(url, stream=True, verify=True, headers=headers, timeout=(10, 30)) as response:
                    response.raise_for_status()
                    
                    mode = 'ab' if resume_byte_pos > 0 else 'wb'
                    
                    # Handle server not supporting Range (200 OK instead of 206 Partial Content)
                    if response.status_code == 200:
                        if resume_byte_pos > 0:
                            self.logger.warning("Server does not support resume (got 200), restarting download.")
                            resume_byte_pos = 0
                            mode = 'wb'
                        total_size = int(response.headers.get('content-length', 0))
                    elif response.status_code == 206:
                        # Content-Range: bytes 1000-2000/5000
                        content_range = response.headers.get('content-range', '')
                        if '/' in content_range:
                            total_size = int(content_range.split('/')[1])
                        else:
                            # Fallback if unknown total
                            total_size = resume_byte_pos + int(response.headers.get('content-length', 0))
                    else:
                        total_size = 0 # Unknown

                    block_size = 8192
                    downloaded = resume_byte_pos
                    
                    with open(temp_filepath, mode) as f:
                        for chunk in response.iter_content(chunk_size=block_size):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback and total_size > 0:
                                    percent = int(downloaded * 100 / total_size)
                                    progress_callback(min(percent, 100))
                
                # If we got here without exception, download is likely complete or stream finished naturally.
                # Verify size if possible
                if total_size > 0 and downloaded < total_size:
                    raise Exception(f"Incomplete download: {downloaded}/{total_size}")
                
                # Success! Rename temp file to actual file
                if os.path.exists(filepath):
                    os.remove(filepath)
                os.rename(temp_filepath, filepath)
                
                if progress_callback:
                    progress_callback(100)
                
                self.logger.info("Download complete.")
                return filepath
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"Download attempt {attempt+1}/{retries} failed: {str(e)}")
                time.sleep(2) # Wait before retry
                
                # Update resume position for next attempt
                if os.path.exists(temp_filepath):
                    resume_byte_pos = os.path.getsize(temp_filepath)
        
        # If we exhausted retries
        self.logger.error(f"Download failed after {retries} attempts.")
        raise last_error

    def extract_zip(self, zip_path, extract_to, progress_callback=None):
        """Generic zip extraction"""
        self.logger.info(f"Extracting {zip_path} to {extract_to}")
        try:
            if not os.path.exists(extract_to):
                os.makedirs(extract_to)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                total_files = len(zip_ref.infolist())
                for i, file in enumerate(zip_ref.infolist()):
                    zip_ref.extract(file, extract_to)
                    if progress_callback:
                        percent = int((i + 1) * 100 / total_files)
                        progress_callback(percent)
                        
            self.logger.info("Extraction complete.")
            # Return the actual directory name if it extracts into a subdirectory
            # Often zip files contain a root directory (e.g., jdk-17/...)
            # We should return the path that contains the bin folder ultimately
            return extract_to
        except Exception as e:
            self.logger.error(f"Extraction failed: {str(e)}")
            raise e

    @abstractmethod
    def install(self, version, install_dir, progress_callback=None):
        """Main installation logic"""
        pass

    def _on_rm_error(self, func, path, exc_info):
        """
        Error handler for shutil.rmtree.
        If the error is due to an access error (read only file)
        it attempts to add write permission and then retries.
        If the error is because the file is not found, it ignores it.
        """
        # Is the error an access error?
        if not os.access(path, os.W_OK):
            try:
                os.chmod(path, stat.S_IWUSR)
                func(path)
                return
            except Exception as e:
                 self.logger.warning(f"Failed to change permissions for {path}: {e}")
        
        self.logger.error(f"Failed to remove {path}: {exc_info[1]}")

    def remove_directory(self, path):
        """Safely remove a directory"""
        if not os.path.exists(path):
            self.logger.warning(f"Directory not found: {path}")
            return
        
        try:
            self.logger.info(f"Removing directory: {path}")
            # Basic safety check
            if len(os.path.abspath(path)) < 5: # e.g. C:\ or D:\
                 raise Exception(f"Path too short/unsafe, refusing to delete: {path}")
                 
            shutil.rmtree(path, onerror=self._on_rm_error)
            self.logger.info("Directory removed.")
        except Exception as e:
             self.logger.error(f"Failed to remove directory: {e}")
             raise e

    @abstractmethod
    def uninstall(self, install_dir, progress_callback=None):
        """Uninstall logic"""
        pass
