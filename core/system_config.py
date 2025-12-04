import winreg
import ctypes
import os
from core.logger import Logger

class SystemConfig:
    def __init__(self):
        self.logger = Logger()
        # Using HKCU (HKEY_CURRENT_USER) to avoid admin requirement
        self.key_path = r"Environment"

    def get_env_variable(self, name):
        """Get user environment variable value"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return value
        except FileNotFoundError:
            return None
        except Exception as e:
            self.logger.error(f"Failed to read env var {name}: {str(e)}")
            return None

    def set_env_variable(self, name, value):
        """Set user environment variable"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            self.logger.info(f"Set environment variable: {name}={value}")
            self._notify_system_change()
            return True
        except Exception as e:
            self.logger.error(f"Failed to set env var {name}: {str(e)}")
            return False

    def add_to_path(self, new_path, prepend=True):
        """Add a directory to the user PATH. Default prepends to prioritize."""
        try:
            # Normalize path separator
            new_path = os.path.normpath(new_path)
            
            current_path = self.get_env_variable("PATH")
            if not current_path:
                current_path = ""

            paths = [p.strip() for p in current_path.split(";") if p.strip()]
            
            # Remove existing if any (to re-position it)
            paths = [p for p in paths if p.lower() != new_path.lower()]

            # Insert
            if prepend:
                paths.insert(0, new_path)
            else:
                paths.append(new_path)
            
            new_path_val = ";".join(paths)
            
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_READ) as key:
                    _, type_ = winreg.QueryValueEx(key, "PATH")
            except:
                type_ = winreg.REG_EXPAND_SZ # Default for PATH
            
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "PATH", 0, type_, new_path_val)
            
            self.logger.info(f"Updated PATH (prepend={prepend}): {new_path}")
            self._notify_system_change()
            return True
        except Exception as e:
            self.logger.error(f"Failed to modify PATH: {str(e)}")
            return False

    def _notify_system_change(self):
        """Broadcast WM_SETTINGCHANGE to notify running applications (like Explorer)"""
        try:
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            
            result = ctypes.c_long()
            SendMessageTimeout = ctypes.windll.user32.SendMessageTimeoutW
            SendMessageTimeout(
                HWND_BROADCAST,
                WM_SETTINGCHANGE,
                0,
                "Environment",
                SMTO_ABORTIFHUNG,
                5000,
                ctypes.byref(result)
            )
            self.logger.info("System notified of environment change.")
        except Exception as e:
            self.logger.error(f"Failed to notify system: {str(e)}")

    def remove_env_variable(self, name):
        """Remove user environment variable"""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, name)
            self.logger.info(f"Removed environment variable: {name}")
            self._notify_system_change()
            return True
        except FileNotFoundError:
            self.logger.info(f"Env var {name} not found, nothing to remove.")
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove env var {name}: {str(e)}")
            return False

    def remove_from_path(self, path_to_remove):
        """Remove a directory from the user PATH"""
        try:
            # Normalize
            path_to_remove = os.path.normpath(path_to_remove)
            
            current_path = self.get_env_variable("PATH")
            if not current_path:
                return True

            paths = [p.strip() for p in current_path.split(";") if p.strip()]
            
            # Filter out the path (case insensitive check)
            new_paths = [p for p in paths if p.lower() != path_to_remove.lower()]
            
            if len(new_paths) == len(paths):
                self.logger.info(f"Path not found in PATH: {path_to_remove}")
                return True

            new_path_val = ";".join(new_paths)
            
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_READ) as key:
                    _, type_ = winreg.QueryValueEx(key, "PATH")
            except:
                type_ = winreg.REG_EXPAND_SZ

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key_path, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "PATH", 0, type_, new_path_val)
            
            self.logger.info(f"Removed from PATH: {path_to_remove}")
            self._notify_system_change()
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove from PATH: {str(e)}")
            return False


