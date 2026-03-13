import os
import sys
import threading
import queue
import re
import io
from datetime import datetime
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import requests

# 设置环境变量，告知核心模块这是GUI模式
os.environ["QZONE_GUI"] = "1"

# 设置外观模式和主题
ctk.set_appearance_mode("Dark")  # Modes: "System" (standard), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (standard), "green", "dark-blue"

class QueueWriter:
    """重定向 stdout/stderr 到队列"""
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, message):
        if message:
            self.log_queue.put(message)

    def flush(self):
        return

class QzoneGuiApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- 窗口基础设置 ---
        self.title("QQ空间历史动态导出工具")
        
        # 获取屏幕尺寸以计算居中
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 1100
        window_height = 750
        x_pos = (screen_width - window_width) // 2
        y_pos = (screen_height - window_height) // 2
        self.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
        self.minsize(900, 600)
        
        # --- 字体设置 ---
        self.font_title = ("Microsoft YaHei UI", 20, "bold")
        self.font_subtitle = ("Microsoft YaHei UI", 14, "bold")
        self.font_body = ("Microsoft YaHei UI", 12)
        self.font_small = ("Microsoft YaHei UI", 11)
        self.font_log = ("Consolas", 10)  # 日志还是用等宽字体好

        # --- 数据与状态 ---
        self.log_queue = queue.Queue()
        self.worker_thread = None
        self.login_thread = None
        self.login_session_id = None
        self.qr_image = None
        self.fetch_mode_var = tk.StringVar(value="full")  # 默认获取全部（含已删除）
        self.current_texts = []  # 存储当前获取的动态数据
        empty_pil = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        self.empty_qr_image = ctk.CTkImage(light_image=empty_pil, dark_image=empty_pil, size=(160, 160))
        self.last_qr_mtime = None
        self.history_runs = []

        import util.ConfigUtil as Config
        self.config = Config
        self.config.init_flooder()
        self.qr_path = os.path.abspath(os.path.join(self.config.temp_path, "QR.png"))

        # --- 构建界面 ---
        self._build_ui()
        
        # --- 初始化逻辑 ---
        self.refresh_users()
        self._poll_log_queue()
        self._poll_worker_status()
        self._poll_qr_image()

        # 打印版本信息
        self.exe_path = os.path.abspath(sys.argv[0])
        try:
            mtime = os.path.getmtime(self.exe_path)
            build_stamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        except:
            build_stamp = "Unknown"
        self._log(f"Version: {build_stamp}\nPath: {self.exe_path}\n")

        # 自动启动登录流程
        if not self.config.selected_user_file:
             self.force_relogin()

    def _build_ui(self):
        """构建主界面布局"""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # === 1. 左侧边栏 ===
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1) # 让历史记录列表占据剩余空间

        # 标题 Logo
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="QQ空间导出助手", font=self.font_title)
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # 新建任务按钮
        self.new_task_btn = ctk.CTkButton(self.sidebar_frame, text="+ 新建任务 / 切换账号", 
                                          command=self.force_relogin, font=self.font_body, height=36, corner_radius=18)
        self.new_task_btn.grid(row=1, column=0, padx=20, pady=10)

        # 用户列表
        ctk.CTkLabel(self.sidebar_frame, text="已登录账号:", anchor="w", font=self.font_small, text_color="gray70").grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        
        # 使用 Listbox 需要包装一下，因为 CTk 没有原生 Listbox，这里用 ScrollableFrame + Buttons 模拟，或者直接嵌入 tk.Listbox
        # 为了美观，我们用 tk.Listbox 但去掉边框，通过 Frame 包装
        self.user_list_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.user_list_frame.grid(row=3, column=0, padx=20, pady=(5, 10), sticky="ew")
        
        self.user_listbox = tk.Listbox(self.user_list_frame, height=5, bg="#2b2b2b", fg="white", 
                                       selectbackground="#1f538d", borderwidth=0, highlightthickness=0, font=("Microsoft YaHei UI", 11))
        self.user_listbox.pack(fill="both", expand=True)
        self.user_listbox.bind("<<ListboxSelect>>", self._on_user_select)

        # 历史记录
        ctk.CTkLabel(self.sidebar_frame, text="运行历史:", anchor="w", font=self.font_small, text_color="gray70").grid(row=4, column=0, padx=20, pady=(10, 0), sticky="nw")
        
        self.history_list_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.history_list_frame.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="nsew")
        
        self.run_listbox = tk.Listbox(self.history_list_frame, bg="#2b2b2b", fg="white", 
                                      selectbackground="#1f538d", borderwidth=0, highlightthickness=0, font=("Microsoft YaHei UI", 11))
        self.run_listbox.pack(fill="both", expand=True)
        self.run_listbox.bind("<<ListboxSelect>>", self._on_run_select)


        # === 2. 右侧主内容区 ===
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(2, weight=1) # 日志区域自适应

        # --- 顶部：状态卡片 ---
        self.top_panel = ctk.CTkFrame(self.main_frame, fg_color=("gray85", "gray17"))
        self.top_panel.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        self.top_panel.grid_columnconfigure(1, weight=1)

        # 二维码/登录区域
        self.qr_frame = ctk.CTkFrame(self.top_panel, width=200, height=240, corner_radius=16,
                                     fg_color=("gray90", "gray18"))
        self.qr_frame.grid(row=0, column=0, rowspan=2, padx=20, pady=20)
        self.qr_frame.grid_propagate(False)

        self.qr_label = ctk.CTkLabel(
            self.qr_frame,
            text="等待生成二维码...",
            font=self.font_small,
            width=160,
            height=160,
            corner_radius=12,
            fg_color=("gray85", "gray22"),
            image=self.empty_qr_image,
            compound="center",
        )
        self.qr_label.pack(padx=12, pady=(12, 6))

        self.qr_action_frame = ctk.CTkFrame(self.qr_frame, fg_color="transparent")
        self.qr_action_frame.pack(fill="x", padx=12, pady=(4, 12))

        self.refresh_qr_btn = ctk.CTkButton(
            self.qr_action_frame,
            text="刷新二维码",
            command=self.force_relogin,
            height=28,
            corner_radius=14,
            font=self.font_small,
        )
        self.refresh_qr_btn.pack(fill="x", pady=(0, 6))

        self.qr_debug_btn = ctk.CTkButton(
            self.qr_action_frame,
            text="二维码诊断",
            command=self.debug_qr,
            height=28,
            corner_radius=14,
            font=self.font_small,
            fg_color="transparent",
            border_width=1,
            text_color=("gray10", "#DCE4EE"),
        )
        self.qr_debug_btn.pack(fill="x")

        # 信息区域
        self.info_frame = ctk.CTkFrame(self.top_panel, fg_color="transparent")
        self.info_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=20)
        
        self.status_label = ctk.CTkLabel(self.info_frame, text="等待操作", font=self.font_title, anchor="w")
        self.status_label.pack(anchor="w")

        self.account_info_label = ctk.CTkLabel(self.info_frame, text="当前未登录", font=self.font_body, text_color="gray70", anchor="w")
        self.account_info_label.pack(anchor="w", pady=(5, 0))
        
        self.progress_bar = ctk.CTkProgressBar(self.info_frame)
        self.progress_bar.pack(fill="x", pady=(15, 5))
        self.progress_bar.set(0)
        
        self.progress_label = ctk.CTkLabel(self.info_frame, text="就绪", font=self.font_small, text_color="gray60", anchor="w")
        self.progress_label.pack(anchor="w")

        # 操作按钮区域
        self.action_frame = ctk.CTkFrame(self.top_panel, fg_color="transparent")
        self.action_frame.grid(row=0, column=2, padx=20, pady=20, sticky="ns")
        
        # 获取模式选择
        ctk.CTkLabel(self.action_frame, text="获取模式:", font=self.font_small, text_color="gray70").pack(anchor="w")
        self.fetch_mode_menu = ctk.CTkOptionMenu(
            self.action_frame, 
            values=["全部动态(含已删除)", "仅可见动态"],
            command=self._on_fetch_mode_change,
            width=140,
            height=30,
            corner_radius=15,
            font=self.font_small
        )
        self.fetch_mode_menu.set("全部动态(含已删除)")
        self.fetch_mode_menu.pack(pady=(5, 10))
        
        self.start_btn = ctk.CTkButton(self.action_frame, text="开始获取", command=self.start_fetch, 
                                       font=self.font_subtitle, height=45, width=140, corner_radius=22)
        self.start_btn.pack(pady=(0, 10))
        
        self.open_dir_btn = ctk.CTkButton(self.action_frame, text="打开结果目录", command=self.open_result_dir, 
                                          fg_color="transparent", border_width=2, text_color=("gray10", "#DCE4EE"),
                                          font=self.font_body, height=35, width=140, corner_radius=18)
        self.open_dir_btn.pack()

        # --- 中部：统计面板 ---
        self.stats_frame = ctk.CTkFrame(self.main_frame, height=80, fg_color=("gray85", "gray17"))
        self.stats_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        
        self.stats_labels = {}
        stats_keys = ["总动态", "好友数", "说说", "转发", "留言", "其他"]
        for idx, key in enumerate(stats_keys):
            frame = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
            frame.pack(side="left", expand=True, fill="y", padx=5, pady=10)
            
            ctk.CTkLabel(frame, text=key, font=self.font_small, text_color="gray60").pack()
            val_label = ctk.CTkLabel(frame, text="-", font=("Microsoft YaHei UI", 18, "bold"), text_color="#3B8ED0")
            val_label.pack()
            self.stats_labels[key] = val_label

        # --- 底部：使用Tabview分隔动态展示和日志 ---
        self.bottom_tabview = ctk.CTkTabview(self.main_frame, corner_radius=10)
        self.bottom_tabview.grid(row=2, column=0, sticky="nsew")
        
        # 添加两个标签页
        self.tab_moments = self.bottom_tabview.add("动态列表")
        self.tab_logs = self.bottom_tabview.add("运行日志")
        
        # === 动态列表标签页 ===
        self.tab_moments.grid_rowconfigure(0, weight=1)
        self.tab_moments.grid_columnconfigure(0, weight=1)
        
        self.moments_scrollable = ctk.CTkScrollableFrame(self.tab_moments, fg_color="transparent")
        self.moments_scrollable.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.moments_scrollable.grid_columnconfigure(0, weight=1)
        
        # 占位提示
        self.moments_placeholder = ctk.CTkLabel(
            self.moments_scrollable, 
            text="暂无动态数据\n点击「开始获取」抓取QQ空间动态", 
            font=self.font_body, 
            text_color="gray50"
        )
        self.moments_placeholder.grid(row=0, column=0, pady=50)
        
        # === 日志标签页 ===
        self.tab_logs.grid_rowconfigure(0, weight=1)
        self.tab_logs.grid_columnconfigure(0, weight=1)

        self.log_textbox = ctk.CTkTextbox(self.tab_logs, font=self.font_log, activate_scrollbars=True)
        self.log_textbox.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.log_textbox.configure(state="disabled")

    # --- 逻辑功能 (保持原样) ---

    def _log(self, message):
        """写入日志到队列"""
        if message:
            self.log_queue.put(message)

    def _poll_log_queue(self):
        """定期从队列读取日志并更新到UI"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                # 移除ANSI颜色代码
                message = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", str(message))
                
                self.log_textbox.configure(state="normal")
                self.log_textbox.insert("end", message)
                self.log_textbox.see("end")
                self.log_textbox.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def refresh_users(self):
        """刷新用户列表"""
        self.user_listbox.delete(0, tk.END)
        if not os.path.exists(self.config.user_path):
            return
        files = sorted(os.listdir(self.config.user_path))
        for file_name in files:
            self.user_listbox.insert(tk.END, file_name)

    def _on_fetch_mode_change(self, choice):
        """切换获取模式"""
        if "全部" in choice:
            self.fetch_mode_var.set("full")
            self._log("切换为: 全部动态(含已删除互动消息)\n")
        else:
            self.fetch_mode_var.set("visible_only")
            self._log("切换为: 仅可见动态\n")

    def _on_user_select(self, event):
        """选择用户事件"""
        selection = self.user_listbox.curselection()
        if not selection:
            return
        file_name = self.user_listbox.get(selection[0])
        self.config.set_selected_user_file(file_name)
        self.config.set_force_relogin(False)
        self._reset_request_session()
        
        self.status_label.configure(text=f"已选择用户: {file_name}")
        self.account_info_label.configure(text=f"准备就绪 (点击开始获取)")
        self.qr_label.configure(image=self.empty_qr_image, text="无需扫码")
        self.qr_image = None
        self._log(f"切换用户: {file_name}\n")

    def force_relogin(self):
        """强制重登录/新建任务"""
        self.config.set_selected_user_file(None)
        self.config.set_force_relogin(True)
        self._reset_request_session()
        
        self.qr_label.configure(image=self.empty_qr_image, text="正在生成二维码...")
        self.qr_image = None
        self.status_label.configure(text="请扫码登录")
        self.account_info_label.configure(text="等待用户扫码...")
        self.user_listbox.selection_clear(0, tk.END)
        
        self._log("开始获取二维码...\n")
        self.start_login_flow(force_new=True)

    def start_login_flow(self, force_new=False):
        if not force_new and self.login_thread and self.login_thread.is_alive():
            return
        self._log("启动二维码登录线程...\n")
        try:
            import util.LoginUtil as LoginUtil
            self.login_session_id = LoginUtil.new_login_session()
        except Exception:
            self.login_session_id = None
        self.login_thread = threading.Thread(target=self._login_flow, args=(self.login_session_id,), daemon=True)
        self.login_thread.start()

    def _login_flow(self, session_id):
        import util.LoginUtil as LoginUtil
        stdout_backup = sys.stdout
        stderr_backup = sys.stderr
        sys.stdout = QueueWriter(self.log_queue)
        sys.stderr = QueueWriter(self.log_queue)
        try:
            cookies = LoginUtil.cookie(force_relogin=True, session_id=session_id)
            if cookies and cookies.get("uin"):
                if session_id == self.login_session_id:
                    self.after(0, self._on_login_success, cookies.get("uin"))
            else:
                if session_id == self.login_session_id:
                    self.after(0, lambda: self.status_label.configure(text="登录失败"))
                    self.log_queue.put("二维码登录失败，未获取到有效 cookies\n")
        except Exception as exc:
            if session_id == self.login_session_id:
                self.log_queue.put(f"\n登录异常: {exc}\n")
        finally:
            sys.stdout = stdout_backup
            sys.stderr = stderr_backup

    def _on_login_success(self, uin):
        self.config.set_force_relogin(False)
        self.config.set_selected_user_file(uin)
        self.refresh_users()
        self.status_label.configure(text="登录成功")
        self.account_info_label.configure(text=f"已保存用户: {uin}")
        self.qr_label.configure(image=self.empty_qr_image, text="✔")
        self.qr_image = None
        self._log(f"登录成功: {uin}\n")

    def debug_qr(self):
        try:
            import util.LoginUtil as LoginUtil

            self._log("开始二维码接口诊断...\n")
            result = LoginUtil.debug_qr_endpoints()
            for line in result:
                self._log(line + "\n")
            self._log("诊断结束\n")
        except Exception as exc:
            self._log(f"诊断异常: {exc}\n")

    def _poll_qr_image(self):
        """定期检查二维码图片更新"""
        if os.path.exists(self.qr_path):
            try:
                mtime = os.path.getmtime(self.qr_path)
                if self.last_qr_mtime is None or mtime != self.last_qr_mtime:
                    self.last_qr_mtime = mtime
                    
                    # 使用 CTkImage
                    with Image.open(self.qr_path) as img:
                        pil_image = img.copy()
                    self.qr_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(160, 160))
                    
                    self.qr_label.configure(image=self.qr_image, text="")
                    self._log(f"二维码已更新\n")
            except Exception as exc:
                self._log(f"二维码加载失败: {exc}\n")
        self.after(1000, self._poll_qr_image)

    def start_fetch(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "任务正在运行中")
            return
        if self.login_thread and self.login_thread.is_alive():
            messagebox.showinfo("提示", "请先完成扫码登录")
            return
        
        # 自动重登录检查
        if self.config.force_relogin or not self.config.selected_user_file:
            self.force_relogin()
            return

        self._log("启动任务...\n")
        self.status_label.configure(text="正在抓取数据...")
        self.progress_label.configure(text="初始化中...")
        self.progress_bar.set(0)
        self.start_btn.configure(state="disabled")
        
        self.worker_thread = threading.Thread(target=self._run_main_task, daemon=True)
        self.worker_thread.start()

    def _run_main_task(self):
        self.log_queue.put("[worker] 工作线程已启动\n")
        
        try:
            import main
            from util import GetAllMomentsUtil
            from util import RequestUtil
            self.log_queue.put("[worker] 模块导入成功\n")
        except Exception as e:
            self.log_queue.put(f"[worker] 模块导入失败: {e}\n")
            self.after(0, lambda: self.start_btn.configure(state="normal"))
            return

        def progress_callback(current, total, message):
            if total > 0:
                percent = current / total
                self.after(0, lambda: self.progress_bar.set(percent))
                self.after(0, lambda: self.progress_label.configure(text=f"{message} ({int(percent*100)}%)"))

        GetAllMomentsUtil.set_progress_callback(progress_callback)

        stdout_backup = sys.stdout
        stderr_backup = sys.stderr
        sys.stdout = QueueWriter(self.log_queue)
        sys.stderr = QueueWriter(self.log_queue)
        result = None
        try:
            # 根据下拉菜单的显示文本判断模式
            menu_value = self.fetch_mode_menu.get()
            print(f"=" * 60)
            print(f"下拉菜单值: {menu_value}")
            if "全部" in menu_value:
                fetch_mode = "full"
                print("模式设置为: full (获取全部动态，包含已删除)")
            else:
                fetch_mode = "visible_only"
                print("模式设置为: visible_only (仅获取未删除动态)")
            print(f"=" * 60)
            self.log_queue.put(f"[worker] 开始执行核心逻辑... (模式: {fetch_mode})\n")
            result = main.run_main(return_data=True, fetch_mode=fetch_mode)
            self.log_queue.put("\n任务结束\n")
        except Exception as exc:
            import traceback
            self.log_queue.put(f"\n运行异常: {exc}\n")
            self.log_queue.put(traceback.format_exc() + "\n")
        finally:
            sys.stdout = stdout_backup
            sys.stderr = stderr_backup
            self.after(0, lambda: self.start_btn.configure(state="normal"))
        
        if result:
            self.after(0, self._on_fetch_done, result)
        else:
            self.after(0, lambda: self.status_label.configure(text="获取失败"))

    def _on_fetch_done(self, result):
        self.status_label.configure(text="任务完成")
        self.progress_label.configure(text="100%")
        self.progress_bar.set(1)
        self._update_info(result)
        self._add_history_run(result)
        # 显示动态列表
        self._display_moments(result.get("texts", []))

    def _update_info(self, result):
        uin = result.get("uin") or "-"
        nickname = result.get("nickname") or "-"
        counts = result.get("counts") or {}
        
        self.account_info_label.configure(text=f"{nickname} ({uin})")
        
        self.stats_labels["总动态"].configure(text=str(counts.get('total', 0)))
        self.stats_labels["好友数"].configure(text=str(counts.get('friends', 0)))
        self.stats_labels["说说"].configure(text=str(counts.get('shuoshuo', 0)))
        self.stats_labels["转发"].configure(text=str(counts.get('forward', 0)))
        self.stats_labels["留言"].configure(text=str(counts.get('leave', 0)))
        self.stats_labels["其他"].configure(text=str(counts.get('other', 0)))

    def _display_moments(self, texts):
        """在动态列表中显示获取到的动态"""
        # 清除现有内容
        for widget in self.moments_scrollable.winfo_children():
            widget.destroy()
        
        if not texts or len(texts) == 0:
            self.moments_placeholder = ctk.CTkLabel(
                self.moments_scrollable, 
                text="暂无动态数据", 
                font=self.font_body, 
                text_color="gray50"
            )
            self.moments_placeholder.grid(row=0, column=0, pady=50)
            return
        
        self.current_texts = texts
        self._log(f"正在渲染 {len(texts)} 条动态（全部显示）...\n")
        
        # 切换到动态列表标签页
        self.bottom_tabview.set("动态列表")
        
        # 存储图片引用，防止被垃圾回收
        self.moment_images = []
        
        # 显示全部动态，使用分批渲染避免卡顿
        self._render_batch_index = 0
        self._render_batch_size = 50  # 每批渲染50条
        self._render_texts = texts
        self._render_next_batch()
    
    def _render_next_batch(self):
        """分批渲染动态，避免界面卡顿"""
        start_idx = self._render_batch_index
        end_idx = min(start_idx + self._render_batch_size, len(self._render_texts))
        
        for idx in range(start_idx, end_idx):
            item = self._render_texts[idx]
            try:
                time_str = item[0] if len(item) > 0 else ""
                content = item[1] if len(item) > 1 else ""
                img_urls_str = item[2] if len(item) > 2 else ""
                
                # 创建动态卡片
                card = ctk.CTkFrame(self.moments_scrollable, fg_color=("gray85", "gray20"), corner_radius=10)
                card.grid(row=idx, column=0, sticky="ew", padx=5, pady=5)
                card.grid_columnconfigure(1, weight=1)
                
                # 序号
                num_label = ctk.CTkLabel(card, text=f"#{idx+1}", font=self.font_small, text_color="gray50", width=40)
                num_label.grid(row=0, column=0, rowspan=3, padx=(10, 5), pady=10)
                
                # 时间
                time_label = ctk.CTkLabel(card, text=time_str, font=self.font_small, text_color="#3B8ED0", anchor="w")
                time_label.grid(row=0, column=1, sticky="w", padx=5, pady=(10, 2))
                
                # 内容 (截断过长文本)
                display_content = content[:200] + "..." if len(content) > 200 else content
                content_label = ctk.CTkLabel(card, text=display_content, font=self.font_body, anchor="w", justify="left", wraplength=550)
                content_label.grid(row=1, column=1, sticky="w", padx=5, pady=(2, 5))
                
                # 图片显示区域
                if img_urls_str and "http" in str(img_urls_str):
                    img_urls = [url.strip() for url in str(img_urls_str).split(",") if url.strip() and "http" in url]
                    if img_urls:
                        img_frame = ctk.CTkFrame(card, fg_color="transparent")
                        img_frame.grid(row=2, column=1, sticky="w", padx=5, pady=(0, 10))
                        
                        # 显示最多4张图片缩略图
                        for img_idx, img_url in enumerate(img_urls[:4]):
                            try:
                                # 异步加载图片
                                self._load_image_async(img_frame, img_url, img_idx, idx)
                            except Exception as e:
                                pass
                        
                        # 如果有更多图片，显示数量
                        if len(img_urls) > 4:
                            more_img = ctk.CTkLabel(img_frame, text=f"+{len(img_urls)-4}", font=self.font_small, text_color="gray60")
                            more_img.grid(row=0, column=4, padx=5)
                    
            except Exception as e:
                self._log(f"渲染第{idx+1}条动态失败: {e}\n")
        
        self._render_batch_index = end_idx
        
        # 如果还有更多，继续渲染下一批
        if end_idx < len(self._render_texts):
            # 更新进度
            progress = int(end_idx / len(self._render_texts) * 100)
            self._log(f"渲染进度: {progress}% ({end_idx}/{len(self._render_texts)})\n")
            # 延迟10ms后渲染下一批，让界面有机会更新
            self.after(10, self._render_next_batch)
        else:
            self._log(f"动态渲染完成，共 {len(self._render_texts)} 条\n")

    def _load_image_async(self, parent_frame, img_url, img_idx, card_idx):
        """异步加载图片缩略图"""
        def load():
            try:
                import requests
                import io
                
                # 使用缩略图URL（如果可用）
                thumb_url = img_url
                if "/s&" in img_url or "!/s/" in img_url:
                    pass  # 已经是缩略图
                elif "/m&" in img_url:
                    thumb_url = img_url.replace("/m&", "/s&")
                elif "!/m/" in img_url:
                    thumb_url = img_url.replace("!/m/", "!/s/")
                
                response = requests.get(thumb_url, timeout=5, verify=False)
                if response.status_code == 200:
                    img_data = io.BytesIO(response.content)
                    pil_img = Image.open(img_data)
                    pil_img.thumbnail((60, 60))
                    
                    # 在主线程中更新UI
                    self.after(0, lambda: self._place_image(parent_frame, pil_img, img_idx, card_idx))
            except Exception as e:
                pass  # 图片加载失败，静默忽略
        
        # 在后台线程加载
        threading.Thread(target=load, daemon=True).start()

    def _place_image(self, parent_frame, pil_img, img_idx, card_idx):
        """在UI中放置图片"""
        try:
            if not parent_frame.winfo_exists():
                return
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(60, 60))
            self.moment_images.append(ctk_img)  # 保持引用
            img_label = ctk.CTkLabel(parent_frame, image=ctk_img, text="", width=60, height=60)
            img_label.grid(row=0, column=img_idx, padx=2)
        except Exception as e:
            pass

    def _add_history_run(self, result):
        title = datetime.now().strftime("%Y-%m-%d %H:%M")
        run = {
            "title": title,
            "result": result,
        }
        self.history_runs.insert(0, run)
        self.run_listbox.insert(0, title)
        self.run_listbox.selection_clear(0, tk.END)
        self.run_listbox.selection_set(0)

    def _on_run_select(self, event):
        selection = self.run_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if index >= len(self.history_runs):
            return
        run = self.history_runs[index]
        result = run.get("result") or {}
        self._update_info(result)

    def _reset_request_session(self):
        try:
            from util import RequestUtil
            RequestUtil.reset_login()
        except Exception:
            pass

    def _poll_worker_status(self):
        """监控工作线程状态，虽然这里已经在线程结束时回调了，保留作为保险"""
        if self.worker_thread and not self.worker_thread.is_alive():
            self.worker_thread = None
        self.after(1000, self._poll_worker_status)

    def open_result_dir(self):
        try:
            result_path = os.path.abspath(self.config.result_path)
            os.makedirs(result_path, exist_ok=True)
            os.startfile(result_path)
        except Exception as exc:
            messagebox.showerror("错误", f"打开目录失败: {exc}")

if __name__ == "__main__":
    app = QzoneGuiApp()
    app.mainloop()
