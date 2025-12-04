import json
import os
from datetime import datetime
from core.logger import Logger

class HistoryManager:
    def __init__(self):
        self.logger = Logger()
        # 使用统一管理文件夹下的配置文件
        from core.config import ConfigManager
        config_manager = ConfigManager()
        self.history_file = config_manager.get_history_file()
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.history_file):
            self._save_data({"installed": []})

    def _load_data(self):
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load history: {e}")
            return {"installed": []}

    def _save_data(self, data):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save history: {e}")

    def add_record(self, env, version, path):
        """Add or update an installation record"""
        data = self._load_data()
        records = data.get("installed", [])
        
        # Check if path already exists, update it if so
        # Or check if env+version exists? A user might reinstall to a new path.
        # Let's key primarily by Path, as that's unique for an installation on disk.
        
        # Remove existing record with same path to avoid duplicates
        records = [r for r in records if os.path.normpath(r['path']) != os.path.normpath(path)]
        
        new_record = {
            "env": env,
            "version": version,
            "path": path,
            "install_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        records.append(new_record)
        
        data["installed"] = records
        self._save_data(data)
        self.logger.info(f"History updated: Added {env} at {path}")

    def remove_record(self, path):
        """Remove a record by path"""
        data = self._load_data()
        records = data.get("installed", [])
        
        initial_len = len(records)
        records = [r for r in records if os.path.normpath(r['path']) != os.path.normpath(path)]
        
        if len(records) < initial_len:
            data["installed"] = records
            self._save_data(data)
            self.logger.info(f"History updated: Removed record for {path}")

    def get_records(self):
        """Get all installation records"""
        return self._load_data().get("installed", [])

