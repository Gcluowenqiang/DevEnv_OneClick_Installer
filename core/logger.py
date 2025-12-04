import logging
import os
import sys
from datetime import datetime

class Logger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialize_logger()
        return cls._instance

    def _initialize_logger(self):
        self.logger = logging.getLogger("DevEnvInstaller")
        self.logger.setLevel(logging.INFO)
        
        # 使用统一管理文件夹下的logs目录
        try:
            from core.config import ConfigManager
            config_manager = ConfigManager()
            logs_dir = config_manager.get_logs_dir()
        except Exception:
            # 如果ConfigManager初始化失败，使用程序目录下的logs（向后兼容）
            logs_dir = os.path.join(os.getcwd(), "logs")
        
        # Create logs directory if it doesn't exist
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(logs_dir, f"install_{timestamp}.log")
        
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.gui_callback = None

    def set_gui_callback(self, callback):
        """Set a callback function to update GUI logs"""
        self.gui_callback = callback

    def info(self, message):
        self.logger.info(message)
        if self.gui_callback:
            self.gui_callback(f"[INFO] {message}")

    def error(self, message):
        self.logger.error(message)
        if self.gui_callback:
            self.gui_callback(f"[ERROR] {message}")

    def warning(self, message):
        self.logger.warning(message)
        if self.gui_callback:
            self.gui_callback(f"[WARN] {message}")


