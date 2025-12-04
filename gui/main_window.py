import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from core.logger import Logger
from core.history import HistoryManager
from core.config import ConfigManager
from core.updater import Updater
from core.version import APP_VERSION
import threading
import os
import json
import time

class MainWindow:
    def __init__(self):
        self.logger = Logger()
        self.history_manager = HistoryManager()
        self.config_manager = ConfigManager()
        self.updater = Updater(self.config_manager)
        
        self.root = ttk.Window(themename="cosmo")
        self.root.title(f"DevEnv OneClick Installer v{APP_VERSION}")
        self.root.geometry("900x700")
        
        self.logger.set_gui_callback(self.append_log)
        
        self._init_ui()
        self._init_menu()
        
        # Check for first run after update
        self.root.after(1000, self._check_first_run_after_update)
        
    def _init_menu(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label=f"当前版本: v{APP_VERSION}", state="disabled")
        help_menu.add_separator()
        help_menu.add_command(label="检查更新", command=self._check_update)
    
    def _check_first_run_after_update(self):
        last_version = self.config_manager.get_last_run_version()
        if last_version != APP_VERSION:
            # 如果是版本变更（或者是首次运行）
            # 尝试获取更新日志（如果是首次运行，可能不需要显示更新日志，或者是欢迎信息）
            # 这里我们做一个简单的判断：如果 last_version 不是 0.0.0，说明是更新
            if last_version != "0.0.0":
                # 尝试从 GitHub 获取 release notes (异步)
                threading.Thread(target=self._show_release_notes_async, args=(APP_VERSION,), daemon=True).start()
            
            # 更新本地记录的版本号
            self.config_manager.set_last_run_version(APP_VERSION)

    def _show_release_notes_async(self, current_version):
        try:
            # 尝试获取最新版本的 Release Notes
            has_update, latest_tag, body, _ = self.updater.check_for_updates()
            
            # 如果 GitHub 上最新的 tag 与当前运行版本一致，显示该 release notes
            if latest_tag and latest_tag.lstrip('v') == current_version.lstrip('v'):
                def _show():
                    # 创建一个简单的弹窗显示日志
                    top = ttk.Toplevel(self.root)
                    top.title(f"版本更新 v{current_version}")
                    top.geometry("600x400")
                    # Center
                    x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 300
                    y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 200
                    top.geometry(f"+{x}+{y}")
                    
                    ttk.Label(top, text=f"欢迎使用新版本 v{current_version}！", font=("微软雅黑", 12, "bold")).pack(pady=10)
                    ttk.Label(top, text="更新日志:", anchor="w").pack(fill=X, padx=10)
                    
                    text_frame = ttk.Frame(top)
                    text_frame.pack(fill=BOTH, expand=YES, padx=10, pady=5)
                    
                    text = tk.Text(text_frame, height=10, font=("Consolas", 10))
                    text.pack(side=LEFT, fill=BOTH, expand=YES)
                    text.insert(END, body)
                    text.configure(state="disabled")
                    
                    scroll = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
                    scroll.pack(side=RIGHT, fill=Y)
                    text.configure(yscrollcommand=scroll.set)
                    
                    ttk.Button(top, text="确定", command=top.destroy).pack(pady=10)
                    
                self.root.after(0, _show)
            else:
                 self.root.after(0, lambda: messagebox.showinfo("更新成功", f"欢迎使用新版本 v{current_version}！"))
        except:
             self.root.after(0, lambda: messagebox.showinfo("更新成功", f"欢迎使用新版本 v{current_version}！"))

    def _check_update(self):
        """手动检查更新"""
        self.logger.info("正在检查更新...")
        threading.Thread(target=self._do_check_update, daemon=True).start()

    def _do_check_update(self):
        try:
            has_update, version, body, download_url = self.updater.check_for_updates()
            
            def _on_result():
                if has_update:
                    msg = f"发现新版本: v{version}\n\n更新内容:\n{body}\n\n是否立即更新？"
                    if messagebox.askyesno("发现新版本", msg):
                        self._start_update_download(download_url)
                else:
                    messagebox.showinfo("检查更新", f"当前已是最新版本 (v{APP_VERSION})")
                    self.logger.info("当前已是最新版本。")
            
            self.root.after(0, _on_result)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"检查更新失败: {e}"))

    def _start_update_download(self, url):
        """开始下载更新"""
        # 显示进度弹窗
        progress_win = ttk.Toplevel(self.root)
        progress_win.title("正在下载更新")
        progress_win.geometry("400x150")
        # Center the window
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 200
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 75
        progress_win.geometry(f"+{x}+{y}")
        
        ttk.Label(progress_win, text="正在下载新版本，请稍候...", padding=10).pack()
        
        pb = ttk.Progressbar(progress_win, maximum=100, length=300, mode='determinate')
        pb.pack(pady=10)
        
        status_lbl = ttk.Label(progress_win, text="0%")
        status_lbl.pack()
        
        def _update_pb(val):
            pb['value'] = val
            status_lbl.configure(text=f"{int(val)}%")
            
        def _download_task():
            try:
                save_path = self.updater.download_update(url, lambda v: self.root.after(0, _update_pb, v))
                self.root.after(0, lambda: _on_download_complete(save_path))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("更新失败", f"下载失败: {e}"))
                self.root.after(0, progress_win.destroy)

        def _on_download_complete(save_path):
            progress_win.destroy()
            if messagebox.askyesno("下载完成", "新版本下载完成，是否立即重启进行安装？\n\n程序将自动关闭并完成更新。"):
                # 先启动更新脚本
                success, msg = self.updater.perform_update(save_path)
                if success:
                    # 延迟关闭窗口，确保更新脚本已启动
                    def _close_app():
                        try:
                            self.root.destroy()
                        except:
                            import sys
                            sys.exit(0)
                    self.root.after(500, _close_app)
                else:
                    messagebox.showerror("更新失败", msg)

        threading.Thread(target=_download_task, daemon=True).start()

    def _init_ui(self):
        # 1. Header
        header_frame = ttk.Frame(self.root, padding=10)
        header_frame.pack(fill=X)
        ttk.Label(header_frame, text="开发环境一键安装工具", font=("微软雅黑", 18, "bold")).pack(side=LEFT)
        
        # 2. Create Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=BOTH, expand=YES, padx=10, pady=5)
        
        # Tab 1: 安装/卸载环境
        self.install_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.install_frame, text="安装/卸载环境")
        self._init_install_tab()
        
        # Tab 2: 安装历史
        self.history_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.history_tab_frame, text="安装历史")
        self._init_history_tab()
        
        # Tab 3: 设置
        self.settings_tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_tab_frame, text="设置")
        self._init_settings_tab()
        
        # Bind tab change event to refresh history
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        
        # 3. Log/Progress Area (Always visible)
        log_frame = ttk.Labelframe(self.root, text="系统日志", padding=10)
        log_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Progress Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(log_frame, variable=self.progress_var, maximum=100, bootstyle=STRIPED)
        self.progress_bar.pack(fill=X, pady=(0, 5))
        
        # Log Text
        self.log_text = tk.Text(log_frame, height=8, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=YES)
        
        # Scrollbar for Log
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Initialize with JDK options
        self._load_versions("JDK")

    def _init_install_tab(self):
        """Initialize the install/uninstall tab"""
        content_frame = ttk.Labelframe(self.install_frame, text="环境配置", padding=10)
        content_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # Grid layout for content
        content_frame.columnconfigure(1, weight=1)
        
        # Action Selection (Install/Uninstall)
        action_frame = ttk.Frame(content_frame)
        action_frame.grid(row=0, column=0, columnspan=2, sticky=EW, pady=(0, 10))
        
        self.action_var = tk.StringVar(value="install")
        ttk.Radiobutton(action_frame, text="安装环境", variable=self.action_var, value="install", command=self._on_mode_change).pack(side=LEFT, padx=10)
        ttk.Radiobutton(action_frame, text="卸载环境", variable=self.action_var, value="uninstall", command=self._on_mode_change).pack(side=LEFT, padx=10)
        
        # Environment Type Selection
        ttk.Label(content_frame, text="选择环境:").grid(row=1, column=0, sticky=W, pady=5)
        self.env_var = tk.StringVar(value="JDK")
        env_combo = ttk.Combobox(content_frame, textvariable=self.env_var, values=["JDK", "Node.js", "Maven", "Redis", "Python"], state="readonly")
        env_combo.grid(row=1, column=1, sticky=EW, padx=5, pady=5)
        env_combo.bind("<<ComboboxSelected>>", self._on_env_change)
        
        # Version Selection
        self.version_lbl = ttk.Label(content_frame, text="选择版本:")
        self.version_lbl.grid(row=2, column=0, sticky=W, pady=5)
        self.version_var = tk.StringVar()
        self.version_combo = ttk.Combobox(content_frame, textvariable=self.version_var, state="readonly")
        self.version_combo.grid(row=2, column=1, sticky=EW, padx=5, pady=5)
        
        # Install Path Display (只读显示，不提供自定义)
        self.path_lbl = ttk.Label(content_frame, text="安装目录:")
        self.path_lbl.grid(row=3, column=0, sticky=W, pady=5)
        path_frame = ttk.Frame(content_frame)
        path_frame.grid(row=3, column=1, sticky=EW, padx=5, pady=5)
        
        # 使用统一管理文件夹下的apps目录
        self.path_var = tk.StringVar()
        self._update_install_path()
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var, state="readonly")
        self.path_entry.pack(side=LEFT, fill=X, expand=YES)
        
        # 提示信息
        self.tip_label = ttk.Label(content_frame, text="提示: 所有环境统一安装在DevEnvManager/apps目录下，路径固定不可修改", 
                             font=("微软雅黑", 8), foreground="gray")
        self.tip_label.grid(row=4, column=0, columnspan=2, sticky=W, padx=5, pady=(0, 5))

        # Dynamic Config Area
        self.config_frame = ttk.Labelframe(content_frame, text="高级配置", padding=10)
        self.config_frame.grid(row=5, column=0, columnspan=2, sticky=EW, padx=5, pady=10)
        self.config_widgets = {}
        
        # Action Buttons
        action_frame_btn = ttk.Frame(content_frame)
        action_frame_btn.grid(row=6, column=0, columnspan=2, pady=20)
        
        self.action_btn = ttk.Button(action_frame_btn, text="开始安装", command=self._start_action, bootstyle=SUCCESS, width=20)
        self.action_btn.pack()

    def _init_history_tab(self):
        """Initialize the history tab"""
        history_frame = ttk.Labelframe(self.history_tab_frame, text="已安装环境", padding=10)
        history_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        # History Treeview
        columns = ("env", "version", "path", "date")
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show="headings", height=15)
        self.history_tree.heading("env", text="环境")
        self.history_tree.heading("version", text="版本")
        self.history_tree.heading("path", text="路径")
        self.history_tree.heading("date", text="安装时间")
        
        self.history_tree.column("env", width=100)
        self.history_tree.column("version", width=150)
        self.history_tree.column("path", width=400)
        self.history_tree.column("date", width=180)
        
        self.history_tree.pack(side=LEFT, fill=BOTH, expand=YES)
        
        # Scrollbar for tree
        tree_scroll = ttk.Scrollbar(history_frame, orient="vertical", command=self.history_tree.yview)
        tree_scroll.pack(side=RIGHT, fill=Y)
        self.history_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.history_tree.bind("<<TreeviewSelect>>", self._on_history_select)
        self.history_tree.bind("<Double-1>", self._on_history_double_click)
        
        # Load history on init
        self._load_history_list()
    
    def _init_settings_tab(self):
        """Initialize the settings tab"""
        settings_frame = ttk.Labelframe(self.settings_tab_frame, text="统一管理文件夹设置", padding=10)
        settings_frame.pack(fill=BOTH, expand=YES, padx=10, pady=10)
        
        settings_frame.columnconfigure(1, weight=1)
        
        # 说明文字
        info_label = ttk.Label(settings_frame, 
                              text="所有开发环境将统一安装在此文件夹下的apps目录中，便于集中管理。\n安装路径固定，不可自定义。",
                              font=("微软雅黑", 9), foreground="gray")
        info_label.grid(row=0, column=0, columnspan=3, sticky=W, pady=(0, 15))
        
        # 统一管理文件夹路径
        ttk.Label(settings_frame, text="统一管理文件夹:").grid(row=1, column=0, sticky=W, pady=5)
        
        manager_path_frame = ttk.Frame(settings_frame)
        manager_path_frame.grid(row=1, column=1, sticky=EW, padx=5, pady=5)
        manager_path_frame.columnconfigure(0, weight=1)
        
        self.manager_path_var = tk.StringVar()
        self.manager_path_var.set(self.config_manager.get_manager_folder_path())
        ttk.Entry(manager_path_frame, textvariable=self.manager_path_var).grid(row=0, column=0, sticky=EW, padx=(0, 5))
        ttk.Button(manager_path_frame, text="浏览", command=self._browse_manager_path, bootstyle=SECONDARY).grid(row=0, column=1)
        
        # 保存按钮
        save_btn = ttk.Button(settings_frame, text="保存设置", command=self._save_manager_path, bootstyle=SUCCESS, width=20)
        save_btn.grid(row=2, column=0, columnspan=3, pady=20)
        
        # 当前设置显示
        current_info_frame = ttk.Labelframe(settings_frame, text="当前设置", padding=10)
        current_info_frame.grid(row=3, column=0, columnspan=3, sticky=EW, pady=10)
        
        self.current_info_text = tk.Text(current_info_frame, height=6, state="disabled", font=("Consolas", 9))
        self.current_info_text.pack(fill=BOTH, expand=YES)
        self._update_settings_info()

    def _on_tab_change(self, event):
        """Handle tab change event"""
        selected_tab = self.notebook.index(self.notebook.select())
        if selected_tab == 1:  # History tab
            self._load_history_list()
        elif selected_tab == 2:  # Settings tab
            self._update_settings_info()
            # 更新路径输入框的值
            self.manager_path_var.set(self.config_manager.get_manager_folder_path())

    def _on_mode_change(self):
        mode = self.action_var.get()
        if mode == "install":
            self.version_lbl.grid()
            self.version_combo.grid()
            self.path_lbl.configure(text="安装目录:")
            self.path_entry.configure(state="readonly")
            self.tip_label.configure(text="提示: 所有环境统一安装在DevEnvManager/apps目录下，路径固定不可修改")
            self._on_env_change(None)
            self.action_btn.configure(text="开始安装", bootstyle=SUCCESS)
        else:
            self.version_lbl.grid_remove()
            self.version_combo.grid_remove()
            self.path_lbl.configure(text="目标目录:")
            self.path_entry.configure(state="normal")  # 卸载模式下可编辑，允许选择要卸载的目录
            self.tip_label.configure(text="提示: 请选择要卸载的环境目录，或从'安装历史'标签页双击选择")
            self.config_frame.grid_remove()
            self.action_btn.configure(text="开始卸载", bootstyle=DANGER)
            # Load history when switching to uninstall mode
            self._load_history_list()
            # 卸载模式下，路径可以手动选择（从历史记录中选择）
    
    def _load_history_list(self):
        """Load and display all installation history records"""
        # Clear existing
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
            
        try:
            records = self.history_manager.get_records()
            self.logger.info(f"Loading {len(records)} history records...")
            
            for r in records:
                self.history_tree.insert("", END, values=(r['env'], r['version'], r['path'], r['install_time']))
            
            if len(records) > 0:
                self.logger.info(f"Successfully loaded {len(records)} history records")
            else:
                self.logger.info("No installation history found")
        except Exception as e:
            self.logger.error(f"Failed to load history: {e}")

    def _on_history_select(self, event):
        """Handle history item selection - only auto-fill if in install tab, no auto-switch on single click"""
        selection = self.history_tree.selection()
        if not selection: return
        
        item = self.history_tree.item(selection[0])
        values = item['values'] # env, version, path, date
        if values:
            # Only auto-fill fields if already in install tab
            # Do NOT auto-switch tabs on single click - let users browse history freely
            if self.notebook.index(self.notebook.select()) == 0:  # Install tab
                self.env_var.set(values[0])
                self.path_var.set(values[2])
            # If in history tab, just select - no action needed

    def _on_history_double_click(self, event):
        """Handle history item double-click - switch to install tab and fill fields"""
        selection = self.history_tree.selection()
        if not selection: return
        
        item = self.history_tree.item(selection[0])
        values = item['values'] # env, version, path, date
        if values:
            # Switch to install tab and fill fields
            self.notebook.select(0)
            self.env_var.set(values[0])
            self.path_var.set(values[2])
            # Switch to uninstall mode since we're selecting from history
            self.action_var.set("uninstall")
            self._on_mode_change()

    def _browse_path(self):
        # 安装模式下不允许修改路径
        mode = self.action_var.get()
        if mode == "install":
            messagebox.showinfo("提示", "安装目录固定为DevEnvManager/apps目录，不可修改。\n\n如需修改统一管理文件夹位置，请前往'设置'标签页。")
            self.notebook.select(2)  # 切换到设置标签页
        else:
            # 卸载模式下，允许选择目录
            current_path = self.path_var.get()
            initial_dir = os.path.dirname(current_path) if current_path and os.path.exists(current_path) else os.path.expanduser("~")
            path = filedialog.askdirectory(initialdir=initial_dir, title="选择要卸载的环境目录")
        if path:
            self.path_var.set(path)

    def _on_env_change(self, event):
        env = self.env_var.get()
        self._load_versions(env)
        self._update_config_ui(env)
        self._update_install_path()
    
    def _update_install_path(self):
        """更新安装路径（基于统一管理文件夹）"""
        env = self.env_var.get()
        install_path = self.config_manager.get_env_install_path(env)
        self.path_var.set(install_path)
    
    def _browse_manager_path(self):
        """浏览选择统一管理文件夹"""
        current_path = self.manager_path_var.get()
        initial_dir = os.path.dirname(current_path) if os.path.exists(current_path) else os.path.expanduser("~")
        
        path = filedialog.askdirectory(initialdir=initial_dir, title="选择统一管理文件夹")
        if path:
            self.manager_path_var.set(path)
    
    def _save_manager_path(self):
        """保存统一管理文件夹设置"""
        new_path = self.manager_path_var.get().strip()
        if not new_path:
            messagebox.showerror("错误", "路径不能为空")
            return
        
        old_path = self.config_manager.get_manager_folder_path()
        if os.path.normpath(new_path) == os.path.normpath(old_path):
            messagebox.showinfo("提示", "路径未改变，无需迁移")
            return
        
        # 确认迁移
        confirm_msg = f"确定要将统一管理文件夹从:\n{old_path}\n\n迁移到:\n{new_path}\n\n" \
                      f"此操作将:\n" \
                      f"1. 迁移所有文件（downloads, logs, config, apps）\n" \
                      f"2. 更新所有环境变量（JAVA_HOME, NODE_HOME等）\n" \
                      f"3. 更新PATH环境变量\n" \
                      f"4. 更新安装历史记录\n" \
                      f"5. 尝试删除原目录（如失败将尝试管理员权限删除）\n\n" \
                      f"迁移过程可能需要一些时间，请耐心等待。\n" \
                      f"如需要管理员权限删除，将弹出UAC提示。"
        
        if not messagebox.askyesno("确认迁移", confirm_msg):
            return
        
        # 执行迁移
        self.logger.info(f"开始迁移统一管理文件夹: {old_path} -> {new_path}")
        success, message = self.config_manager.set_manager_folder_path(new_path, migrate_files=True)
        
        if success:
            self.logger.info(f"迁移成功: {message}")
            messagebox.showinfo("成功", f"统一管理文件夹迁移成功！\n\n{message}\n\n" \
                                      f"新路径: {new_path}\n\n" \
                                      f"所有文件已迁移，环境变量已更新。")
            self._update_install_path()
            self._update_settings_info()
            # 刷新历史记录显示
            self._load_history_list()
        else:
            self.logger.error(f"迁移失败: {message}")
            messagebox.showerror("迁移失败", f"统一管理文件夹迁移失败:\n\n{message}\n\n" \
                                          f"请检查路径是否有效，或查看日志了解详细信息。")
    
    def _update_settings_info(self):
        """更新设置信息显示"""
        manager_path = self.config_manager.get_manager_folder_path()
        manager_name = self.config_manager.get_manager_folder_name()
        
        info_text = f"统一管理文件夹名称: {manager_name}\n"
        info_text += f"完整路径: {manager_path}\n\n"
        info_text += "程序目录结构:\n"
        info_text += f"  • 下载目录: {self.config_manager.get_downloads_dir()}\n"
        info_text += f"  • 日志目录: {self.config_manager.get_logs_dir()}\n"
        info_text += f"  • 配置目录: {self.config_manager.get_config_dir()}\n"
        info_text += f"  • 应用目录: {self.config_manager.get_apps_dir()}\n"
        info_text += f"  • 配置文件: {self.config_manager.get_config_file()}\n"
        info_text += f"  • 历史记录: {self.config_manager.get_history_file()}\n\n"
        info_text += "各环境安装位置（固定路径）:\n"
        
        envs = ["JDK", "Node.js", "Maven", "Redis", "Python"]
        for env in envs:
            env_path = self.config_manager.get_env_install_path(env)
            info_text += f"  • {env}: {env_path}\n"
        
        self.current_info_text.configure(state="normal")
        self.current_info_text.delete(1.0, tk.END)
        self.current_info_text.insert(1.0, info_text)
        self.current_info_text.configure(state="disabled")

    def _update_config_ui(self, env):
        # Clear previous config widgets
        for widget in self.config_frame.winfo_children():
            widget.destroy()
        self.config_widgets = {}
        
        # Hide config frame by default, show if needed
        self.config_frame.grid_remove()

        if env == "Maven":
            self.config_frame.grid()
            ttk.Label(self.config_frame, text="本地仓库路径:").grid(row=0, column=0, sticky=W, pady=5)
            repo_var = tk.StringVar()
            entry = ttk.Entry(self.config_frame, textvariable=repo_var, width=40)
            entry.grid(row=0, column=1, sticky=EW, padx=5)
            
            def _browse_repo():
                p = filedialog.askdirectory()
                if p: repo_var.set(p)
            
            ttk.Button(self.config_frame, text="浏览", command=_browse_repo, bootstyle=SECONDARY).grid(row=0, column=2, padx=5)
            self.config_widgets['local_repo'] = repo_var
            
        elif env == "Redis":
            self.config_frame.grid()
            
            # First row: Port, Username, Password
            ttk.Label(self.config_frame, text="端口号:").grid(row=0, column=0, sticky=W, pady=5)
            port_var = tk.StringVar(value="6379")
            ttk.Entry(self.config_frame, textvariable=port_var, width=10).grid(row=0, column=1, sticky=W, padx=5)
            self.config_widgets['port'] = port_var
            
            ttk.Label(self.config_frame, text="用户名 (可选):").grid(row=0, column=2, sticky=W, pady=5, padx=(10,0))
            user_var = tk.StringVar()
            ttk.Entry(self.config_frame, textvariable=user_var, width=15).grid(row=0, column=3, sticky=W, padx=5)
            self.config_widgets['username'] = user_var
            
            ttk.Label(self.config_frame, text="密码 (可选):").grid(row=0, column=4, sticky=W, pady=5, padx=(10,0))
            pass_var = tk.StringVar()
            ttk.Entry(self.config_frame, textvariable=pass_var, width=15, show="*").grid(row=0, column=5, sticky=W, padx=5)
            self.config_widgets['password'] = pass_var
            
            # Service
            service_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(self.config_frame, text="注册为系统服务 (开机自启)", variable=service_var).grid(row=1, column=0, columnspan=6, sticky=W, pady=5)
            self.config_widgets['service'] = service_var

    def _load_versions(self, env):
        # Load from specific Installer classes
        self.version_combo.set("Loading...")
        self.version_combo['values'] = []
        
        def _fetch_and_update():
            try:
                versions = []
                if env == "JDK":
                    from impl.jdk import JDKInstaller
                    versions = JDKInstaller().get_version_list()
                elif env == "Node.js":
                    from impl.node import NodeInstaller
                    versions = NodeInstaller().get_version_list()
                elif env == "Maven":
                    from impl.maven import MavenInstaller
                    versions = MavenInstaller().get_version_list()
                elif env == "Redis":
                    from impl.redis import RedisInstaller
                    versions = RedisInstaller().get_version_list()
                elif env == "Python":
                    from impl.python import PythonInstaller
                    versions = PythonInstaller().get_version_list()
                
                def _update_ui():
                    self.version_combo['values'] = versions
                    if versions:
                        self.version_combo.current(0)
                    else:
                        self.version_combo.set("No versions found")
                
                self.root.after(0, _update_ui)
            except Exception as e:
                self.logger.error(f"Failed to load versions: {e}")
                self.root.after(0, lambda: self.version_combo.set("Error loading versions"))

        threading.Thread(target=_fetch_and_update, daemon=True).start()

    def _start_action(self):
        mode = self.action_var.get()
        env = self.env_var.get()
        path = self.path_var.get()
        
        if not path:
            messagebox.showerror("错误", "请选择目录")
            return

        if mode == "install":
            version = self.version_var.get()
            # Collect extra config
            extra_config = {}
            for key, var in self.config_widgets.items():
                extra_config[key] = var.get()

            # 1. Pre-check for existing environment
            installer = self._get_installer_instance(env)
            if installer:
                check_result = installer.check_existing()
                if check_result:
                    msg = f"检测到系统中已存在 {env}。\n\n" \
                          f"当前位置: {check_result.get('path', '未知')}\n" \
                          f"检测依据: {check_result.get('source', '环境变量')}\n\n" \
                          f"继续安装将把系统默认环境切换为: {version}\n" \
                          f"旧版本文件将被保留，但环境变量将被覆盖。"
                    
                    if not messagebox.askyesno("环境冲突提示", msg):
                        return

            self._toggle_ui_state(disabled=True)
            threading.Thread(target=self._run_task, args=(mode, env, version, path, extra_config), daemon=True).start()
        
        else: # Uninstall
             if not messagebox.askyesno("确认卸载", f"确定要卸载位于 {path} 的 {env} 吗？\n\n此操作将：\n1. 删除整个目录\n2. 移除相关环境变量\n3. 停止相关服务(如Redis)"):
                 return
             
             self._toggle_ui_state(disabled=True)
             threading.Thread(target=self._run_task, args=(mode, env, None, path, None), daemon=True).start()

    def _toggle_ui_state(self, disabled):
         state = "disabled" if disabled else "normal"
         self.action_btn.configure(state=state)
         if disabled:
             self.progress_var.set(0)
             self.log_text.configure(state="normal")
             self.log_text.delete(1.0, END)
             self.log_text.configure(state="disabled")

    def _run_task(self, mode, env, version, path, extra_config):
        try:
            installer = self._get_installer_instance(env)
            if not installer:
                self.logger.warning(f"{env} not yet implemented.")
                return

            if mode == "install":
                self.logger.info(f"Starting installation of {env} {version} to {path}...")
                installer.install(version, path, self._update_progress, extra_config=extra_config)
                # Record success history - save the actual installation path
                # Get actual path from environment variable (which points to the real install location)
                actual_path = path
                env_var_map = {
                    "JDK": "JAVA_HOME",
                    "Node.js": "NODE_HOME",
                    "Maven": "MAVEN_HOME",
                    "Redis": "REDIS_HOME",
                    "Python": "PYTHON_HOME"
                }
                env_var_name = env_var_map.get(env)
                if env_var_name:
                    from core.system_config import SystemConfig
                    sys_config = SystemConfig()
                    env_path = sys_config.get_env_variable(env_var_name)
                    if env_path and os.path.exists(env_path):
                        actual_path = env_path
                        self.logger.info(f"Using actual install path from {env_var_name}: {actual_path}")
                
                self.history_manager.add_record(env, version, actual_path)
                # Refresh history list in both tabs
                self.root.after(0, self._load_history_list)
                messagebox.showinfo("完成", f"{env} 安装成功！")
            else:
                self.logger.info(f"Starting uninstallation of {env} from {path}...")
                installer.uninstall(path, self._update_progress)
                # Remove from history
                self.history_manager.remove_record(path)
                # Refresh history list
                self.root.after(0, self._load_history_list)
                messagebox.showinfo("完成", f"{env} 卸载成功！")
            
            self.logger.info("Process finished.")
            
        except Exception as e:
            self.logger.error(f"Error: {str(e)}")
            messagebox.showerror("错误", f"操作失败: {str(e)}")
        finally:
            self.root.after(0, lambda: self._toggle_ui_state(disabled=False))

    def _get_installer_instance(self, env):
        if env == "JDK":
            from impl.jdk import JDKInstaller
            return JDKInstaller()
        elif env == "Node.js":
            from impl.node import NodeInstaller
            return NodeInstaller()
        elif env == "Maven":
            from impl.maven import MavenInstaller
            return MavenInstaller()
        elif env == "Redis":
            from impl.redis import RedisInstaller
            return RedisInstaller()
        elif env == "Python":
            from impl.python import PythonInstaller
            return PythonInstaller()
        return None

    def _update_progress(self, value):
        self.progress_var.set(value)

    def append_log(self, message):
        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert(END, message + "\n")
            self.log_text.see(END)
            self.log_text.configure(state="disabled")
        
        self.root.after(0, _append)

    def run(self):
        self.root.mainloop()
