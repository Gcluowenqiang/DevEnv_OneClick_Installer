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

            # 验证新文件是否存在
            if not os.path.exists(new_exe_path):
                return False, f"新版本文件不存在: {new_exe_path}"
            
            current_dir = os.path.dirname(current_exe)
            current_name = os.path.basename(current_exe)
            old_exe_backup = os.path.join(current_dir, f"{current_name}.old")
            
            # 获取当前进程ID
            current_pid = os.getpid()
            
            # 规范化路径，确保使用绝对路径
            current_exe = os.path.abspath(current_exe)
            new_exe_path = os.path.abspath(new_exe_path)
            old_exe_backup = os.path.abspath(old_exe_backup)
            
            # 转义路径中的特殊字符，使用单引号包裹（PowerShell 单引号是字面量）
            def escape_ps_path(path):
                # 将反斜杠转换为正斜杠，或使用单引号
                # PowerShell 中单引号内的内容会被视为字面量
                return path.replace("'", "''")  # 单引号需要转义为两个单引号
            
            current_exe_escaped = escape_ps_path(current_exe)
            new_exe_escaped = escape_ps_path(new_exe_path)
            old_backup_escaped = escape_ps_path(old_exe_backup)
            
            # 直接在批处理中使用 PowerShell 内联代码，避免路径编码问题
            # 使用静默模式，不显示终端窗口
            bat_path = os.path.join(current_dir, "update_installer.bat")
            with open(bat_path, 'w', encoding='gbk') as f:
                f.write('@echo off\n')
                f.write('chcp 65001 > NUL 2>&1\n')  # 设置 UTF-8 编码，静默
                # 使用 -WindowStyle Hidden 隐藏 PowerShell 窗口
                f.write('powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -Command "')
                f.write('$ErrorActionPreference = \\"Stop\\"; ')
                # 使用单引号包裹路径，避免转义问题
                f.write(f"$currentExe = '{current_exe_escaped}'; ")
                f.write(f"$newExe = '{new_exe_escaped}'; ")
                f.write(f"$oldBackup = '{old_backup_escaped}'; ")
                f.write(f'$currentPid = {current_pid}; ')
                # 移除所有 Write-Host，静默执行
                f.write('try { $process = Get-Process -Id $currentPid -ErrorAction SilentlyContinue; ')
                f.write('if ($process) { $process.CloseMainWindow() | Out-Null; Start-Sleep -Seconds 2; ')
                f.write('if (-not $process.HasExited) { Stop-Process -Id $currentPid -Force -ErrorAction Stop } } } ')
                f.write('catch { }; ')  # 静默处理错误
                f.write('$maxWait = 30; $waited = 0; ')
                f.write('while ($waited -lt $maxWait) { $process = Get-Process -Id $currentPid -ErrorAction SilentlyContinue; ')
                f.write('if (-not $process) { break }; Start-Sleep -Seconds 1; $waited++ }; ')
                f.write('$process = Get-Process -Id $currentPid -ErrorAction SilentlyContinue; ')
                f.write('if ($process) { Stop-Process -Id $currentPid -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }; ')
                f.write('Start-Sleep -Seconds 2; ')  # 等待文件释放
                f.write('$currentDir = Split-Path -Parent $currentExe; ')
                f.write('if (-not (Test-Path $currentDir)) { New-Item -ItemType Directory -Path $currentDir -Force | Out-Null }; ')
                f.write('if (-not (Test-Path $newExe)) { throw \\"新版本文件不存在\\" }; ')
                f.write('try { if (Test-Path $currentExe) { ')
                f.write('$retryCount = 0; $maxRetries = 5; ')
                f.write('while ($retryCount -lt $maxRetries) { try { Move-Item -Path $currentExe -Destination $oldBackup -Force -ErrorAction Stop; break } ')
                f.write('catch { $retryCount++; if ($retryCount -ge $maxRetries) { throw $_ }; Start-Sleep -Seconds 1 } } }; ')
                f.write('Move-Item -Path $newExe -Destination $currentExe -Force -ErrorAction Stop; ')
                f.write('if (Test-Path $oldBackup) { Remove-Item -Path $oldBackup -Force -ErrorAction SilentlyContinue }; ')
                f.write('if (-not (Test-Path $currentExe)) { throw \\"更新后的文件不存在\\" }; ')
                f.write('$exeDir = Split-Path -Parent $currentExe; ')
                f.write('try { Start-Process -FilePath $currentExe -WorkingDirectory $exeDir -WindowStyle Hidden -ErrorAction Stop | Out-Null } ')
                f.write('catch { try { Push-Location $exeDir; cmd /c start \\"\\" \\"$currentExe\\"; Pop-Location } catch { throw \\"无法启动新版本\\" } } } ')
                f.write('catch { if (Test-Path $oldBackup) { Move-Item -Path $oldBackup -Destination $currentExe -Force -ErrorAction SilentlyContinue }; ')
                # 只有出错时才显示错误窗口
                f.write('$wshell = New-Object -ComObject WScript.Shell; ')
                f.write('$wshell.Popup(\\"更新失败: $_\\", 0, \\"更新错误\\", 0x10); exit 1 }"\n')
                f.write('if %errorlevel% equ 0 (\n')
                f.write('    timeout /t 1 /nobreak > NUL 2>&1\n')
                f.write('    del /F /Q "%~f0" > NUL 2>&1\n')
                f.write(')\n')
            
            self.logger.info(f"Starting update script: {bat_path}")
            self.logger.info(f"Current exe: {current_exe}")
            self.logger.info(f"New exe: {new_exe_path}")
            
            # 使用 CREATE_NO_WINDOW 标志静默执行，不显示批处理窗口
            subprocess.Popen([bat_path], shell=True, cwd=current_dir, creationflags=0x08000000)
            
            return True, "正在重启以完成更新..."
            
        except Exception as e:
            self.logger.error(f"Update failed: {e}")
            return False, str(e)

