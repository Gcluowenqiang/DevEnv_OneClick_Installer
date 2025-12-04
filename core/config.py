import json
import os
from core.logger import Logger
from core.version import APP_VERSION, GITHUB_REPO

class ConfigManager:
    """配置管理器，用于保存和读取应用配置，统一管理所有程序目录"""
    
    DEFAULT_MANAGER_FOLDER = "DevEnvManager"
    
    def __init__(self):
        self.logger = Logger()
        # 先使用临时logger，避免循环依赖
        self._init_logger = None
        
        # 获取统一管理文件夹路径
        self.manager_folder_path = self._get_or_create_manager_folder()
        
        # 确保所有子目录存在
        self._ensure_directories()
        
        # 启动时清理旧目录（如果存在）
        self._cleanup_old_directories_on_startup()

        # 读取上次运行的版本号
        self.last_run_version = self._load_last_run_version()
    
    def _load_last_run_version(self):
        """读取上次运行的版本号"""
        config_file = self.get_config_file()
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("last_run_version", "0.0.0")
            except:
                pass
        return "0.0.0"

    def get_last_run_version(self):
        return self.last_run_version

    def set_last_run_version(self, version):
        self.last_run_version = version
        self._save_config()

    def _get_or_create_manager_folder(self):
        """获取或创建统一管理文件夹"""
        # 1. 优先从环境变量读取（最高优先级）
        try:
            from core.system_config import SystemConfig
            sys_config = SystemConfig()
            env_path = sys_config.get_env_variable("DEVENVMANAGER_CONFIG")
            
            if env_path and env_path.strip():
                path_normalized = os.path.normpath(env_path.strip())
                # 验证路径是否有效（允许路径不存在，因为可能是新设置的路径）
                if path_normalized:
                    return path_normalized
        except Exception as e:
            pass
        
        # 2. 如果没有环境变量，使用默认路径（首次运行）
        # 默认路径：用户主目录下的DevEnvManager
        default_path = os.path.join(os.path.expanduser("~"), self.DEFAULT_MANAGER_FOLDER)
        
        # 确保目录存在（仅在不存在时创建）
        if not os.path.exists(default_path):
            try:
                os.makedirs(default_path)
            except Exception as e:
                # 如果创建失败，使用程序目录
                default_path = os.path.join(os.getcwd(), self.DEFAULT_MANAGER_FOLDER)
                if not os.path.exists(default_path):
                    os.makedirs(default_path)
        
        return os.path.normpath(default_path)
    
    def _migrate_config(self, old_config_file, new_manager_path):
        """迁移旧配置文件到新位置"""
        try:
            # 读取旧配置
            with open(old_config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 确保新目录存在
            config_dir = os.path.join(new_manager_path, "config")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            # 保存到新位置
            new_config_file = os.path.join(config_dir, "config.json")
            with open(new_config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            # 可选：删除旧配置文件（保留注释掉，以防万一）
            # os.remove(old_config_file)
        except Exception:
            pass
    
    def _ensure_directories(self):
        """确保所有必要的子目录存在"""
        dirs = [
            self.get_downloads_dir(),
            self.get_logs_dir(),
            self.get_config_dir(),
            self.get_apps_dir()  # apps目录用于安装环境
        ]
        for dir_path in dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path)
                except Exception as e:
                    if self._init_logger:
                        self._init_logger.warning(f"Failed to create directory {dir_path}: {e}")
    
    def get_manager_folder_path(self):
        """获取统一管理文件夹的完整路径"""
        return self.manager_folder_path
    
    def set_manager_folder_path(self, path, migrate_files=True):
        """设置统一管理文件夹路径，并迁移原有文件
        
        Args:
            path: 新的统一管理文件夹路径
            migrate_files: 是否迁移原有文件（默认True）
        
        Returns:
            tuple: (success: bool, message: str)
        """
        if not path:
            return False, "路径不能为空"
        
        # 规范化路径
        path = os.path.normpath(path)
        old_path = self.manager_folder_path
        
        # 如果新旧路径相同，无需迁移
        if os.path.normpath(path) == os.path.normpath(old_path):
            return True, "路径未改变"
        
        # 确保父目录存在
        parent_dir = os.path.dirname(path)
        if not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir)
            except Exception as e:
                return False, f"无法创建父目录: {e}"
        
        # 如果新路径不存在，创建它
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                return False, f"无法创建目录: {e}"
        
        # 迁移文件
        if migrate_files and os.path.exists(old_path) and old_path != path:
            try:
                migrate_result = self._migrate_all_files(old_path, path)
                if not migrate_result[0]:
                    return False, f"文件迁移失败: {migrate_result[1]}"
            except Exception as e:
                return False, f"文件迁移异常: {e}"
        
        # 更新环境变量
        try:
            env_update_result = self._update_environment_variables(old_path, path)
            if not env_update_result[0]:
                return False, f"环境变量更新失败: {env_update_result[1]}"
        except Exception as e:
            return False, f"环境变量更新异常: {e}"
        
        # 更新历史记录
        try:
            self._update_history_paths(old_path, path)
        except Exception as e:
            # 历史记录更新失败不影响主流程，只记录警告
            if self._init_logger:
                self._init_logger.warning(f"历史记录更新失败: {e}")
        
        # 保存配置
        self.manager_folder_path = path
        
        # 保存到环境变量（最高优先级）
        try:
            from core.system_config import SystemConfig
            sys_config = SystemConfig()
            sys_config.set_env_variable("DEVENVMANAGER_CONFIG", path)
        except Exception as e:
            pass
        
        self._save_config()
        self._ensure_directories()
        
        # 删除旧位置的配置文件（程序目录下的config.json）
        old_config_in_cwd = os.path.join(os.getcwd(), "config.json")
        if os.path.exists(old_config_in_cwd):
            try:
                os.remove(old_config_in_cwd)
            except Exception as e:
                pass
        
        # 重新初始化Logger以使用新路径
        self._reinitialize_logger()
        
        # 延迟再次尝试删除旧目录（确保所有文件句柄已释放）
        import time
        time.sleep(1.5)  # 等待1.5秒，确保文件句柄释放
        
        final_removed = self._force_remove_directory(old_path)
        
        if final_removed:
            return True, "迁移成功，原目录已删除"
        else:
            # 如果删除失败，尝试使用Windows延迟删除机制
            scheduled = self._schedule_delete_on_reboot(old_path)
            
            if scheduled:
                return True, f"迁移成功。原目录将在系统重启时自动删除。\n原目录路径: {old_path}"
            else:
                # 如果Windows延迟删除也失败，尝试使用管理员权限删除
                admin_removed = self._delete_with_admin(old_path)
                
                if admin_removed:
                    return True, "迁移成功，原目录已通过管理员权限删除"
                else:
                    return True, f"迁移成功，但原目录无法立即删除（已复制到新位置）。\n请手动删除原目录: {old_path}\n或重启系统后自动删除。"
    
    def _reinitialize_logger(self):
        """重新初始化Logger以使用新的日志路径"""
        try:
            from core.logger import Logger
            logger_instance = Logger()
            
            # 关闭所有文件处理器
            for handler in logger_instance.logger.handlers[:]:
                try:
                    handler.close()
                    logger_instance.logger.removeHandler(handler)
                except:
                    pass
            
            # 重新初始化Logger（使用新路径）
            logger_instance._initialize_logger()
        except Exception as e:
            # 如果重新初始化失败，不影响主流程
            pass
    
    def _migrate_all_files(self, old_path, new_path):
        """迁移所有文件从旧位置到新位置，处理正在使用的文件"""
        try:
            import shutil
            import time
            
            # 先关闭Logger的文件句柄，避免日志文件被占用
            self._close_logger_handlers()
            
            # 需要迁移的目录
            dirs_to_migrate = ["downloads", "logs", "config", "apps"]
            failed_files = []
            skipped_files = []
            
            for dir_name in dirs_to_migrate:
                old_dir = os.path.join(old_path, dir_name)
                new_dir = os.path.join(new_path, dir_name)
                
                if os.path.exists(old_dir):
                    # 如果新目录已存在，合并内容
                    if os.path.exists(new_dir):
                        # 合并目录内容
                        for item in os.listdir(old_dir):
                            old_item = os.path.join(old_dir, item)
                            new_item = os.path.join(new_dir, item)
                            
                            result = self._migrate_item(old_item, new_item, retries=3)
                            if result == "failed":
                                failed_files.append(old_item)
                            elif result == "skipped":
                                skipped_files.append(old_item)
                        
                        # 尝试删除旧目录（如果为空）
                        try:
                            if not os.listdir(old_dir):
                                os.rmdir(old_dir)
                        except:
                            pass  # 目录不为空或删除失败，保留
                    else:
                        # 直接迁移整个目录
                        result = self._migrate_item(old_dir, new_dir, retries=3)
                        if result == "failed":
                            failed_files.append(old_dir)
                        elif result == "skipped":
                            skipped_files.append(old_dir)
            
            # 强制删除旧目录及其所有内容（多次尝试确保删除）
            old_dir_removed = False
            for attempt in range(3):
                old_dir_removed = self._force_remove_directory(old_path)
                if old_dir_removed:
                    break
                import time
                time.sleep(0.5)  # 等待后重试
            
            # 构建结果消息
            message_parts = ["文件迁移完成"]
            if old_dir_removed:
                message_parts.append("原目录已删除")
            else:
                message_parts.append("原目录部分文件无法删除（已复制到新位置）")
            
            if skipped_files:
                message_parts.append(f"跳过 {len(skipped_files)} 个正在使用的文件")
            if failed_files:
                message_parts.append(f"失败 {len(failed_files)} 个文件")
            
            if failed_files:
                return False, "; ".join(message_parts) + f"\n失败文件: {', '.join(failed_files[:3])}" + ("..." if len(failed_files) > 3 else "")
            elif skipped_files and not old_dir_removed:
                return True, "; ".join(message_parts) + "\n提示：部分文件正在使用，原目录可能仍有残留文件，可手动删除。"
            else:
                return True, "; ".join(message_parts)
        except Exception as e:
            return False, str(e)
    
    def _migrate_item(self, old_item, new_item, retries=3):
        """迁移单个文件或目录，处理文件占用问题
        
        Returns:
            "success": 成功迁移
            "skipped": 跳过（文件正在使用，但已复制）
            "failed": 失败
        """
        import shutil
        import time
        
        for attempt in range(retries):
            try:
                if os.path.isdir(old_item):
                    # 目录：先复制，再删除
                    if os.path.exists(new_item):
                        # 如果目标已存在，合并内容
                        for sub_item in os.listdir(old_item):
                            old_sub = os.path.join(old_item, sub_item)
                            new_sub = os.path.join(new_item, sub_item)
                            self._migrate_item(old_sub, new_sub, retries=1)
                    else:
                        shutil.copytree(old_item, new_item)
                    
                    # 尝试删除原目录
                    try:
                        if not os.listdir(old_item):
                            os.rmdir(old_item)
                        else:
                            # 目录不为空，尝试删除其中的文件
                            for sub_item in os.listdir(old_item):
                                sub_path = os.path.join(old_item, sub_item)
                                try:
                                    if os.path.isdir(sub_path):
                                        shutil.rmtree(sub_path)
                                    else:
                                        os.remove(sub_path)
                                except:
                                    pass
                            # 再次尝试删除
                            try:
                                if not os.listdir(old_item):
                                    os.rmdir(old_item)
                            except:
                                pass
                    except:
                        # 无法删除，但已复制，返回skipped
                        return "skipped"
                    
                    return "success"
                else:
                    # 文件：先复制，再删除
                    if not os.path.exists(new_item):
                        shutil.copy2(old_item, new_item)
                    
                    # 尝试删除原文件
                    try:
                        os.remove(old_item)
                        return "success"
                    except PermissionError:
                        # 文件正在使用，但已复制，返回skipped
                        if attempt < retries - 1:
                            time.sleep(0.5)  # 等待后重试
                            continue
                        return "skipped"
                    except Exception as e:
                        if attempt < retries - 1:
                            time.sleep(0.5)
                            continue
                        return "failed"
            except PermissionError:
                # 文件正在使用
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
                # 尝试复制而不是移动
                try:
                    if not os.path.exists(new_item):
                        shutil.copy2(old_item, new_item)
                    return "skipped"
                except:
                    return "failed"
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
                return "failed"
        
        return "failed"
    
    def _force_remove_directory(self, dir_path):
        """强制删除目录及其所有内容，处理文件占用问题"""
        import shutil
        import time
        import stat
        
        if not os.path.exists(dir_path):
            return True
        
        try:
            # 先尝试使用 rmtree 直接删除（最快的方法）
            try:
                shutil.rmtree(dir_path, ignore_errors=False)
                if not os.path.exists(dir_path):
                    return True
            except:
                pass
            
            # 如果直接删除失败，逐步删除
            if os.path.isdir(dir_path):
                # 递归删除所有文件和子目录
                def remove_readonly(func, path, exc_info):
                    """处理只读文件的删除"""
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except:
                        pass
                
                # 使用自定义错误处理函数删除
                try:
                    shutil.rmtree(dir_path, onerror=remove_readonly)
                    if not os.path.exists(dir_path):
                        return True
                except:
                    pass
                
                # 如果还是失败，手动删除每个文件
                try:
                    items = list(os.listdir(dir_path))
                    for item in items:
                        item_path = os.path.join(dir_path, item)
                        try:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path, onerror=remove_readonly)
                            else:
                                try:
                                    os.chmod(item_path, stat.S_IWRITE)
                                    os.remove(item_path)
                                except:
                                    pass
                        except:
                            pass
                    
                    # 等待文件系统更新
                    time.sleep(0.3)
                    
                    # 再次尝试删除目录
                    try:
                        if not os.listdir(dir_path):
                            os.rmdir(dir_path)
                            return True
                        else:
                            # 强制删除剩余文件
                            remaining = list(os.listdir(dir_path))
                            for item in remaining:
                                item_path = os.path.join(dir_path, item)
                                try:
                                    if os.path.isdir(item_path):
                                        shutil.rmtree(item_path, onerror=remove_readonly)
                                    else:
                                        os.chmod(item_path, stat.S_IWRITE)
                                        os.remove(item_path)
                                except:
                                    pass
                            
                            # 最后尝试删除目录
                            time.sleep(0.2)
                            if not os.listdir(dir_path):
                                os.rmdir(dir_path)
                                return True
                            else:
                                # 使用 rmtree 最后一次尝试
                                shutil.rmtree(dir_path, ignore_errors=True)
                                result = not os.path.exists(dir_path)
                                return result
                    except Exception as e:
                        # 最后尝试：使用 rmtree 强制删除
                        shutil.rmtree(dir_path, ignore_errors=True)
                        result = not os.path.exists(dir_path)
                        return result
                except Exception as e2:
                    # 最后尝试：使用 rmtree 强制删除
                    shutil.rmtree(dir_path, ignore_errors=True)
                    return not os.path.exists(dir_path)
            else:
                # 如果是文件，直接删除
                try:
                    os.chmod(dir_path, stat.S_IWRITE)
                    os.remove(dir_path)
                    return True
                except:
                    return False
        except Exception as e:
            # 最后的尝试：使用 rmtree 强制删除
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
                return not os.path.exists(dir_path)
            except:
                return False
        
        return False
    
    def _delete_with_admin(self, dir_path):
        """使用管理员权限删除目录（通过启动管理员CMD）"""
        try:
            import subprocess
            import sys
            
            # 构建删除命令
            # 使用PowerShell的Remove-Item命令，支持强制删除
            ps_command = f'Remove-Item -Path "{dir_path}" -Recurse -Force -ErrorAction SilentlyContinue'
            
            # 使用PowerShell以管理员权限执行
            # 注意：这会弹出UAC提示
            cmd = [
                'powershell',
                '-Command',
                f'Start-Process powershell -ArgumentList "-Command", "{ps_command}" -Verb RunAs -Wait'
            ]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return not os.path.exists(dir_path)
            except subprocess.TimeoutExpired:
                return False
            except Exception as e:
                return False
        except Exception as e:
            return False
    
    def _schedule_delete_on_reboot(self, dir_path):
        """使用Windows API在系统重启时删除目录"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # Windows API: MoveFileEx with MOVEFILE_DELAY_UNTIL_REBOOT
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            
            kernel32 = ctypes.windll.kernel32
            MoveFileEx = kernel32.MoveFileExW
            MoveFileEx.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
            MoveFileEx.restype = wintypes.BOOL
            
            # 将路径转换为宽字符串
            path_wide = ctypes.c_wchar_p(dir_path)
            
            # 调用MoveFileEx，第二个参数为None表示删除
            result = MoveFileEx(path_wide, None, MOVEFILE_DELAY_UNTIL_REBOOT)
            return result != 0
        except Exception as e:
            return False
    
    def _cleanup_old_directories_on_startup(self):
        """程序启动时清理旧目录（如果存在且已迁移）"""
        try:
            # 读取配置文件，检查是否有待清理的旧目录
            config_file = self.get_config_file()
            if not os.path.exists(config_file):
                return
            
            # 检查默认位置的旧目录是否存在
            default_old_path = os.path.join(os.path.expanduser("~"), self.DEFAULT_MANAGER_FOLDER)
            current_path = self.manager_folder_path
            
            # 如果当前路径不是默认路径，且默认路径存在，尝试清理
            if os.path.normpath(current_path) != os.path.normpath(default_old_path):
                if os.path.exists(default_old_path):
                    # 检查旧目录是否为空或只包含logs目录
                    try:
                        items = os.listdir(default_old_path)
                        # 如果只有logs目录，尝试删除
                        if len(items) == 1 and items[0] == "logs":
                            logs_dir = os.path.join(default_old_path, "logs")
                            if os.path.isdir(logs_dir):
                                # 尝试删除logs目录
                                import shutil
                                try:
                                    shutil.rmtree(logs_dir, ignore_errors=True)
                                    # 如果logs删除成功，尝试删除父目录
                                    if not os.path.exists(logs_dir):
                                        try:
                                            os.rmdir(default_old_path)
                                        except:
                                            pass
                                except:
                                    pass
                        # 如果目录为空，直接删除
                        elif len(items) == 0:
                            try:
                                os.rmdir(default_old_path)
                            except:
                                pass
                    except:
                        pass
        except Exception as e:
            # 清理失败不影响程序启动
            pass
    
    def _close_logger_handlers(self):
        """关闭Logger的所有文件句柄，释放日志文件"""
        try:
            from core.logger import Logger
            import logging
            
            logger_instance = Logger()
            
            # 关闭所有文件处理器，特别是文件处理器
            handlers_to_remove = []
            for handler in logger_instance.logger.handlers[:]:
                try:
                    # 如果是文件处理器，确保完全关闭
                    if isinstance(handler, logging.FileHandler):
                        handler.flush()  # 刷新缓冲区
                        handler.close()  # 关闭文件句柄
                    else:
                        handler.close()
                    handlers_to_remove.append(handler)
                except:
                    pass
            
            # 移除所有处理器
            for handler in handlers_to_remove:
                try:
                    logger_instance.logger.removeHandler(handler)
                except:
                    pass
            
            # 强制刷新logger
            logger_instance.logger.handlers = []
            
            # 等待文件系统更新
            import time
            time.sleep(0.3)
            
            # 重新初始化Logger（使用新路径）
            logger_instance._initialize_logger()
        except Exception as e:
            # 如果关闭失败，不影响迁移流程
            pass
    
    def _update_environment_variables(self, old_path, new_path):
        """更新环境变量，将旧路径替换为新路径"""
        try:
            from core.system_config import SystemConfig
            sys_config = SystemConfig()
            
            # 环境变量映射
            env_var_map = {
                "JDK": "JAVA_HOME",
                "Node.js": "NODE_HOME",
                "Maven": ["MAVEN_HOME", "M2_HOME"],  # Maven有两个环境变量
                "Redis": "REDIS_HOME",
                "Python": "PYTHON_HOME"
            }
            
            # 环境名称到文件夹名称的映射
            env_folder_map = {
                "JDK": "jdk",
                "Node.js": "nodejs",
                "Maven": "maven",
                "Redis": "redis",
                "Python": "python"
            }
            
            updated_vars = []
            
            for env_name, var_names in env_var_map.items():
                if not isinstance(var_names, list):
                    var_names = [var_names]
                
                folder_name = env_folder_map.get(env_name)
                if not folder_name:
                    continue
                    
                old_env_path = os.path.join(old_path, "apps", folder_name)
                new_env_path = os.path.join(new_path, "apps", folder_name)
                
                for var_name in var_names:
                    current_value = sys_config.get_env_variable(var_name)
                    
                    if current_value:
                        # 检查是否是旧路径下的环境
                        current_normalized = os.path.normpath(current_value)
                        old_env_normalized = os.path.normpath(old_env_path)
                        
                        # 如果环境变量指向旧路径，更新为新路径
                        if current_normalized.startswith(old_env_normalized):
                            # 计算相对路径
                            if current_normalized == old_env_normalized:
                                new_value = new_env_path
                            else:
                                # 保持相对结构
                                try:
                                    relative = os.path.relpath(current_normalized, old_env_normalized)
                                    new_value = os.path.join(new_env_path, relative)
                                except ValueError:
                                    # 如果路径不在同一驱动器，使用新路径
                                    new_value = new_env_path
                            
                            # 更新环境变量
                            if sys_config.set_env_variable(var_name, new_value):
                                updated_vars.append(f"{var_name}: {current_value} -> {new_value}")
                            
                            # 更新PATH中的相关路径
                            self._update_path_in_path_var(sys_config, current_value, new_value)
            
            if updated_vars:
                return True, f"已更新 {len(updated_vars)} 个环境变量"
            else:
                return True, "无需更新环境变量"
        except Exception as e:
            return False, str(e)
    
    def _update_path_in_path_var(self, sys_config, old_path, new_path):
        """更新PATH环境变量中的路径"""
        try:
            import winreg
            current_path = sys_config.get_env_variable("PATH")
            if not current_path:
                return
            
            paths = [p.strip() for p in current_path.split(";") if p.strip()]
            updated = False
            
            for i, path in enumerate(paths):
                path_normalized = os.path.normpath(path)
                old_path_normalized = os.path.normpath(old_path)
                
                # 如果PATH中的路径在旧路径下，更新为新路径
                if path_normalized.startswith(old_path_normalized):
                    try:
                        relative = os.path.relpath(path_normalized, old_path_normalized)
                        new_path_value = os.path.join(new_path, relative)
                    except ValueError:
                        # 如果路径不在同一驱动器，使用新路径
                        new_path_value = new_path
                    paths[i] = new_path_value
                    updated = True
            
            if updated:
                new_path_val = ";".join(paths)
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                        _, type_ = winreg.QueryValueEx(key, "PATH")
                except:
                    type_ = winreg.REG_EXPAND_SZ
                
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, "PATH", 0, type_, new_path_val)
                sys_config._notify_system_change()
        except Exception as e:
            if self._init_logger:
                self._init_logger.warning(f"更新PATH失败: {e}")
    
    def _update_history_paths(self, old_path, new_path):
        """更新历史记录文件中的路径"""
        try:
            from core.history import HistoryManager
            history_manager = HistoryManager()
            records = history_manager.get_records()
            
            updated = False
            for record in records:
                record_path = record.get('path', '')
                if record_path and os.path.normpath(record_path).startswith(os.path.normpath(old_path)):
                    # 计算新路径
                    relative = os.path.relpath(os.path.normpath(record_path), os.path.normpath(old_path))
                    new_record_path = os.path.join(new_path, relative)
                    
                    # 更新记录
                    record['path'] = new_record_path
                    updated = True
            
            if updated:
                # 保存更新后的记录
                data = {"installed": records}
                history_file = self.get_history_file()
                with open(history_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            if self._init_logger:
                self._init_logger.warning(f"更新历史记录失败: {e}")
    
    def get_manager_folder_name(self):
        """获取统一管理文件夹名称（不含路径）"""
        return os.path.basename(self.manager_folder_path)
    
    def get_downloads_dir(self):
        """获取下载目录路径"""
        return os.path.join(self.manager_folder_path, "downloads")
    
    def get_logs_dir(self):
        """获取日志目录路径"""
        return os.path.join(self.manager_folder_path, "logs")
    
    def get_config_dir(self):
        """获取配置目录路径"""
        return os.path.join(self.manager_folder_path, "config")
    
    def get_apps_dir(self):
        """获取apps目录路径（所有环境统一安装在此目录下）"""
        return os.path.join(self.manager_folder_path, "apps")
    
    def get_config_file(self):
        """获取配置文件路径"""
        return os.path.join(self.get_config_dir(), "config.json")
    
    def get_history_file(self):
        """获取历史记录文件路径"""
        return os.path.join(self.get_config_dir(), "installed.json")
    
    def get_env_install_path(self, env_name):
        """获取指定环境的安装路径（在统一管理文件夹下的apps目录中）"""
        # 环境名称映射到文件夹名称
        env_folder_map = {
            "JDK": "jdk",
            "Node.js": "nodejs",
            "Maven": "maven",
            "Redis": "redis",
            "Python": "python"
        }
        folder_name = env_folder_map.get(env_name, env_name.lower())
        return os.path.join(self.get_apps_dir(), folder_name)
    
    def _save_config(self):
        """保存配置到文件"""
        config_file = self.get_config_file()
        
        try:
            data = {
                "manager_folder": self.get_manager_folder_name(),
                "manager_folder_path": self.manager_folder_path,
                "last_run_version": self.last_run_version
            }
            
            # 确保配置目录存在
            config_dir = os.path.dirname(config_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            # 如果保存失败，尝试保存到程序目录（向后兼容）
            try:
                fallback_file = os.path.join(os.getcwd(), "config.json")
                data = {
                    "manager_folder": self.get_manager_folder_name(),
                    "manager_folder_path": self.manager_folder_path,
                    "last_run_version": self.last_run_version
                }
                with open(fallback_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            except Exception as e2:
                pass
