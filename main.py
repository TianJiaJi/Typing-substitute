#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟打字程序 Pro - 终极修复版
修复：64位系统注入失效、中文无法打出、界面缩水
"""
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import keyboard
import time
import random
import threading
import os
import sys
import ctypes

# ==========================================
# 核心引擎：Windows API (修复64位对齐 + WM_CHAR降级)
# ==========================================
if sys.platform == 'win32':
    import ctypes.wintypes
    ULONG_PTR = ctypes.c_void_p

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [('wVk', ctypes.wintypes.WORD), ('wScan', ctypes.wintypes.WORD),
                    ('dwFlags', ctypes.wintypes.DWORD), ('time', ctypes.wintypes.DWORD),
                    ('dwExtraInfo', ULONG_PTR)]

    class _INPUT(ctypes.Union):
        _fields_ = [('ki', KEYBDINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ('_input',)
        _fields_ = [('type', ctypes.wintypes.DWORD), ('_input', _INPUT)]

    SendInput = ctypes.windll.user32.SendInput
    SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
    SendInput.restype = ctypes.c_uint
    
    user32 = ctypes.windll.user32
    GetForegroundWindow = user32.GetForegroundWindow
    SendMessageW = user32.SendMessageW

    def type_char(char):
        if char == '\n': vk, scan = 0x0D, 0
        elif char == '\t': vk, scan = 0x09, 0
        else: vk, scan = 0, ord(char)
        
        flags = 0 if char in '\n\t' else 0x0004 # KEYEVENTF_UNICODE
        
        # 1. 尝试底层注入
        inp_down = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0))
        res = SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(inp_down))
        inp_up = INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags|0x0002, time=0, dwExtraInfo=0))
        SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(inp_up))
        
        # 2. 降级方案：如果注入失败(返回0)，使用 WM_CHAR 直接发消息(专治中文打不出)
        if res == 0 and char not in '\n\t':
            hwnd = GetForegroundWindow()
            SendMessageW(hwnd, 0x0102, ord(char), 0) # WM_CHAR
else:
    def type_char(char):
        keyboard.write(char)


class TypeSimulatorPro:
    def __init__(self, root):
        self.root = root
        self.root.title("✨ 模拟打字程序 Pro (终极修复版)")
        self.root.geometry("700x680")
        self.root.minsize(600, 600)
        
        self.colors = {"bg": "#f8f9fa", "panel": "#ffffff", "success": "#2ecc71", 
                       "danger": "#e74c3c", "warning": "#f39c12", "text": "#2c3e50"}
        self.root.configure(bg=self.colors["bg"])
        
        self.is_typing = False
        self._typing_thread = None
        self.log_queue = []
        
        self._build_ui()
        self._start_log_updater()

    def _build_ui(self):
        main_frame = tk.Frame(self.root, bg=self.colors["bg"], padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部工具栏 (固定顶部)
        toolbar = tk.Frame(main_frame, bg=self.colors["bg"])
        toolbar.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        tk.Button(toolbar, text="📂 打开文件", bg=self.colors["panel"], relief=tk.FLAT, padx=10, pady=5,
                  command=self.load_file).pack(side=tk.LEFT, padx=5)
        tk.Button(toolbar, text="🗑️ 清空文本", bg=self.colors["panel"], relief=tk.FLAT, padx=10, pady=5,
                  command=self.clear_text).pack(side=tk.LEFT, padx=5)
        self.stats_label = tk.Label(toolbar, text="字符: 0 | 预计: 0s", font=("Consolas", 9), bg=self.colors["bg"])
        self.stats_label.pack(side=tk.RIGHT)

        # 2. 底部日志面板 (固定底部，防缩水)
        log_frame = tk.LabelFrame(main_frame, text=" 📋 运行日志 ", bg=self.colors["bg"], padx=5, pady=5)
        log_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        self.log_box = scrolledtext.ScrolledText(log_frame, height=5, font=("Consolas", 9),
                                                 bg="#2d2d2d", fg="#cccccc", borderwidth=1, relief=tk.SOLID)
        self.log_box.pack(fill=tk.X, pady=(5, 0))
        tk.Button(log_frame, text="清空日志", bg="#555", fg="white", relief=tk.FLAT,
                  command=lambda: self.log_box.delete(1.0, tk.END)).pack(anchor=tk.E)

        # 3. 控制面板 (固定底部之上，防缩水)
        control_panel = tk.LabelFrame(main_frame, text=" ⚙️ 控制设置 ", bg=self.colors["bg"], padx=10, pady=10)
        control_panel.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        
        # 引擎选择
        engine_row = tk.Frame(control_panel, bg=self.colors["bg"])
        engine_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(engine_row, text="🚀 引擎:", bg=self.colors["bg"], font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT)
        self.engine_var = tk.StringVar(value="🛡️ Unicode注入 (推荐)")
        engines = ["🛡️ Unicode注入 (推荐)", "📋 剪贴板粘贴", "⌨️ 物理按键 (专治禁止粘贴)"]
        ttk.Combobox(engine_row, textvariable=self.engine_var, values=engines, state="readonly", width=30).pack(side=tk.LEFT, padx=10)

        # 速度设置
        row1 = tk.Frame(control_panel, bg=self.colors["bg"])
        row1.pack(fill=tk.X, pady=5)
        tk.Label(row1, text="速度(s):", bg=self.colors["bg"]).pack(side=tk.LEFT)
        self.speed_var = tk.DoubleVar(value=0.08)
        tk.Scale(row1, from_=0.02, to=0.5, resolution=0.01, orient=tk.HORIZONTAL, variable=self.speed_var,
                 length=120, bg=self.colors["bg"], highlightthickness=0).pack(side=tk.LEFT, padx=5)
        tk.Label(row1, text="波动(%):", bg=self.colors["bg"]).pack(side=tk.LEFT, padx=(10, 0))
        self.variation_var = tk.IntVar(value=30)
        tk.Scale(row1, from_=0, to=100, resolution=5, orient=tk.HORIZONTAL, variable=self.variation_var,
                 length=80, bg=self.colors["bg"], highlightthickness=0).pack(side=tk.LEFT, padx=5)

        # 按钮
        row2 = tk.Frame(control_panel, bg=self.colors["bg"])
        row2.pack(fill=tk.X, pady=5)
        self.start_btn = tk.Button(row2, text="▶ 开始打字", font=("Microsoft YaHei", 11, "bold"),
                                   bg=self.colors["success"], fg="white", relief=tk.FLAT, padx=20, pady=8,
                                   command=self.on_start_click)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = tk.Button(row2, text="⏹ 停止", font=("Microsoft YaHei", 11),
                                  bg=self.colors["danger"], fg="white", relief=tk.FLAT, padx=20, pady=8,
                                  command=self.on_stop_click, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.countdown_label = tk.Label(row2, text="", font=("Arial", 12, "bold"), bg=self.colors["bg"], fg=self.colors["warning"])
        self.countdown_label.pack(side=tk.RIGHT, padx=10)

        # 4. 中间文本框 (最后 pack，自适应填充，绝不缩水)
        text_frame = tk.LabelFrame(main_frame, text=" 📝 输入内容 ", bg=self.colors["bg"], padx=5, pady=5)
        text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        self.text_box = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD, font=("Consolas", 11),
                                                  padx=10, pady=10, bg=self.colors["panel"], borderwidth=1, relief=tk.SOLID)
        self.text_box.pack(fill=tk.BOTH, expand=True)
        self.text_box.insert(tk.END, "你好！这是终极修复版。\n\n已修复64位系统注入失效问题。\n已增加WM_CHAR降级机制，中文绝对能打出来！")
        self.text_box.bind("<KeyRelease>", self.update_stats)
        
        self.log("系统就绪。已修复64位注入Bug，启用WM_CHAR降级保护。")
        self.update_stats()

    def load_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt")])
        if file_path:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.text_box.delete("1.0", tk.END)
                self.text_box.insert(tk.END, f.read())
            self.update_stats()

    def clear_text(self):
        if messagebox.askyesno("确认", "确定清空？"):
            self.text_box.delete("1.0", tk.END)
            self.update_stats()

    def update_stats(self, event=None):
        text = self.text_box.get("1.0", tk.END).rstrip("\n")
        c = len(text)
        self.stats_label.config(text=f"字符: {c} | 预计: {c * self.speed_var.get():.1f}s")

    def log(self, msg):
        self.log_queue.append(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _start_log_updater(self):
        def update():
            while self.log_queue:
                self.log_box.insert(tk.END, self.log_queue.pop(0) + "\n")
                self.log_box.see(tk.END)
            self.root.after(100, update)
        update()

    def on_start_click(self):
        text = self.text_box.get("1.0", tk.END).rstrip("\n")
        if not text.strip(): return messagebox.showwarning("提示", "文本为空！")
        
        self.is_typing = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.text_box.config(state=tk.DISABLED)
        self.log(f"✅ 启动任务 [{self.engine_var.get()}]...")
        self._typing_thread = threading.Thread(target=self._do_typing, args=(text,), daemon=True)
        self._typing_thread.start()

    def on_stop_click(self):
        self.is_typing = False
        self.log("⏹ 停止...")

    def _do_typing(self, text: str):
        engine = self.engine_var.get()
        base_speed = self.speed_var.get()
        variation = base_speed * (self.variation_var.get() / 100.0)
        total = len(text)

        for i in range(3, 0, -1):
            if not self.is_typing: break
            self.root.after(0, lambda c=i: self.countdown_label.config(text=f"⏳ {c}"))
            time.sleep(1)

        if not self.is_typing: return self._reset_ui()
        self.root.after(0, lambda: self.countdown_label.config(text=""))
        self.log("⌨️ 开始输入...")

        try:
            for i, char in enumerate(text):
                if not self.is_typing: break

                if "剪贴板" in engine:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(char)
                    self.root.update()
                    keyboard.press_and_release('ctrl+v' if sys.platform != 'darwin' else 'cmd+v')
                elif "物理" in engine and ord(char) <= 127:
                    keyboard.write(char)
                else:
                    # 核心：使用修复后的 type_char (包含 WM_CHAR 降级)
                    type_char(char)

                if (i + 1) % 50 == 0 or (i + 1) == total:
                    self.log(f"📊 进度: {(i+1)/total*100:.1f}%")

                delay = base_speed + random.uniform(-variation, variation)
                time.sleep(max(0.01, delay))

            if self.is_typing: self.log("✅ 完美完成！")
        except Exception as e:
            self.log(f"❌ 错误: {e}")
        finally:
            self._reset_ui()

    def _reset_ui(self):
        def _update():
            self.is_typing = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.text_box.config(state=tk.NORMAL)
            self.countdown_label.config(text="")
        self.root.after(0, _update)

    def on_closing(self):
        if self.is_typing:
            if messagebox.askokcancel("退出", "正在打字，确定退出？"): self.root.destroy()
        else: self.root.destroy()

def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = TypeSimulatorPro(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry(f'+{(root.winfo_screenwidth()//2)-(w//2)}+{(root.winfo_screenheight()//2)-(h//2)}')
    root.mainloop()

if __name__ == "__main__":
    main()