import os
import sys
import requests
import subprocess
import time
from core.logger import Logger
from core.version import APP_VERSION, GITHUB_REPO

class Updater:
    def __init__(self, config_manager):
        self.logger = Logger()
        self.config_manager = config_manager
        self.github_api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        
    def check_for_updates(self):
        """检查更新
        Returns:
            tuple: (has_update, version, body, download_url)
        """
        try:
            self.logger.info(f"Checking for updates from {self.github_api_url}...")
            response = requests.get(self.github_api_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            latest_tag = data.get("tag_name", "").lstrip("v")
            body = data.get("body", "")
            assets = data.get("assets", [])
            
            # 查找 exe 下载链接
            download_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".exe"):
                    download_url = asset.get("browser_download_url")
                    break
            
            if not download_url:
                self.logger.warning("No executable asset found in release.")
                return False, latest_tag, "未找到可执行文件", None
                
            if self._compare_versions(latest_tag, APP_VERSION) > 0:
                return True, latest_tag, body, download_url
            else:
                return False, latest_tag, body, None
                
        except Exception as e:
            self.logger.error(f"Failed to check for updates: {e}")
            return False, None, str(e), None

    def _compare_versions(self, v1, v2):
        """比较版本号 v1 和 v2。 v1 > v2 返回 1, v1 < v2 返回 -1, 相等返回 0"""
        def parse(v):
            try:
                return [int(x) for x in v.split('.')]
            except:
                return [0]
            
        try:
            p1 = parse(v1)
            p2 = parse(v2)
            
            # 补齐长度
            max_len = max(len(p1), len(p2))
            p1.extend([0] * (max_len - len(p1)))
            p2.extend([0] * (max_len - len(p2)))
            
            if p1 > p2: return 1
            if p1 < p2: return -1
            return 0
        except:
            return 0

    def download_update(self, url, progress_callback=None):
        """下载更新"""
        try:
            save_dir = self.config_manager.get_downloads_dir()
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                
            filename = url.split("/")[-1]
            save_path = os.path.join(save_dir, f"update_{filename}")
            
            self.logger.info(f"Downloading update from {url} to {save_path}...")
            
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded_size = 0
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if progress_callback and total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            progress_callback(progress)
                            
            return save_path
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            raise

    def perform_update(self, new_exe_path):
        """执行更新替换"""
        try:
            current_exe = sys.executable
            
            # 如果是在 Python 环境下运行（非打包），无法替换自身，仅提示
            if not getattr(sys, 'frozen', False):
                self.logger.warning("Running in source mode, cannot perform self-update.")
                return False, "源码运行模式下无法自动更新，请手动下载新代码。"

            # 生成批处理脚本
            bat_path = os.path.join(os.path.dirname(current_exe), "update_installer.bat")
            with open(bat_path, 'w', encoding='gbk') as f: # Windows bat 通常使用 gbk
                f.write('@echo off\n')
                f.write('timeout /t 2 /nobreak > NUL\n') # 等待主程序退出
                f.write(f'del "{current_exe}"\n')
                f.write(f'move "{new_exe_path}" "{current_exe}"\n')
                f.write(f'start "" "{current_exe}"\n')
                f.write(f'del "%~f0"\n')
            
            self.logger.info(f"Starting update script: {bat_path}")
            # CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen([bat_path], shell=True, creationflags=0x08000000)
            
            return True, "正在重启以完成更新..."
            
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            return False, str(e)

