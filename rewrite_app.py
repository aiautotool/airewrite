import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import time
import os
import sys
import rewrite
import re
import json
from datetime import datetime
from urllib.parse import urlparse
import subprocess
import uuid
import random
import customtkinter as ctk
import concurrent.futures
import requests

# Support for Scrapy when running as a frozen bundle
if len(sys.argv) > 2 and sys.argv[1] == '-m' and sys.argv[2] == 'scrapy':
    try:
        from scrapy.cmdline import execute
        sys.argv = sys.argv[2:]
        execute()
    except Exception as e:
        print(f"Scrapy execution error: {e}")
    sys.exit(0)


from ai_agent import AIAgent
from sheet_manager import get_sheet_manager
from wp_api_manager import get_wp_manager
from account_manager import get_account_manager, AccountManager

# CustomTkinter Setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class GradientFrame(tk.Canvas):
    def __init__(self, parent, color1, color2, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self.color1 = color1
        self.color2 = color2
        self.bind("<Configure>", self._draw_gradient)

    def _draw_gradient(self, event=None):
        self.delete("gradient")
        width = self.winfo_width()
        height = self.winfo_height()
        limit = height
        (r1,g1,b1) = self.winfo_rgb(self.color1)
        (r2,g2,b2) = self.winfo_rgb(self.color2)
        r_ratio = float(r2-r1) / limit
        g_ratio = float(g2-g1) / limit
        b_ratio = float(b2-b1) / limit

        for i in range(limit):
            nr = int(r1 + (r_ratio * i))
            ng = int(g1 + (g_ratio * i))
            nb = int(b1 + (b_ratio * i))
            color = "#%4.4x%4.4x%4.4x" % (nr,ng,nb)
            self.create_line(0,i,width,i, tags=("gradient",), fill=color)
        self.tag_lower("gradient")

# Thread-Aware Redirector
class ThreadAwareRedirector(object):
    def __init__(self):
        self.widgets = {} # Maps thread_id -> widget
        self.tags = {}    # Maps thread_id -> tag
        self.lock = threading.Lock()

    def register(self, thread_id, widget, tag="stdout"):
        with self.lock:
            self.widgets[thread_id] = widget
            self.tags[thread_id] = tag

    def unregister(self, thread_id):
        with self.lock:
            if thread_id in self.widgets:
                del self.widgets[thread_id]
            if thread_id in self.tags:
                del self.tags[thread_id]

    def write(self, string):
        # Identify current thread
        current_id = threading.get_ident()
        with self.lock:
            widget = self.widgets.get(current_id)
            tag = self.tags.get(current_id, "stdout")
        
        if widget and widget.winfo_exists():
            try:
                widget.configure(state="normal")
                widget.insert("end", string, (tag,))
                widget.see("end")
                widget.configure(state="disabled")
            except:
                pass
        else:
            # Fallback to true stdout if no widget registered for this thread
            sys.__stdout__.write(string)

    def flush(self):
        sys.__stdout__.flush()

# Global Redirector Instance
std_out_router = ThreadAwareRedirector()
sys.stdout = std_out_router

class CrawlerTab(ctk.CTkFrame):
    """Tab xử lý crawler cho một domain cụ thể"""
    
    def __init__(self, parent, app, initial_url="", config=None):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.app = app
        self.url_var = tk.StringVar(value=initial_url)
        self.status_var = tk.StringVar(value="Ready")
        self.counter_var = tk.StringVar(value="0 processed")
        self.include_var = tk.StringVar()
        self.exclude_var = tk.StringVar()
        self.system_prompt_var = tk.StringVar()
        self.dest_mode_var = tk.IntVar(value=0) # 0: Sheet, 1: WP API
        self.use_scrapy_var = tk.BooleanVar(value=False)
        self.title_selector_var = tk.StringVar()
        self.content_selector_var = tk.StringVar()
        self.pagination_selector_var = tk.StringVar()
        self.article_selector_var = tk.StringVar()
        self.tab_name_var = tk.StringVar(value="New Crawler")
        self.model_var = tk.StringVar(value="gemini-2.5-flash")

        
        self.wp_manager = get_wp_manager()
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.is_paused = False
        self.stop_requested = False
        self.domain = self.get_domain(initial_url) if initial_url else ""
        self.file_lock = threading.Lock()
        
        # Tab Name
        default_name = config.get("tab_name", "") if config else ""
        if not default_name: default_name = self.domain or "New Tab"
        self.tab_name_var = tk.StringVar(value=default_name)
        
        # Files (initially None)
        self.log_file = None
        self.progress_file = None
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        
        # Managers
        self.sheet_manager = get_sheet_manager()
        self.setup_ui()
        
        if config:
            self.load_from_config(config)
        
        if initial_url:
            self.update_filenames()

    def setup_ui(self):
        # Top Frame: Controls
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=10, pady=(5, 10))

        url_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        url_frame.pack(fill="x", side="top", pady=(0, 10))

        # Name Entry
        ctk.CTkLabel(url_frame, text="Tab Name:").pack(side="left", padx=5)
        self.name_entry = ctk.CTkEntry(url_frame, textvariable=self.tab_name_var, width=120)
        self.name_entry.pack(side="left", padx=5)
        # Auto-save name on change or loose focus? 
        # For simplicity, bind FocusOut to update sidebar
        self.name_entry.bind("<FocusOut>", lambda e: self.app.update_sidebar_crawlers())
        self.name_entry.bind("<Return>", lambda e: self.app.update_sidebar_crawlers())
        
        ctk.CTkLabel(url_frame, text="Source URL:").pack(side="left", padx=5)
        self.url_entry = ctk.CTkEntry(url_frame, textvariable=self.url_var, width=60)
        self.url_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Scrapy Toggle + Config
        ctk.CTkCheckBox(url_frame, text="Auto Crawl Ref (Scrapy)", variable=self.use_scrapy_var).pack(side="left", padx=5)
        ctk.CTkButton(url_frame, text="⚙️", width=30, command=self.open_scrapy_config, fg_color="gray70", text_color="black").pack(side="left", padx=2)


        
        # Target Selection
        sheet_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        sheet_frame.pack(fill="x", side="top", pady=(0, 10))
        ctk.CTkLabel(sheet_frame, text="Target:").pack(side="left", padx=5)
        
        ctk.CTkRadioButton(sheet_frame, text="Sheet", variable=self.dest_mode_var, value=0, 
                       command=self.toggle_dest_mode).pack(side="left")
        ctk.CTkRadioButton(sheet_frame, text="WP API", variable=self.dest_mode_var, value=1, 
                       command=self.toggle_dest_mode).pack(side="left", padx=(0, 10))

        self.sheet_combo = ctk.CTkComboBox(sheet_frame, state="readonly", width=180)
        self.sheet_combo.pack(side="left", padx=5)
        
        self.wp_combo = ctk.CTkComboBox(sheet_frame, state="readonly", width=150, command=self.on_wp_site_selected)
        self.cat_label = ctk.CTkLabel(sheet_frame, text="Cat:")
        self.cat_combo = ctk.CTkComboBox(sheet_frame, state="readonly", width=100)
        
        self.refresh_dest_lists()

        # Filter Frame
        filter_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        filter_frame.pack(fill="x", side="top", pady=(0, 10))
        ctk.CTkLabel(filter_frame, text="Include (,) :").pack(side="left", padx=5)
        ctk.CTkEntry(filter_frame, textvariable=self.include_var, width=150).pack(side="left", padx=5)
        ctk.CTkLabel(filter_frame, text="Exclude (,) :").pack(side="left", padx=10)
        ctk.CTkEntry(filter_frame, textvariable=self.exclude_var, width=150).pack(side="left", padx=5)
        ctk.CTkButton(filter_frame, text="?", command=self.show_filter_help, width=30, fg_color="#607D8B").pack(side="left", padx=10)

        # Thread Control
        thread_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        thread_frame.pack(fill="x", side="top", pady=(0, 10))
        ctk.CTkLabel(thread_frame, text="Threads:").pack(side="left", padx=5)
        self.thread_count_var = tk.IntVar(value=1)
        self.thread_slider = ctk.CTkSlider(thread_frame, from_=1, to=10, number_of_steps=9, variable=self.thread_count_var, width=150)
        self.thread_slider.pack(side="left", padx=5)
        self.thread_label = ctk.CTkLabel(thread_frame, textvariable=self.thread_count_var, width=30)
        self.thread_label.pack(side="left", padx=5)

        # Buttons
        btn_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        btn_frame.pack(fill="x", side="top")
        self.btn_run = ctk.CTkButton(btn_frame, text="▶ Run", command=self.start_process, fg_color="#4CAF50", width=80)
        self.btn_run.pack(side="left", padx=5)
        self.btn_pause = ctk.CTkButton(btn_frame, text="⏸ Pause", command=self.toggle_pause, state="disabled", fg_color="#FFC107", width=80)
        self.btn_pause.pack(side="left", padx=5)
        self.btn_stop = ctk.CTkButton(btn_frame, text="⏹ Stop", command=self.stop_process, state="disabled", fg_color="#F44336", width=80)
        self.btn_stop.pack(side="left", padx=5)
        self.btn_reset = ctk.CTkButton(btn_frame, text="↺ Reset", command=self.reset_progress, fg_color="#607D8B")
        self.btn_reset.pack(side="left", padx=15)
        self.btn_prompt = ctk.CTkButton(btn_frame, text="📝 Prompt", command=self.open_prompt_editor, width=100)
        self.btn_prompt.pack(side="left", padx=5)

        # Model Selection
        model_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        model_frame.pack(fill="x", side="top", pady=(10, 0))
        ctk.CTkLabel(model_frame, text="AI Model:").pack(side="left", padx=5)
        self.model_combo = ctk.CTkComboBox(model_frame, variable=self.model_var, 
                                           values=["gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-exp-1206", "claude-sonnet-3.5", "gpt-4o"])
        self.model_combo.pack(side="left", padx=5)

        # Console
        self.console = ctk.CTkTextbox(self, state="disabled", wrap="word")
        self.console.pack(fill="both", expand=True, padx=10, pady=5)
        self.console.tag_config("stdout", foreground="#cccccc")
        self.console.tag_config("info", foreground="#61dafb")
        self.console.tag_config("success", foreground="#98c379")
        self.console.tag_config("error", foreground="#e06c75")

        # Bottom Status
        status_bar = ctk.CTkFrame(self, height=30)
        status_bar.pack(fill="x", side="bottom")
        ctk.CTkLabel(status_bar, textvariable=self.status_var, font=("Arial", 10)).pack(side="left", padx=10)
        ctk.CTkLabel(status_bar, textvariable=self.counter_var, font=("Arial", 10)).pack(side="left", padx=20)
        self.progress_bar = ctk.CTkProgressBar(status_bar, mode="indeterminate")
        self.progress_bar.pack(side="right", padx=10, fill="x", expand=True)

    def get_domain(self, url):
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "") or "unknown"
            return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', domain)
        except: return "unknown"

    def update_filenames(self):
        self.domain = self.get_domain(self.url_var.get().strip())
        self.log_file = os.path.join(self.app.data_dir, f"history_{self.domain}.log")
        self.progress_file = os.path.join(self.app.data_dir, f"progress_{self.domain}.json")

    def load_from_config(self, config):
        self.url_var.set(config.get("url", ""))
        self.include_var.set(config.get("include", ""))
        self.exclude_var.set(config.get("exclude", ""))
        self.system_prompt_var.set(config.get("prompt", ""))
        self.dest_mode_var.set(config.get("dest_mode", 0))
        self.sheet_combo.set(config.get("selected_sheet", ""))
        self.wp_combo.set(config.get("selected_wp", ""))
        self.cat_combo.set(config.get("selected_cat", ""))
        self.use_scrapy_var.set(config.get("use_scrapy", False))
        self.title_selector_var.set(config.get("title_selector", ""))
        self.content_selector_var.set(config.get("content_selector", ""))
        self.pagination_selector_var.set(config.get("pagination_selector", ""))
        self.article_selector_var.set(config.get("article_selector", ""))
        self.model_var.set(config.get("model", "gemini-2.5-flash"))
        self.toggle_dest_mode()

    def refresh_dest_lists(self):
        sheets = [s['name'] for s in self.sheet_manager.list_sheets()]
        self.sheet_combo.configure(values=sheets)
        if sheets and not self.sheet_combo.get(): self.sheet_combo.set(sheets[0])
            
        wp_sites = [w['name'] for w in self.wp_manager.list_destinations()]
        self.wp_combo.configure(values=wp_sites)
        if wp_sites and not self.wp_combo.get(): self.wp_combo.set(wp_sites[0])
        self.toggle_dest_mode()

    def toggle_dest_mode(self):
        if self.dest_mode_var.get() == 0:
            self.wp_combo.pack_forget(); self.cat_label.pack_forget(); self.cat_combo.pack_forget()
            self.sheet_combo.pack(side="left", padx=5)
        else:
            self.sheet_combo.pack_forget()
            self.wp_combo.pack(side="left", padx=5)
            self.cat_label.pack(side="left", padx=5); self.cat_combo.pack(side="left", padx=5)
            self.on_wp_site_selected(self.wp_combo.get())

    def on_wp_site_selected(self, selected_name):
        if not selected_name: return
        def fetch():
            sites = self.wp_manager.list_destinations()
            conf = next((w for w in sites if w['name'] == selected_name), None)
            if conf:
                cats = self.wp_manager.get_categories(conf)
                self.category_map = {c['name']: c['id'] for c in cats}
                cat_names = sorted(list(self.category_map.keys()))
                self.after(0, lambda: self.cat_combo.configure(values=cat_names))
        threading.Thread(target=fetch, daemon=True).start()

    def log(self, message, tag="info"):
        # Local Console
        if self.console.winfo_exists():
            self.console.configure(state="normal")
            ts = datetime.now().strftime("[%H:%M:%S] ")
            self.console.insert("end", ts + message + "\n", (tag,))
            self.console.see("end")
            self.console.configure(state="disabled")

        # Global Dashboard Feed
        if hasattr(self.app, 'dashboard_tab') and self.app.dashboard_tab:
            self.app.dashboard_tab.add_log(f"{self.domain}: {message}", tag)

    def show_filter_help(self):
        messagebox.showinfo("Filter Help", "Enter keywords separated by commas.\nInclude: Only process items containing these.\nExclude: Skip items containing these.")

    def view_history(self):
        self.update_filenames()
        if os.path.exists(self.log_file):
            if sys.platform == "darwin": subprocess.call(["open", self.log_file])
            else: os.startfile(self.log_file)
        else: messagebox.showinfo("Info", "No history found.")

    def reset_progress(self):
        self.update_filenames()
        if messagebox.askyesno("Confirm", "Reset progress for this domain?"):
            if os.path.exists(self.log_file): os.remove(self.log_file)
            if os.path.exists(self.progress_file): os.remove(self.progress_file)
            self.log("Progress reset.", "success")

    def toggle_pause(self):
        if self.is_paused:
            self.is_paused = False; self.pause_event.set()
            self.btn_pause.configure(text="⏸ Pause"); self.status_var.set("Status: Running")
        else:
            self.is_paused = True; self.pause_event.clear()
            self.btn_pause.configure(text="▶ Resume"); self.status_var.set("Status: Paused")

    def open_prompt_editor(self):
        editor = tk.Toplevel(self)
        editor.title("Edit System Prompt")
        text = scrolledtext.ScrolledText(editor, width=60, height=20)
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", self.system_prompt_var.get() or "Default Prompt")
        def save():
            self.system_prompt_var.set(text.get("1.0", "end-1c").strip())
            editor.destroy()
        ctk.CTkButton(editor, text="Save", command=save).pack(pady=10)

    def start_process(self):
        if self.is_running: return
        url = self.url_var.get().strip()
        if not url: return messagebox.showerror("Error", "URL required")
        
        self.update_filenames()
        self.is_running = True; self.stop_event.clear(); self.pause_event.set()
        self.btn_run.configure(state="disabled"); self.btn_pause.configure(state="normal")
        self.btn_stop.configure(state="normal"); self.progress_bar.start()
        
        # Get Destination Config
        dest = None
        if self.dest_mode_var.get() == 0:
            name = self.sheet_combo.get()
            dest = next((s for s in self.sheet_manager.list_sheets() if s['name'] == name), None)
            if dest: dest = {"type": "sheet", "config": dest}
        else:
            name = self.wp_combo.get()
            dest = next((w for w in self.wp_manager.list_destinations() if w['name'] == name), None)
            if dest:
                cat_id = getattr(self, 'category_map', {}).get(self.cat_combo.get())
                conf = dest.copy(); conf['category_id'] = cat_id
                dest = {"type": "wp", "config": conf}
        
        if not dest: 
            self.process_finished()
            return messagebox.showerror("Error", "Check Target selection")

        # Fork logic: Regular WP API Crawl or Scrapy
        model = self.model_var.get()
        if self.use_scrapy_var.get():
             threading.Thread(target=self.run_scrapy_consumer, args=(url, dest, model), daemon=True).start()
        else:
             threading.Thread(target=self.run_crawler, args=(url, dest, model), daemon=True).start()

    def stop_process(self):
        self.stop_event.set(); self.pause_event.set()
        self.log("Stopping after current item...", "error")
        # If scrapy is running, kill it faster
        if hasattr(self, 'proc') and self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.log("Scrapy process terminated.", "error")
            except: pass

    def process_finished(self):
        self.is_running = False; self.btn_run.configure(state="normal")
        self.btn_pause.configure(state="disabled"); self.btn_stop.configure(state="disabled")
        self.progress_bar.stop(); self.status_var.set("Status: Stopped")

    def open_scrapy_config(self):
        dialog = tk.Toplevel(self)
        dialog.title("Scrapy Configuration")
        dialog.geometry("500x300")
        
        ctk.CTkLabel(dialog, text="Custom CSS/XPath Selectors", font=("Arial", 16, "bold")).pack(pady=10)
        
        def create_input(label, var, placeholder):
            f = ctk.CTkFrame(dialog, fg_color="transparent")
            f.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(f, text=label, width=120, anchor="w").pack(side="left")
            e = ctk.CTkEntry(f, textvariable=var)
            e.pack(side="left", fill="x", expand=True)
            if not var.get(): e.insert(0, ""); e.configure(placeholder_text=placeholder)
            
        create_input("Title Selector (Detail):", self.title_selector_var, "e.g. h1.entry-title")
        create_input("Content Selector (Detail):", self.content_selector_var, "e.g. .entry-content")
        create_input("Article URL Selector (List):", self.article_selector_var, "e.g. .post-title a (href to detail)")
        create_input("Pagination Selector (List):", self.pagination_selector_var, "e.g. .pagination a.next")
        
        ctk.CTkLabel(dialog, text="(Leave empty to use auto-detection via Readability or generic link following)", text_color="gray60", font=("Arial", 10)).pack(pady=5)
        
        def close_and_save():
            self.app.save_state()
            dialog.destroy()
        
        dialog.protocol("WM_DELETE_WINDOW", close_and_save)    
        ctk.CTkButton(dialog, text="Save & Close", command=close_and_save).pack(pady=20)

    def run_scrapy_consumer(self, start_url, dest_config, model="gemini-2.5-flash"):

        std_out_router.register(threading.get_ident(), self.console)
        
        domain = self.get_domain(start_url)
        safe_domain = "".join([c if c.isalnum() or c in ['.','-'] else '_' for c in domain])
        jsonl_file = f"scraped_data_{safe_domain}.jsonl"

        if getattr(sys, 'frozen', False):
            cwd = sys._MEIPASS
        else:
            cwd = os.path.dirname(os.path.abspath(__file__)) # py/
            
        crawler_dir = os.path.join(cwd, "crawler")
        
        if not os.path.exists(crawler_dir):
            self.log(f"Crawler directory not found: {crawler_dir}", "error")
            self.log(f"Looked in: {cwd}", "error")
            self.process_finished()
            return

        jsonl_path = os.path.join(self.app.data_dir, jsonl_file)
        
        self.log(f"Starting Scrapy for {start_url}...", "info")
        self.log(f"Output will be monitored at: {jsonl_path}", "info")
        
        # Determine start line
        start_line = 0
        if os.path.exists(jsonl_path):
             with open(jsonl_path, 'r', encoding='utf-8') as f:
                 start_line = sum(1 for _ in f)
        
        
        # cmd = [sys.executable, "-m", "scrapy", "crawl", "dynamic", "-a", f"url={start_url}"]
        cmd = [sys.executable, "-m", "scrapy", "crawl", "dynamic", "-a", f"url={start_url}", "-a", f"output_file={jsonl_path}"]
        
        # Add selectors if present
        if self.title_selector_var.get().strip():
             cmd.extend(["-a", f"title_selector={self.title_selector_var.get().strip()}"])
        if self.content_selector_var.get().strip():
             cmd.extend(["-a", f"content_selector={self.content_selector_var.get().strip()}"])
        if self.article_selector_var.get().strip():
             cmd.extend(["-a", f"article_selector={self.article_selector_var.get().strip()}"])
        if self.pagination_selector_var.get().strip():
             cmd.extend(["-a", f"pagination_selector={self.pagination_selector_var.get().strip()}"])
        
        self.proc = None

        try:
             # Set PYTHONPATH to parent directory so crawler module can be found
             env = os.environ.copy()
             env['PYTHONPATH'] = cwd
             self.proc = subprocess.Popen(cmd, cwd=crawler_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except Exception as e:
             self.log(f"Failed to start scrapy: {e}", "error")
             self.process_finished()
             return

        processed = rewrite.load_processed_titles(log_file=self.log_file)
        num_threads = self.thread_count_var.get()
        
        def process_post_task(post, processed_set):
            if self.stop_event.is_set(): return
            while self.is_paused and not self.stop_event.is_set(): time.sleep(1)
            if self.stop_event.is_set(): return

            title = re.sub('<[^<]+?>', '', post.get("title", {}).get("rendered", ""))
            with self.file_lock:
                if title in processed_set: return

            self.log(f"Processing: {title}")
            res = rewrite.rewrite_content_with_fallback(title, post.get("content", {}).get("rendered", ""), 
                                                       system_prompt=self.system_prompt_var.get(), model=model)
            
            if res:
                status = rewrite.aiautotool_pingbackstatus(title, res, 1, dest_config=dest_config)
                if status in [200, 201]:
                    with self.file_lock:
                        rewrite.save_processed_title(title, log_file=self.log_file)
                        processed_set.add(title)
                        self.counter_var.set(f"{len(processed_set)} processed")
                        self.log(f"Submitted [{title}]!", "success")
                        self.app.stats['processed'] += 1
                        self.app.dashboard_tab.update_stats()

        try:
            current_file_obj = None
            if os.path.exists(jsonl_path):
                 current_file_obj = open(jsonl_path, 'r', encoding='utf-8')
                 for _ in range(start_line): current_file_obj.readline()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                while not self.stop_event.is_set():
                     if self.is_paused: self.pause_event.wait()
                         
                     if not current_file_obj and os.path.exists(jsonl_path):
                          current_file_obj = open(jsonl_path, 'r', encoding='utf-8')
                     
                     batch = []
                     if current_file_obj:
                         while True:
                             line = current_file_obj.readline()
                             if not line: break
                             try:
                                 data = json.loads(line)
                                 if "title" in data and isinstance(data["title"], str): data["title"] = {"rendered": data["title"]}
                                 if "content" in data and isinstance(data["content"], str): data["content"] = {"rendered": data["content"]}
                                 batch.append(data)
                             except: pass
                             if len(batch) >= num_threads: break
                     
                     if batch:
                         self.log(f"Found {len(batch)} items from Scrapy...", "info")
                         futures = [executor.submit(process_post_task, post, processed) for post in batch]
                         concurrent.futures.wait(futures)
                     else:
                         if self.proc.poll() is not None:
                             self.log("Scrapy finished.", "success")
                             break
                         time.sleep(2)
        except Exception as e:
             self.log(f"Error in Consumer: {e}", "error")
        finally:
             if self.proc and self.proc.poll() is None: self.proc.terminate()
             if current_file_obj: current_file_obj.close()
             
             # Auto cleanup: If finished normally (not stopped) and file exists, delete it
             try:
                 if not self.stop_event.is_set() and os.path.exists(jsonl_path):
                     os.remove(jsonl_path)
                     self.log(f"Cleaned up temporary file: {jsonl_file}", "info")
             except: pass
             
             self.after(0, self.process_finished)


    def run_crawler(self, base_url, dest_config, model="gemini-2.5-flash"):
        std_out_router.register(threading.get_ident(), self.console)
        
        # Helper function for processing a single post
        def process_post_task(post, processed_set):
            if self.stop_event.is_set(): return
            
            # Pause check (busy wait with sleep to allow pausing inside threads)
            while self.is_paused and not self.stop_event.is_set():
                time.sleep(1)
            
            if self.stop_event.is_set(): return

            title = re.sub('<[^<]+?>', '', post.get("title", {}).get("rendered", ""))
            
            with self.file_lock:
                if title in processed_set: return

            self.log(f"Processing: {title}")
            res = rewrite.rewrite_content_with_fallback(title, post.get("content", {}).get("rendered", ""), 
                                                       system_prompt=self.system_prompt_var.get(), model=model)
            
            if res:
                # We reuse the logic but need to be careful about print statements inside rewrite module if they interleave
                # The rewrite module prints to stdout, which we are capturing.
                
                # Critical Section: Writing to external destination
                # Note: aiautotool_pingbackstatus prints log as well.
                status = rewrite.aiautotool_pingbackstatus(title, res, 1, dest_config=dest_config)
                
                if status in [200, 201]:
                    with self.file_lock:
                        rewrite.save_processed_title(title, log_file=self.log_file)
                        processed_set.add(title)
                        self.counter_var.set(f"{len(processed_set)} processed")
                        self.log(f"Submitted [{title}]!", "success")
                        self.app.stats['processed'] += 1
                        self.app.dashboard_tab.update_stats()

        try:
            progress = rewrite.load_progress(progress_file=self.progress_file)
            current_page = progress.get("current_page", 1)
            processed = rewrite.load_processed_titles(log_file=self.log_file)
            
            num_threads = self.thread_count_var.get()
            self.log(f"Starting with {num_threads} threads...", "info")

            # Create ThreadPoolExecutor once and reuse it
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
                while not self.stop_event.is_set():
                    if self.is_paused:
                        self.pause_event.wait()

                    posts = rewrite.fetch_wp_posts(page=current_page, base_url=base_url)
                    if not posts: break
                    
                    # Filter posts that are already processed
                    posts_to_process = [p for p in posts if re.sub('<[^<]+?>', '', p.get("title", {}).get("rendered", "")) not in processed]
                    
                    if not posts_to_process:
                        self.log(f"No new posts on page {current_page}. Moving next.", "info")
                    else:
                        self.log(f"Found {len(posts_to_process)} new posts on page {current_page}. Processing concurrently...", "info")
                        
                        # Submit tasks to the existing executor
                        futures = [executor.submit(process_post_task, post, processed) for post in posts_to_process]
                        
                        # Wait for this batch to complete
                        for future in concurrent.futures.as_completed(futures):
                            if self.stop_event.is_set():
                                break
                            try:
                                future.result()
                            except Exception as e:
                                self.log(f"Thread Error: {e}", "error")

                    if self.stop_event.is_set(): break
                    
                    current_page += 1
                    with self.file_lock:
                        rewrite.save_progress(current_page, progress_file=self.progress_file)
                    
                    # Small delay between pages
                    time.sleep(2)

        except Exception as e: self.log(f"Error: {e}", "error")
        finally: self.after(0, self.process_finished)

class SheetManagerTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.sheet_manager = get_sheet_manager()
        self.selected_id = None
        
        # Keys for required fields
        self.field_keys = ['author_id', 'title', 'slug', 'content', 'publish', 'date_year', 'date_month', 'date_day']
        self.entry_widgets = {} # Map key -> entry widget
        
        self.setup_ui()
        self.refresh_sheet_list()

    def setup_ui(self):
        # 2 Columns: List (Left), Details (Right)
        self.grid_columnconfigure(0, weight=0, minsize=250)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- LEFT PANEL (List) ---
        left_panel = ctk.CTkFrame(self, corner_radius=0)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 2), pady=0)
        
        ctk.CTkLabel(left_panel, text="Danh Sách Sheets", font=("Arial", 14, "bold")).pack(pady=10)
        
        self.sheet_list_frame = ctk.CTkScrollableFrame(left_panel, fg_color="transparent")
        self.sheet_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Buttons at bottom of left panel
        btn_frame_left = ctk.CTkFrame(left_panel, fg_color="transparent")
        btn_frame_left.pack(fill="x", pady=10, padx=5)
        
        ctk.CTkButton(btn_frame_left, text="+ Add New", command=self.add_new, width=100, fg_color="white", text_color="black", hover_color="gray90").pack(side="left", padx=5, expand=True)
        ctk.CTkButton(btn_frame_left, text="Delete", command=self.delete_current, width=100, fg_color="white", text_color="black", hover_color="gray90").pack(side="right", padx=5, expand=True)


        # --- RIGHT PANEL (Details) ---
        right_panel = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent") # Main bg
        right_panel.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(right_panel, text="Sheet Details", font=("Arial", 14, "bold")).pack(pady=(0, 10))
        
        # Allow scrolling for details
        self.details_scroll = ctk.CTkScrollableFrame(right_panel, fg_color="transparent")
        self.details_scroll.pack(fill="both", expand=True)
        
        form_container = self.details_scroll
        
        # Name and URL
        self.name_var = tk.StringVar()
        self.url_var = tk.StringVar()
        
        self._add_row(form_container, "Sheet Name:", self.name_var)
        self._add_row(form_container, "Google Form URL:", self.url_var)
        
        # Auto Extract Button
        self.extract_btn = ctk.CTkButton(form_container, text="🔍 Auto Extract Fields", command=self.run_auto_extract, 
                                         fg_color="gray70", text_color="black", hover_color="gray60", width=200)
        self.extract_btn.pack(pady=15)
        
        ctk.CTkLabel(form_container, text="Field Mapping:", font=("Arial", 12, "bold"), anchor="w").pack(fill="x", pady=(10, 5))
        
        # Field Inputs
        for key in self.field_keys:
            label_text = key.replace("_", " ").title() + ":"
            var = tk.StringVar()
            self.entry_widgets[key] = var
            self._add_row(form_container, label_text, var)

        # Footer Buttons
        footer = ctk.CTkFrame(form_container, fg_color="transparent")
        footer.pack(pady=30)
        
        self.save_btn = ctk.CTkButton(footer, text="💾 Save", command=self.save, width=150, fg_color="gray70", text_color="black", hover_color="gray60")
        self.save_btn.pack(side="left", padx=10)
        
        ctk.CTkButton(footer, text="❌ Cancel", command=self.load_selected, width=150, fg_color="gray70", text_color="black", hover_color="gray60").pack(side="left", padx=10)

    def _add_row(self, parent, label_str, variable):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=2)
        ctk.CTkLabel(f, text=label_str, width=140, anchor="w").pack(side="left")
        ctk.CTkEntry(f, textvariable=variable).pack(side="left", fill="x", expand=True, padx=5)

    def refresh_sheet_list(self):
        for c in self.sheet_list_frame.winfo_children(): c.destroy()
        for s in self.sheet_manager.list_sheets():
            btn = ctk.CTkButton(self.sheet_list_frame, text=s['name'], fg_color="transparent", 
                                command=lambda x=s: self.load_sheet(x), anchor="w")
            btn.pack(fill="x", pady=1)
            # Highlight selected
            if self.selected_id == s['id']:
                 btn.configure(fg_color=("gray75", "gray30"))

    def add_new(self):
        self.selected_id = None
        self.name_var.set("")
        self.url_var.set("")
        for v in self.entry_widgets.values(): v.set("")
        self.refresh_sheet_list() # To clear selection highlight

    def load_sheet(self, s):
        self.selected_id = s['id']
        self.name_var.set(s['name'])
        self.url_var.set(s['form_url'])
        
        fields = s.get('fields', {})
        for key, var in self.entry_widgets.items():
            var.set(fields.get(key, ""))
        
        self.refresh_sheet_list() # Update selection highlight

    def load_selected(self):
        if self.selected_id:
            s = self.sheet_manager.get_sheet(self.selected_id)
            if s: self.load_sheet(s)
        else:
            self.add_new()

    def run_auto_extract(self):
        url = self.url_var.get().strip()
        if not url: return messagebox.showerror("Error", "URL required")
        
        def run():
            self.extract_btn.configure(text="Scanning...", state="disabled")
            try:
                res = self.sheet_manager.extract_form_fields(url)
                
                def finish():
                    self.extract_btn.configure(text="🔍 Auto Extract Fields", state="normal")
                    if not res: 
                        return messagebox.showerror("Error", "Scan failed.")
                    
                    found_fields = res.get("fields", {})
                    # Populate entries
                    for key, val in found_fields.items():
                        if key in self.entry_widgets:
                            self.entry_widgets[key].set(val)
                            
                    # Update URL if redirected
                    if res.get("form_url"):
                        self.url_var.set(res["form_url"])
                        
                    count = len(found_fields)
                    messagebox.showinfo("Success", f"Extracted {count} fields.")
                
                self.app.after(0, finish)
            except Exception as e:
                self.app.after(0, lambda: self.extract_btn.configure(text="🔍 Auto Extract Fields", state="normal"))
                self.app.after(0, lambda: messagebox.showerror("Error", str(e)))
        
        threading.Thread(target=run, daemon=True).start()

    def save(self):
        name = self.name_var.get().strip()
        url = self.url_var.get().strip()
        if not name or not url: return messagebox.showerror("Error", "Name and URL required")
        
        # Collect fields
        fields = {}
        for key, var in self.entry_widgets.items():
            val = var.get().strip()
            if val: fields[key] = val
            
        if self.selected_id:
            if self.sheet_manager.update_sheet(self.selected_id, name=name, form_url=url, fields=fields):
                messagebox.showinfo("Saved", "Sheet updated.")
        else:
            if self.sheet_manager.add_sheet(name, url, fields):
                messagebox.showinfo("Saved", "New sheet added.")
                self.add_new()
        
        self.refresh_sheet_list()
        self.app.refresh_all_crawler_tabs()

    def delete_current(self):
        if not self.selected_id: return
        if messagebox.askyesno("Confirm", "Delete this sheet configuration?"):
            self.sheet_manager.remove_sheet(self.selected_id)
            self.add_new()
            self.app.refresh_all_crawler_tabs()

class AccountTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.manager = get_account_manager()
        self.current_page = 1
        self.items_per_page = 10
        self.setup_ui()
        self.refresh_accounts()

    def setup_ui(self):
        # Header Area
        header_area = ctk.CTkFrame(self, fg_color="transparent")
        header_area.pack(fill="x", padx=20, pady=(20, 10))
        
        # Row 1: Search and Main Actions
        row1 = ctk.CTkFrame(header_area, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh_accounts())
        self.search_entry = ctk.CTkEntry(row1, placeholder_text="Search email...", 
                                         textvariable=self.search_var, width=250, height=35, corner_radius=10)
        self.search_entry.pack(side="left")
        
        # View toggles (Icons)
        view_frame = ctk.CTkFrame(row1, fg_color="transparent")
        view_frame.pack(side="left", padx=15)
        ctk.CTkLabel(view_frame, text="≡", font=("Arial", 24), text_color="gray70").pack(side="left", padx=5)
        ctk.CTkLabel(view_frame, text="⊞", font=("Arial", 20), text_color="gray40").pack(side="left", padx=5)

        right_btns = ctk.CTkFrame(row1, fg_color="transparent")
        right_btns.pack(side="right")
        
        ctk.CTkButton(right_btns, text="+ Add Account", command=self.open_add_account, 
                      width=120, height=35, fg_color="#1f538d", font=("Outfit", 12, "bold")).pack(side="left", padx=5)
        ctk.CTkButton(right_btns, text="🔄", command=self.refresh_all_quotas, 
                      width=35, height=35, fg_color="#3f3f46").pack(side="left", padx=5)
        ctk.CTkButton(right_btns, text="📤", width=35, height=35, fg_color="#3f3f46").pack(side="left", padx=5)

        # Row 2: Filter Chips
        row2 = ctk.CTkFrame(header_area, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        
        self.filter_var = tk.StringVar(value="All")
        filters = ["All", "Available", "Low Quota", "PRO", "ULTRA"]
        for f in filters:
            btn = ctk.CTkButton(row2, text=f, width=80, height=28, corner_radius=15,
                                fg_color="#27272a" if f != "All" else "#1f538d",
                                font=("Outfit", 11),
                                command=lambda x=f: self.set_filter(x))
            btn.pack(side="left", padx=2)
            if f == "All": self.active_filter_btn = btn

        # Table Header (Optional for look)
        # self.create_table_header(header_area)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        # Footer Area (Pagination)
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.pack(fill="x", padx=20, pady=(0, 20))
        
        self.pagination_info = ctk.CTkLabel(self.footer, text="Showing 0 to 0 of 0 entries", 
                                          font=("Outfit", 12), text_color="gray70")
        self.pagination_info.pack(side="left")
        
        # Per Page selector
        ctk.CTkLabel(self.footer, text="Per page", font=("Outfit", 12), text_color="gray70").pack(side="left", padx=(20, 5))
        self.per_page_var = tk.StringVar(value="10 items")
        self.per_page_combo = ctk.CTkComboBox(self.footer, values=["5 items", "10 items", "20 items", "50 items"], 
                                             variable=self.per_page_var, width=100, height=28, 
                                             command=self.on_per_page_change)
        self.per_page_combo.pack(side="left")

        # Pagination Buttons
        self.page_btns_frame = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.page_btns_frame.pack(side="right")
        
    def on_per_page_change(self, val):
        self.items_per_page = int(val.split()[0])
        self.current_page = 1
        self.refresh_accounts()

    def set_filter(self, f):
        self.filter_var.set(f)
        self.refresh_accounts()

    def refresh_accounts(self):
        for c in self.scroll.winfo_children(): c.destroy()
        for c in self.page_btns_frame.winfo_children(): c.destroy()
        
        accounts = self.manager.get_all_accounts()
        search_query = self.search_var.get().lower()
        filter_val = self.filter_var.get()
        
        filtered = []
        for acc in accounts:
            # Search filter
            if search_query and search_query not in acc.get('email', '').lower():
                continue
            
            # Quota/Tier filters
            tier = acc.get('quota', {}).get('subscription_tier', 'free-tier').lower()
            if filter_val == "PRO" and "pro" not in tier: continue
            if filter_val == "ULTRA" and "ultra" not in tier: continue
            
            models = acc.get('quota', {}).get('models', [])
            total_remaining = sum(m.get('percentage', 0) for m in models) / (len(models) if models else 1)
            
            if filter_val == "Available" and total_remaining < 80: continue
            if filter_val == "Low Quota" and total_remaining >= 30: continue
            
            filtered.append(acc)

        total_count = len(filtered)
        
        # Slice for pagination
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_count)
        page_items = filtered[start_idx:end_idx]

        if not filtered:
            self.pagination_info.configure(text="Showing 0 to 0 of 0 entries")
            ctk.CTkLabel(self.scroll, text="No accounts found.", text_color="gray").pack(pady=50)
            return

        for acc in page_items:
            self.create_account_card(acc)
            
        # Update Footer
        self.pagination_info.configure(text=f"Showing {start_idx + 1} to {end_idx} of {total_count} entries")
        
        # Build Page Buttons
        total_pages = (total_count + self.items_per_page - 1) // self.items_per_page
        
        # Previous btn
        prev_btn = ctk.CTkButton(self.page_btns_frame, text="<", width=30, height=30, 
                               fg_color="#18181b", corner_radius=5, state="normal" if self.current_page > 1 else "disabled",
                               command=lambda: self.change_page(self.current_page - 1))
        prev_btn.pack(side="left", padx=2)
        
        # Current Page btn (mockup style)
        page_lbl = ctk.CTkButton(self.page_btns_frame, text=str(self.current_page), width=30, height=30, 
                               fg_color="#1f538d", corner_radius=5)
        page_lbl.pack(side="left", padx=2)
        
        # Next btn
        next_btn = ctk.CTkButton(self.page_btns_frame, text=">", width=30, height=30, 
                               fg_color="#18181b", corner_radius=5, state="normal" if self.current_page < total_pages else "disabled",
                               command=lambda: self.change_page(self.current_page + 1))
        next_btn.pack(side="left", padx=2)

    def change_page(self, page_num):
        self.current_page = page_num
        self.refresh_accounts()

    def create_account_card(self, acc):
        # We use a single frame for the 'row'
        row = ctk.CTkFrame(self.scroll, fg_color="#18181b", corner_radius=10, height=80)
        row.pack(fill="x", pady=4, padx=5)
        
        # Grid layout for table columns
        row.grid_columnconfigure(1, weight=3) # Email/Tier
        row.grid_columnconfigure(2, weight=4) # Models-1
        row.grid_columnconfigure(3, weight=4) # Models-2
        row.grid_columnconfigure(4, weight=1) # Date
        row.grid_columnconfigure(5, weight=0) # Actions

        # Col 0: Checkbox visual
        ctk.CTkCheckBox(row, text="", width=20, corner_radius=4).grid(row=0, column=0, padx=(15, 5), pady=15)

        # Col 1: Email & Badges
        email_frame = ctk.CTkFrame(row, fg_color="transparent")
        email_frame.grid(row=0, column=1, sticky="w", padx=5)
        
        email = acc.get('email', 'N/A')
        tier = acc.get('quota', {}).get('subscription_tier', 'free-tier').lower()
        
        ctk.CTkLabel(email_frame, text=email, font=("Outfit", 14, "bold"), text_color="#60a5fa").pack(side="left")
        
        # Tier Badges
        if "pro" in tier:
            ctk.CTkLabel(email_frame, text="◆ PRO", font=("Outfit", 10, "bold"), 
                         fg_color="#1e40af", text_color="#bfdbfe", corner_radius=4, padx=5).pack(side="left", padx=10)
        else:
            ctk.CTkLabel(email_frame, text="○ FREE", font=("Outfit", 10, "bold"), 
                         fg_color="#3f3f46", text_color="gray80", corner_radius=4, padx=5).pack(side="left", padx=10)
        
        # Col 2 & 3: Models Grid (Compact)
        models = acc.get('quota', {}).get('models', [])
        
        # We split models into 2 columns of 2 labels each
        m_frame1 = ctk.CTkFrame(row, fg_color="transparent")
        m_frame1.grid(row=0, column=2, sticky="ew")
        m_frame2 = ctk.CTkFrame(row, fg_color="transparent")
        m_frame2.grid(row=0, column=3, sticky="ew")

        def create_mini_block(parent, mdata):
            f = ctk.CTkFrame(parent, fg_color="#27272a", corner_radius=4, height=30)
            f.pack(fill="x", padx=2, pady=2)
            
            name = mdata.get('name', '').replace('models/', '')
            if "flash" in name: short = "G3 Fla."
            elif "pro" in name: short = "G3 Pro"
            elif "image" in name: short = "G3 Ima."
            elif "claude" in name: short = "Claud."
            else: short = name[:7]
            
            pct = mdata.get('percentage', 0)
            color = "#22c55e" if pct > 70 else "#f59e0b" if pct > 30 else "#ef4444"
            
            ctk.CTkLabel(f, text=short, font=("Consolas", 10), text_color="gray70").pack(side="left", padx=5)
            ctk.CTkLabel(f, text=f"{pct}%", font=("Consolas", 10, "bold"), text_color=color).pack(side="right", padx=5)

        # Show first 4 models in 2x2 grid-like setup
        for i, m in enumerate(models[:4]):
            target = m_frame1 if i < 2 else m_frame2
            create_mini_block(target, m)

        # Col 4: Date
        created_at = acc.get('created_at', 0)
        date_str = datetime.fromtimestamp(created_at).strftime("%d/%m/%Y")
        time_str = datetime.fromtimestamp(created_at).strftime("%H:%M")
        
        date_frame = ctk.CTkFrame(row, fg_color="transparent")
        date_frame.grid(row=0, column=4, padx=10)
        ctk.CTkLabel(date_frame, text=date_str, font=("Consolas", 11), text_color="gray70").pack()
        ctk.CTkLabel(date_frame, text=time_str, font=("Consolas", 10), text_color="gray50").pack()

        # Col 5: Actions
        act_frame = ctk.CTkFrame(row, fg_color="transparent")
        act_frame.grid(row=0, column=5, padx=(0, 15))
        
        # Info, Switch (placeholder), Refresh, Delete icons
        ctk.CTkLabel(act_frame, text="ⓘ", font=("Arial", 16), text_color="gray60").pack(side="left", padx=3)
        
        # Use buttons for clickable ones
        ctk.CTkButton(act_frame, text="🔄", width=30, height=30, fg_color="transparent", 
                      text_color="gray70", command=lambda a=acc['id']: self.refresh_quota(a)).pack(side="left")
        ctk.CTkButton(act_frame, text="B", width=30, height=30, fg_color="#ea580c", hover_color="#c2410c",
                      text_color="white", font=("Arial", 14, "bold"),
                      command=lambda a=acc['id']: self.open_blogspot_manager(a)).pack(side="left", padx=2)
        ctk.CTkButton(act_frame, text="🗑", width=30, height=30, fg_color="transparent", 
                      text_color="#ef4444", command=lambda a=acc['id']: self.delete_account(a)).pack(side="left")

    def refresh_quota(self, account_id):
        def run():
            try:
                access_token, project_id, _ = self.manager.refresh_and_get(account_id)
                models = self.manager.fetch_available_models_network(access_token, project_id)
                if models:
                    with self.manager.lock:
                        acc = self.manager.accounts[account_id]['data']
                        acc['quota']['models'] = models
                        acc['quota']['last_updated'] = int(time.time())
                        self.manager.save_account(account_id)
                self.app.after(0, self.refresh_accounts)
            except Exception as e:
                self.app.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def refresh_all_quotas(self):
        def run():
            accounts = self.manager.get_all_accounts()
            for acc in accounts:
                try:
                    access_token, project_id, _ = self.manager.refresh_and_get(acc['id'])
                    models = self.manager.fetch_available_models_network(access_token, project_id)
                    if models:
                        with self.manager.lock:
                             acc_data = self.manager.accounts[acc['id']]['data']
                             acc_data['quota']['models'] = models
                             acc_data['quota']['last_updated'] = int(time.time())
                             self.manager.save_account(acc['id'])
                except: pass
            self.app.after(0, self.refresh_accounts)
        threading.Thread(target=run, daemon=True).start()

    def delete_account(self, account_id):
        if messagebox.askyesno("Confirm", "Delete this account?"):
            self.manager.delete_account(account_id)
            self.refresh_accounts()

    def open_add_account(self):
        AddAccountDialog(self)

    def open_blogspot_manager(self, account_id):
        BlogspotManagerDialog(self, self.manager, account_id)

class AddAccountDialog(ctk.CTkToplevel):
    def __init__(self, parent_tab):
        super().__init__()
        self.parent_tab = parent_tab
        self.app = parent_tab.app
        self.manager = parent_tab.manager
        self.title("Add Google Account")
        self.geometry("450x550")
        self.setup_ui()
        
    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Connect Account", font=("Outfit", 24, "bold")).pack(pady=(30, 10))
        ctk.CTkLabel(self, text="Add a Google Refresh Token to the pool", text_color="gray70").pack()
        self.oauth_btn = ctk.CTkButton(self, text="Login with Google", font=("Outfit", 14, "bold"), 
                                       fg_color="white", text_color="black", hover_color="gray90",
                                       height=45, command=self.start_oauth)
        self.oauth_btn.pack(fill="x", padx=40, pady=30)
        ctk.CTkLabel(self, text="OR MANUAL ENTRY", font=("Outfit", 10), text_color="gray50").pack()
        self.token_var = tk.StringVar()
        self.token_entry = ctk.CTkEntry(self, placeholder_text="Refresh Token (1//0...)", 
                                        textvariable=self.token_var, height=40)
        self.token_entry.pack(fill="x", padx=40, pady=10)
        self.reg_btn = ctk.CTkButton(self, text="Register with Token", height=45, command=self.manual_register)
        self.reg_btn.pack(fill="x", padx=40, pady=10)
        self.status_lbl = ctk.CTkLabel(self, text="", wraplength=350)
        self.status_lbl.pack(pady=10)
        ctk.CTkLabel(self, text="How to get a refresh token?", font=("Outfit", 12, "bold"), text_color="gray60").pack(anchor="w", padx=40, pady=(20, 5))
        ctk.CTkLabel(self, text="Login with Google is recommended. For manual entry, extract the refresh_token from your app's session or developer console.", 
                     text_color="gray50", font=("Outfit", 11), wraplength=370, justify="left").pack(padx=40)

    def start_oauth(self):
        self.oauth_btn.configure(state="disabled", text="Check Browser...")
        def run_server():
            from flask import Flask, request as f_request
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            app = Flask(__name__)
            @app.route('/oauth-callback')
            def callback():
                code = f_request.args.get('code')
                if not code: return "Error: No code"
                try:
                    url = "https://oauth2.googleapis.com/token"
                    data = {"client_id": AccountManager.CLIENT_ID, "client_secret": AccountManager.CLIENT_SECRET,
                            "code": code, "redirect_uri": "http://localhost:5007/oauth-callback", "grant_type": "authorization_code"}
                    resp = requests.post(url, data=data, timeout=10)
                    if resp.ok:
                        token_data = resp.json()
                        rt = token_data.get('refresh_token')
                        if rt:
                            aid, email = self.manager.register_account(rt)
                            self.after(0, lambda: self.finish_success(email))
                            return f"Success! Registered {email}. You can close this window."
                    return f"Error: {resp.text}"
                except Exception as e: return f"Exception: {str(e)}"
            try:
                app.run(port=5007)
            except Exception as e:
                print(f"Flask Server Error: {e}")
                # If 5007 is busy, we might just fail gracefully or try another
        import webbrowser
        scopes = ["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/userinfo.email", 
                  "https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/cclog", 
                  "https://www.googleapis.com/auth/experimentsandconfigs"]
        auth_url = ("https://accounts.google.com/o/oauth2/v2/auth?"
                    f"client_id={AccountManager.CLIENT_ID}&redirect_uri=http://localhost:5007/oauth-callback&"
                    f"response_type=code&scope={' '.join(scopes)}&access_type=offline&prompt=consent")
        if hasattr(self.app, "_oauth_server_started"):
             webbrowser.open(auth_url)
             return
             
        self.app._oauth_server_started = True
        webbrowser.open(auth_url)
        threading.Thread(target=run_server, daemon=True).start()

    def manual_register(self):
        token = self.token_var.get().strip()
        if not token: return
        self.reg_btn.configure(state="disabled", text="Verifying...")
        def run():
            try:
                aid, email = self.manager.register_account(token)
                self.after(0, lambda: self.finish_success(email))
            except Exception as e:
                def on_error(msg):
                    if self.winfo_exists():
                        self.status_lbl.configure(text=msg, text_color="red")
                        self.reg_btn.configure(state="normal", text="Register with Token")
                self.after(0, lambda: on_error(str(e)))
        threading.Thread(target=run, daemon=True).start()

    def finish_success(self, email):
        if not self.winfo_exists(): return
        try:
            if hasattr(self, "status_lbl") and self.status_lbl.winfo_exists():
                self.status_lbl.configure(text=f"Successfully registered {email}", text_color="green")
            self.parent_tab.refresh_accounts()
            # Delay destroy to show success message
            self.after(2000, lambda: self.destroy() if self.winfo_exists() else None)
        except:
             pass

class BlogspotManagerDialog(ctk.CTkToplevel):
    def __init__(self, parent, manager, account_id):
        super().__init__()
        self.parent = parent
        self.manager = manager
        self.account_id = account_id
        self.title("Blogspot Manager")
        self.geometry("800x600")
        
        self.setup_ui()
        self.load_blogs()
        
    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=20)
        ctk.CTkLabel(header, text="Blogspot Management", font=("Outfit", 20, "bold")).pack(side="left")
        ctk.CTkButton(header, text="Refresh", width=80, command=self.load_blogs).pack(side="right")

        # Main Scrollable Area
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)
        
        # Action Area (Create?)
        footer = ctk.CTkFrame(self, fg_color="#18181b", height=100)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=20)
        
        ctk.CTkLabel(footer, text="Check Availability / Setup", font=("Outfit", 14, "bold")).pack(anchor="w", padx=15, pady=10)
        
        # Row 1: Title
        t_row = ctk.CTkFrame(footer, fg_color="transparent")
        t_row.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkLabel(t_row, text="Title:", width=60, anchor="w", text_color="gray70").pack(side="left")
        self.title_var = tk.StringVar()
        ctk.CTkEntry(t_row, textvariable=self.title_var, width=250, placeholder_text="My Blog Title").pack(side="left", padx=5)

        # Row 2: Subdomain & Check
        f_row = ctk.CTkFrame(footer, fg_color="transparent")
        f_row.pack(fill="x", padx=15, pady=(0, 15))
        
        ctk.CTkLabel(f_row, text="URL:", width=60, anchor="w", text_color="gray70").pack(side="left")
        self.subdomain_var = tk.StringVar()
        self.subdomain_var.trace_add("write", self.on_subdomain_change)

        ctk.CTkEntry(f_row, placeholder_text="my-awesome-blog", textvariable=self.subdomain_var, width=200).pack(side="left", padx=(5, 0))
        ctk.CTkLabel(f_row, text=".blogspot.com", text_color="gray60").pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(f_row, text="Check Availability", command=self.check_avail, fg_color="#1f538d", width=120).pack(side="left", padx=5)
        
        self.create_btn = ctk.CTkButton(f_row, text="Create via API", command=self.create_blog_action, fg_color="#10b981", width=120, state="disabled")
        self.create_btn.pack(side="left", padx=5)
        
        ctk.CTkButton(f_row, text="Web Create", command=self.open_web_create, fg_color="#3f3f46", width=80).pack(side="left", padx=5)
        
        self.check_lbl = ctk.CTkLabel(f_row, text="")
        self.check_lbl.pack(side="left", padx=10)

    def on_subdomain_change(self, *args):
        # Reset availability check if user types
        self.create_btn.configure(state="disabled", fg_color="#10b981") 
        self.check_lbl.configure(text="")

    def open_web_create(self):
        import webbrowser
        webbrowser.open("https://www.blogger.com/onboarding")

    def load_blogs(self):
        for w in self.scroll.winfo_children(): w.destroy()
        
        def run():
            try:
                acc_token, _, _ = self.manager.refresh_and_get(self.account_id)
                # Checks scopes first
                t_info = self.manager.get_token_info(acc_token)
                scope_str = t_info.get("scope", "")
                if "blogger" not in scope_str:
                    self.after(0, lambda: self.show_permission_error("Missing Blogger permission."))
                    return

                blogs = self.manager.list_blogs(acc_token)
                self.after(0, lambda: self.render_blogs(blogs))
            except Exception as e:
                msg = str(e)
                if "403" in msg or "Insufficient Permission" in msg:
                    self.after(0, lambda: self.show_permission_error(msg))
                else:
                    self.after(0, lambda: messagebox.showerror("Error", msg))
        threading.Thread(target=run, daemon=True).start()

    def show_permission_error(self, msg):
        for w in self.scroll.winfo_children(): w.destroy()
        ctk.CTkLabel(self.scroll, text=f"Error: {msg}", text_color="#ef4444").pack(pady=(20, 10))
        ctk.CTkLabel(self.scroll, text="You need to re-authorize this account to manage blogs.", text_color="gray70").pack()
        ctk.CTkButton(self.scroll, text="Grant Permissions / Re-Login", fg_color="#ea580c", 
                      command=self.start_reauth).pack(pady=20)
    
    def start_reauth(self):
         # Start OAuth Flow specifically for updating this account
         import webbrowser
         scopes = ["https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/userinfo.email", 
                   "https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/cclog", 
                   "https://www.googleapis.com/auth/experimentsandconfigs", "https://www.googleapis.com/auth/blogger"]
         auth_url = ("https://accounts.google.com/o/oauth2/v2/auth?"
                     f"client_id={AccountManager.CLIENT_ID}&redirect_uri=http://localhost:5007/oauth-callback&"
                     f"response_type=code&scope={' '.join(scopes)}&access_type=offline&prompt=consent")
         
         webbrowser.open(auth_url)
         
         # Reuse the server method logic but distinct callback handler? 
         # We can reuse the same port/endpoint, but we need to know we are in "Update Mode".
         # Simplest is to spin up a temporary server here or reuse AddAccountDialog logic logic.
         # For speed, I'll inline a simple server here or hook into a shared one.
         
         def run_reauth_server():
            from flask import Flask, request as f_request
            import logging
            log = logging.getLogger('werkzeug'); log.setLevel(logging.ERROR)
            app = Flask(__name__)
            @app.route('/oauth-callback')
            def callback():
                code = f_request.args.get('code')
                if not code: return "Error: No code"
                try:
                    url = "https://oauth2.googleapis.com/token"
                    data = {"client_id": AccountManager.CLIENT_ID, "client_secret": AccountManager.CLIENT_SECRET,
                            "code": code, "redirect_uri": "http://localhost:5007/oauth-callback", "grant_type": "authorization_code"}
                    resp = requests.post(url, data=data, timeout=10)
                    if resp.ok:
                        token_data = resp.json()
                        # Update the account
                        rt = token_data.get('refresh_token')
                        at = token_data.get('access_token')
                        now = int(time.time())
                        update_data = {
                            "access_token": at,
                            "expires_in": token_data.get('expires_in', 3600),
                            "expiry_timestamp": now + token_data.get('expires_in', 3600)
                        }
                        if rt: update_data["refresh_token"] = rt
                        
                        self.manager.update_account_token_data(self.account_id, update_data)
                        self.after(0, lambda: messagebox.showinfo("Success", "Permissions granted! Reloading..."))
                        self.after(2000, self.load_blogs)
                        return "Success! You can close this window."
                    return f"Error: {resp.text}"
                except Exception as e: return f"Exception: {str(e)}"
            try: app.run(port=5007)
            except: pass # Port busy?
            
         threading.Thread(target=run_reauth_server, daemon=True).start()

    def render_blogs(self, blogs):
        if not blogs:
            ctk.CTkLabel(self.scroll, text="No blogs found or no permission.", text_color="gray").pack(pady=20)
            return

        for blog in blogs:
            self.create_blog_card(blog)

    def create_blog_card(self, blog):
        card = ctk.CTkFrame(self.scroll, fg_color="#27272a", corner_radius=8)
        card.pack(fill="x", pady=5)
        
        # Info
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(side="left", padx=15, pady=15)
        
        name = blog.get('name', 'Untitled')
        url = blog.get('url', 'No URL')
        bid = blog.get('id')
        
        ctk.CTkLabel(info, text=name, font=("Outfit", 16, "bold")).pack(anchor="w")
        ctk.CTkLabel(info, text=url, text_color="gray60", font=("Consolas", 12)).pack(anchor="w")
        
        # Custom Domain Action
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(side="right", padx=15, pady=15)
        
        ctk.CTkButton(actions, text="Set DNS / Custom Domain", 
                      command=lambda: self.open_dns_dialog(bid, name, url)).pack()

    def check_avail(self):
        sub = self.subdomain_var.get().strip()
        if not sub: return
        self.check_lbl.configure(text="Checking...", text_color="gray")
        
        def run():
            try:
                acc_token, _, _ = self.manager.refresh_and_get(self.account_id)
                res = self.manager.check_blog_url_availability(acc_token, sub)
                status = res.get('status') if res else "UNKNOWN"
                self.after(0, lambda: self.show_check_result(status))
            except Exception as e:
                print(e)
        threading.Thread(target=run, daemon=True).start()

    def show_check_result(self, status):
        is_avail = (status == "AVAILABLE")
        color = "green" if is_avail else "red"
        text = "Available!" if is_avail else f"Taken ({status})"
        self.check_lbl.configure(text=text, text_color=color)
        
        if is_avail:
            self.create_btn.configure(state="normal")
        else:
            self.create_btn.configure(state="disabled")

    def create_blog_action(self):
        title = self.title_var.get().strip()
        sub = self.subdomain_var.get().strip()
        
        if not title:
            messagebox.showwarning("Validation", "Please enter a blog title.")
            return
            
        self.create_btn.configure(text="Creating...", state="disabled")
        
        def run():
            try:
                acc_token, _, _ = self.manager.refresh_and_get(self.account_id)
                res = self.manager.create_blog(acc_token, title, sub)
                
                if res and "error" in res:
                    msg = res['error']
                    # Friendly fallback message
                    if "403" in msg or "404" in msg or "not supported" in msg.lower():
                        self.after(0, lambda: self.show_create_error(f"API Creation Failed: {msg}\n\nGoogle often restricts API creation. Please use 'Web Create'."))
                    else:
                        self.after(0, lambda: self.show_create_error(msg))
                else:
                    self.after(0, lambda: self.finish_create_success())
            except Exception as e:
                self.after(0, lambda: self.show_create_error(str(e)))
                
        threading.Thread(target=run, daemon=True).start()

    def show_create_error(self, msg):
        messagebox.showerror("Creation Failed", msg)
        self.create_btn.configure(text="Create via API", state="normal")

    def finish_create_success(self):
        messagebox.showinfo("Success", "Blog created successfully!")
        self.create_btn.configure(text="Success", state="disabled")
        self.load_blogs()

    def open_dns_dialog(self, blog_id, name, current_url):
        d = ctk.CTkToplevel(self)
        d.title(f"DNS for {name}")
        d.geometry("400x300")
        
        ctk.CTkLabel(d, text="Set Custom Domain", font=("Outfit", 16, "bold")).pack(pady=20)
        
        entry = ctk.CTkEntry(d, placeholder_text="www.example.com", width=250)
        entry.pack(pady=10)
        
        lbl = ctk.CTkLabel(d, text="Make sure you have added a CNAME record\npointing to ghs.google.com", 
                           text_color="gray60")
        lbl.pack(pady=10)
        
        def save():
            domain = entry.get().strip()
            if not domain: return
            
            def run_save():
                try:
                    acc, _, _ = self.manager.refresh_and_get(self.account_id)
                    res = self.manager.set_blog_custom_domain(acc, blog_id, domain)
                    if "error" in res:
                        self.after(0, lambda: messagebox.showerror("Failed", res['error']))
                    else:
                        self.after(0, lambda: messagebox.showinfo("Success", f"Domain set to {domain}"))
                        self.load_blogs()
                        d.destroy()
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error", str(e)))
            threading.Thread(target=run_save, daemon=True).start()
            
        ctk.CTkButton(d, text="Save Domain", command=save, fg_color="#10b981").pack(pady=20)

class AutoWriterTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.stop_event = threading.Event()
        self.is_running = False
        self.is_refilling = False
        self.tab_name_var = tk.StringVar(value="New Writer")
        self.dest_mode_var = tk.IntVar(value=0)
        self.counter_var = tk.StringVar(value="0 processed")
        self.processed_count = 0
        self.thread_count_var = tk.IntVar(value=1)
        self.queue_lock = threading.Lock()
        self.wp_manager = get_wp_manager()
        self.sheet_manager = get_sheet_manager()
        self.generated_history = set() # Track generated titles to avoid duplicates
        self.setup_ui()

    def safe_get_titles_text(self):
        """Thread-safe way to get text from titles_text widget"""
        result = [""]
        done = threading.Event()
        
        def _get():
            try:
                result[0] = self.titles_text.get("1.0", "end")
            except Exception as e:
                print(f"UI Read Error: {e}")
            finally:
                done.set()
        
        self.after(0, _get)
        # Wait up to 2 seconds for UI thread to respond
        if done.wait(timeout=2.0):
            return result[0]
        return ""

    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # Main content area expands

        # 1. Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(5, 5))
        
        ctk.CTkLabel(header, text="Tab Name:").pack(side="left", padx=5)
        self.name_entry = ctk.CTkEntry(header, textvariable=self.tab_name_var, width=150)
        self.name_entry.pack(side="left", padx=5)
        self.name_entry.bind("<FocusOut>", lambda e: self.app.update_sidebar_crawlers())
        self.name_entry.bind("<Return>", lambda e: self.app.update_sidebar_crawlers())

        ctk.CTkLabel(header, text="✍️ Auto Writer & Poster", font=("Outfit", 24, "bold")).pack(side="left", padx=30)
        
        # 2. Configuration area (Topic, Target, Model)
        config_card = ctk.CTkFrame(self, fg_color="#18181b", corner_radius=15)
        config_card.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        
        inner = ctk.CTkFrame(config_card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=15)
        
        # Row 1: Topic
        topic_row = ctk.CTkFrame(inner, fg_color="transparent")
        topic_row.pack(fill="x", pady=5)
        ctk.CTkLabel(topic_row, text="Topic:", font=("Outfit", 14, "bold"), width=70, anchor="w").pack(side="left")
        self.topic_var = tk.StringVar(value="Phát triển bản thân, kỹ năng sống, tâm lý tích cực")
        self.topic_entry = ctk.CTkEntry(topic_row, textvariable=self.topic_var, placeholder_text="Enter topic to generate titles...", height=35)
        self.topic_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        self.gen_titles_btn = ctk.CTkButton(topic_row, text="✨ Generate Titles", width=150, height=35, 
                                            command=lambda: self.start_title_gen_async(), fg_color="#1f538d", font=("Outfit", 12, "bold"))
        self.gen_titles_btn.pack(side="left", padx=(10, 0))

        # Row 2: Target & Model
        tm_row = ctk.CTkFrame(inner, fg_color="transparent")
        tm_row.pack(fill="x", pady=5)
        ctk.CTkLabel(tm_row, text="Target:", font=("Outfit", 14, "bold"), width=70, anchor="w").pack(side="left")
        
        ctk.CTkRadioButton(tm_row, text="Sheet", variable=self.dest_mode_var, value=0, command=self.toggle_dest_mode).pack(side="left", padx=5)
        ctk.CTkRadioButton(tm_row, text="WP API", variable=self.dest_mode_var, value=1, command=self.toggle_dest_mode).pack(side="left", padx=5)
        
        self.sheet_combo = ctk.CTkComboBox(tm_row, state="readonly", width=180)
        self.sheet_combo.pack(side="left", padx=5)
        
        self.wp_combo = ctk.CTkComboBox(tm_row, state="readonly", width=150, command=self.on_wp_site_selected)
        self.cat_label = ctk.CTkLabel(tm_row, text="Cat:")
        self.cat_combo = ctk.CTkComboBox(tm_row, state="readonly", width=100)
        
        # Row 2.5: Model & Threads
        mt_row = ctk.CTkFrame(inner, fg_color="transparent")
        mt_row.pack(fill="x", pady=5)
        
        ctk.CTkLabel(mt_row, text="Model:", font=("Outfit", 12), width=70, anchor="w").pack(side="left")
        self.model_var = tk.StringVar(value="gemini-2.0-flash-exp")
        self.model_combo = ctk.CTkComboBox(mt_row, variable=self.model_var, values=["gemini-2.0-flash-exp", "gemini-2.5-flash", "claude-sonnet-3.5", "gpt-4o"], width=180)
        self.model_combo.pack(side="left", padx=5)

        ctk.CTkLabel(mt_row, text="Threads:", font=("Outfit", 12)).pack(side="left", padx=(20, 5))
        self.thread_slider = ctk.CTkSlider(mt_row, from_=1, to=10, number_of_steps=9, variable=self.thread_count_var, width=150)
        self.thread_slider.pack(side="left", padx=5)
        self.thread_label = ctk.CTkLabel(mt_row, textvariable=self.thread_count_var, width=30)
        self.thread_label.pack(side="left", padx=5)

        # Row 3: Action Buttons
        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(15, 0))
        
        self.start_btn = ctk.CTkButton(btn_row, text="▶ START AUTO POST", width=200, height=40,
                                       fg_color="#10b981", hover_color="#059669", command=self.toggle_process, font=("Outfit", 14, "bold"))
        self.start_btn.pack(side="left", padx=5)
        
        self.counter_lbl = ctk.CTkLabel(btn_row, textvariable=self.counter_var, font=("Outfit", 12, "bold"), text_color="#10b981")
        self.counter_lbl.pack(side="left", padx=15)
        
        self.clear_btn = ctk.CTkButton(btn_row, text="↺ Clear Queue", width=120, height=40,
                                       fg_color="#4b5563", command=lambda: self.titles_text.delete("1.0", "end"))
        self.clear_btn.pack(side="left", padx=5)
        
        self.multi_step_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(btn_row, text="Multi-Step (Outline -> Content)", variable=self.multi_step_var).pack(side="right", padx=10)
        
        self.auto_refill_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(btn_row, text="Auto-Refill Titles", variable=self.auto_refill_var).pack(side="right", padx=10)

        # Progress Bar at the bottom of config card
        self.progress_bar = ctk.CTkProgressBar(inner, height=8, fg_color="#27272a", progress_color="#10b981")
        self.progress_bar.pack(fill="x", pady=(15, 0))
        self.progress_bar.set(0)

        # 3. Main Split Area: Queue & Logs
        split_frame = ctk.CTkFrame(self, fg_color="transparent")
        split_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        split_frame.columnconfigure(0, weight=3) # Queue
        split_frame.columnconfigure(1, weight=2) # Logs
        split_frame.rowconfigure(0, weight=1)
        
        # Queue Card
        queue_card = ctk.CTkFrame(split_frame, fg_color="#18181b", corner_radius=15)
        queue_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(queue_card, text="📋 Title Queue (one per line)", font=("Outfit", 12, "bold"), text_color="gray60").pack(pady=5)
        self.titles_text = ctk.CTkTextbox(queue_card, font=("Consolas", 12), fg_color="#09090b")
        self.titles_text.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        # Log Card
        log_card = ctk.CTkFrame(split_frame, fg_color="#18181b", corner_radius=15)
        log_card.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(log_card, text="💻 Logs", font=("Outfit", 12, "bold"), text_color="gray60").pack(pady=5)
        self.console = ctk.CTkTextbox(log_card, font=("Consolas", 11), fg_color="#09090b", text_color="#10b981")
        self.console.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.console.tag_config("info", foreground="#61dafb")
        self.console.tag_config("success", foreground="#98c379")
        self.console.tag_config("error", foreground="#e06c75")
        self.refresh_dest_lists()
        self.toggle_dest_mode() # Initial UI state

    def load_from_config(self, config):
        self.tab_name_var.set(config.get("tab_name", "New Writer"))
        self.topic_var.set(config.get("topic", ""))
        self.titles_text.delete("1.0", "end")
        self.titles_text.insert("1.0", config.get("titles_queue", ""))
        self.dest_mode_var.set(config.get("dest_mode", 0))
        self.sheet_combo.set(config.get("selected_sheet", ""))
        self.wp_combo.set(config.get("selected_wp", ""))
        self.cat_combo.set(config.get("selected_cat", ""))
        self.multi_step_var.set(config.get("multi_step", True))
        self.model_var.set(config.get("model", "gemini-2.0-flash-exp"))
        self.thread_count_var.set(config.get("thread_count", 1))
        self.toggle_dest_mode()
        self.refresh_dest_lists()


    def log(self, msg, tag="info"):
        self.after(0, lambda: self._log(msg, tag))
    
    def _log(self, msg, tag="info"):
        now = datetime.now().strftime("%H:%M:%S")
        self.console.insert("end", f"[{now}] {msg}\n", tag)
        self.console.see("end")

    def start_title_gen(self):
        topic = self.topic_var.get().strip()
        if not topic: return
        self.gen_titles_btn.configure(state="disabled", text="Generating...")
        def run():
            try:
                self.log(f"Generating titles for topic: {topic}...")
                titles = rewrite.auto_generate_titles(topic, model=self.model_var.get())
                if titles:
                    text = "\n".join(titles)
                    self.after(0, lambda: self.titles_text.insert("end", text + "\n"))
                    self.log(f"Added {len(titles)} titles to queue.")
                else:
                    self.log("Failed to generate titles.")
            except Exception as e:
                self.log(f"Error generating titles: {e}")
            finally:
                self.after(0, lambda: self.gen_titles_btn.configure(state="normal", text="Generate Titles"))
        threading.Thread(target=run, daemon=True).start()

    def toggle_dest_mode(self):
        if self.dest_mode_var.get() == 0:
            self.sheet_combo.pack(side="left", padx=5)
            self.wp_combo.pack_forget()
            self.cat_label.pack_forget()
            self.cat_combo.pack_forget()
        else:
            self.sheet_combo.pack_forget()
            self.wp_combo.pack(side="left", padx=5)
            self.cat_label.pack(side="left", padx=5)
            self.cat_combo.pack(side="left", padx=5)

    def refresh_dest_lists(self):
        sheets = self.sheet_manager.list_sheets()
        self.sheet_combo.configure(values=[s['name'] for s in sheets])
        if sheets and not self.sheet_combo.get(): self.sheet_combo.set(sheets[0]['name'])

        sites = self.wp_manager.list_destinations()
        self.wp_combo.configure(values=[s['name'] for s in sites])
        if sites and not self.wp_combo.get(): 
            self.wp_combo.set(sites[0]['name'])
            # Trigger category load for the first site
            self.on_wp_site_selected(sites[0]['name'])
        elif not sites:
            self.wp_combo.set("") # Clear selection if no sites
            self.cat_combo.set("") # Clear categories
            self.cat_combo.configure(values=[])


    def on_wp_site_selected(self, site_name):
        sites = self.wp_manager.list_destinations()
        site = next((s for s in sites if s['name'] == site_name), None)
        if site:
            def load_cats():
                try:
                    cats = self.wp_manager.get_categories(site['id'])
                    self.category_map = {c['name']: c['id'] for c in cats}
                    cat_names = sorted(list(self.category_map.keys()))
                    self.after(0, lambda: self.cat_combo.configure(values=cat_names))
                    if cat_names and not self.cat_combo.get(): self.after(0, lambda: self.cat_combo.set(cat_names[0]))
                except Exception as e: 
                    self.log(f"Error loading categories: {e}")
                    self.after(0, lambda: self.cat_combo.configure(values=[]))
                    self.after(0, lambda: self.cat_combo.set(""))
            threading.Thread(target=load_cats, daemon=True).start()

    def get_dest_config(self):
        if self.dest_mode_var.get() == 0:
            sheets = self.sheet_manager.list_sheets()
            sheet = next((s for s in sheets if s['name'] == self.sheet_combo.get()), None)
            return {"type": "sheet", "config": sheet}
        else:
            sites = self.wp_manager.list_destinations()
            site = next((s for s in sites if s['name'] == self.wp_combo.get()), None)
            cat_id = getattr(self, 'category_map', {}).get(self.cat_combo.get())
            if site:
                conf = site.copy()
                conf['category_id'] = cat_id
                return {"type": "wp", "config": conf}
            return None

    def stop_process(self):
        if self.is_running:
            self.stop_event.set()
            self.is_running = False
            self.start_btn.configure(text="▶ START AUTO POST", fg_color="#10b981")
            self.log("Stopping auto-poster...")

    def toggle_process(self):
        if self.is_running:
            self.stop_process()
        else:
            self.stop_event.clear()
            self.is_running = True
            self.start_btn.configure(text="⏹ STOP AUTO POST", fg_color="#ef4444")
            threading.Thread(target=self.run_process, daemon=True).start()
            threading.Thread(target=self.monitor_queue_loop, daemon=True).start()

    def monitor_queue_loop(self):
        self.log("Auto-Refill Monitor started.")
        while self.is_running and not self.stop_event.is_set():
            try:
                should_refill = False
                should_refill = False
                # Safely check line count
                try:
                    raw_text = self.safe_get_titles_text().strip()
                    lines = [l for l in raw_text.split("\n") if l.strip()]
                    # Refill if less than 3 items left
                    if len(lines) < 3:
                        should_refill = True
                except:
                    pass

                if should_refill:
                    if self.auto_refill_var.get() and not self.is_refilling:
                        self.log("Queue low. Triggering Auto-Refill...", "info")
                        self.is_refilling = True
                        self.perform_auto_refill() # This runs synchronously in this monitor thread
                
                time.sleep(5)
            except Exception as e:
                self.log(f"Monitor error: {e}", "error")
                time.sleep(5)

    def run_process(self):
        self.log("Auto-poster started.")
        self.processed_count = 0 
        self.counter_var.set("0 processed")
        self.progress_bar.set(0)
        
        # Count initial items for progress calculation
        raw_start = self.titles_text.get("1.0", "end").strip()
        lines_start = [l.strip() for l in raw_start.split("\n") if l.strip()]
        total_tasks = len(lines_start)
        
        if total_tasks == 0:
            self.log("No titles to process.")
            self.after(0, self.toggle_process)
            return

        dest_config = self.get_dest_config()
        if not dest_config or not dest_config.get('config'):
             self.log("Invalid destination configuration.", "error")
             self.after(0, self.toggle_process)
             return

        model = self.model_var.get()
        multi_step = self.multi_step_var.get()
        num_threads = self.thread_count_var.get()

        semaphore = threading.Semaphore(num_threads)
        
        def task_wrapper(t):
            try:
                self.process_single_title(t, dest_config, model, multi_step, total_tasks)
            finally:
                semaphore.release()

        # Prepare Executor
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=num_threads)
        try:
            while self.is_running and not self.stop_event.is_set():
                # Wait for a free slot or timeout to check stop_event
                if not semaphore.acquire(timeout=1):
                    continue
                
                title = None
                try:
                    # Thread-Unsafe UI Access Mitigation: Use safe getter
                    with self.queue_lock:
                        raw_text = self.safe_get_titles_text().strip()
                        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                        
                        if lines:
                            title = lines[0]
                            remaining = "\n".join(lines[1:])
                            # Update UI from main thread
                            self.after(0, lambda r=remaining: self._update_queue_ui(r))
                        else:
                             # Queue empty, just wait
                             pass
                except Exception as e:
                    self.log(f"Queue read error: {e}", "error")
                    semaphore.release()
                    time.sleep(1)
                    continue
                
                if not title:
                    semaphore.release()
                    time.sleep(2)
                    
                    # If queue is empty, we decide whether to stop or wait
                    try:
                        auto_refill = self.auto_refill_var.get()
                    except:
                        auto_refill = False
                    
                    if not auto_refill:
                        # Double check if truly empty
                        try:
                            check_text = self.safe_get_titles_text().strip()
                            if not check_text:
                                self.log("Queue empty. Stopping.", "info")
                                break
                        except:
                            pass
                    
                    # If auto_refill is True, we just wait for the monitor thread to fill it up
                    time.sleep(2)
                    continue
                

                
                # Submit task
                executor.submit(task_wrapper, title)
                time.sleep(0.5) # Slight delay between starting threads

        finally:
            executor.shutdown(wait=False)
            self.log("All tasks processed.")
            self.after(0, self.toggle_process)

    def _update_queue_ui(self, remaining_text):
        self.titles_text.delete("1.0", "end")
        self.titles_text.insert("1.0", remaining_text)

    def perform_auto_refill(self):
        try:
            # Gather existing titles in queue to also exclude them
            raw_text = self.safe_get_titles_text().strip()
            current_queue = raw_text.split('\n')
            current_queue = [x.strip() for x in current_queue if x.strip()]
            
            # Combine history and current queue for exclusion
            exclude_set = self.generated_history.union(set(current_queue))
            
            new_titles = self.generate_titles_logic(exclude_titles=exclude_set)
            
            if new_titles:
                 def append_ui(titles):
                     current = self.titles_text.get("1.0", "end").strip()
                     if current:
                         self.titles_text.insert("end", "\n" + "\n".join(titles))
                     else:
                         self.titles_text.insert("end", "\n".join(titles))
                     self.log(f"Auto-refilled {len(titles)} titles.", "success")
                     
                 self.generated_history.update(new_titles)
                 self.after(0, lambda: append_ui(new_titles))
            else:
                 self.log("Auto-refill returned no (new) titles.", "warning")
                 # If we failed to get titles, maybe wait longer before retrying?
                 # But valid logic handles this by sleeping in run_process
        except Exception as e:
            self.log(f"Auto-refill error: {e}", "error")
        finally:
            self.is_refilling = False

    def start_title_gen_async(self):
        self.gen_titles_btn.configure(state="disabled", text="Generating...")
        def run():
            try:
                # Also use history for manual generation
                raw_text = self.safe_get_titles_text().strip()
                current_queue = raw_text.split('\n')
                exclude_set = self.generated_history.union(set(x.strip() for x in current_queue if x.strip()))
                
                titles = self.generate_titles_logic(exclude_titles=exclude_set)
                
                if titles:
                    def append(t):
                        current = self.titles_text.get("1.0", "end").strip()
                        if current:
                            self.titles_text.insert("end", "\n" + "\n".join(t))
                        else:
                            self.titles_text.insert("end", "\n".join(t))
                    
                    self.generated_history.update(titles)
                    self.after(0, lambda: append(titles))
                    self.log(f"Generated {len(titles)} titles.")
                else:
                    self.log("No titles generated.")
            except Exception as e:
                self.log(f"Gen error: {e}", "error")
            finally:
                self.after(0, lambda: self.gen_titles_btn.configure(state="normal", text="✨ Generate Titles"))
        threading.Thread(target=run, daemon=True).start()

    def generate_titles_logic(self, exclude_titles=None):
        # Shared logic for generating titles
        topic = self.topic_var.get().strip()
        model = self.model_var.get()
        if not topic: return []
        
        return rewrite.generate_titles_from_topic(topic, model, exclude_titles=exclude_titles)

    def process_single_title(self, title, dest_config, model, multi_step, total_tasks):
        if self.stop_event.is_set(): return
        
        self.log(f"Processing: {title}")
        try:
            # 1. Generate Content
            content = rewrite.generate_new_content_with_fallback(title, model=model, multi_step=multi_step)
            if content:
                self.log(f"Success! Content size: {len(content)} chars.")
                
                # 2. Select Author
                author_id = rewrite.select_author(title)
                
                # 3. Post to Selected Target
                status = rewrite.aiautotool_pingbackstatus(title, content, author_id, dest_config=dest_config)
                if status in [200, 201]:
                    self.log(f"POSTED SUCCESSFULLY: {title}", "success")
                    # Update Global Stats
                    self.app.stats['processed'] += 1
                    self.app.dashboard_tab.update_stats()
                    self.app.dashboard_tab.add_log(f"New Post Published: {title}", "success")
                    
                    # Update Local Counter & Progress
                    with self.queue_lock:
                        self.processed_count += 1
                        self.after(0, lambda: self.counter_var.set(f"{self.processed_count} processed"))
                        if total_tasks > 0:
                            self.after(0, lambda: self.progress_bar.set(self.processed_count / total_tasks))
                else:
                    self.log(f"Post failed with status {status}: {title}", "error")
            else:
                self.log(f"AI failed to generate content for: {title}", "error")
        except Exception as e:
            self.log(f"Critical error processing {title}: {e}", "error")

class WPManagerTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.wp_manager = get_wp_manager()
        self.selected_id = None
        self.setup_ui()
        self.refresh_wp_list()

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=1); self.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(self, width=200); left.grid(row=0, column=0, sticky="nsew", padx=5)
        self.scroll = ctk.CTkScrollableFrame(left, fg_color="transparent"); self.scroll.pack(fill="both", expand=True)
        ctk.CTkButton(left, text="+ New", command=self.add_new).pack(pady=5)
        
        right = ctk.CTkFrame(self); right.grid(row=0, column=1, sticky="nsew", padx=5)
        self.name_var = tk.StringVar(); self.url_var = tk.StringVar()
        self.user_var = tk.StringVar(); self.pass_var = tk.StringVar()
        self.create_entry(right, "Site Name", self.name_var)
        self.create_entry(right, "URL", self.url_var)
        self.create_entry(right, "User", self.user_var)
        self.create_entry(right, "App Pass", self.pass_var)
        ctk.CTkButton(right, text="Save Site", command=self.save).pack(pady=20)

    def create_entry(self, p, l, v):
        ctk.CTkLabel(p, text=l).pack(pady=(10,0)); ctk.CTkEntry(p, textvariable=v, width=300).pack(pady=5)

    def refresh_wp_list(self):
        for c in self.scroll.winfo_children(): c.destroy()
        for s in self.wp_manager.list_destinations():
            ctk.CTkButton(self.scroll, text=s['name'], fg_color="transparent", command=lambda x=s: self.load(x)).pack(fill="x")

    def add_new(self): self.selected_id = None; self.name_var.set(""); self.url_var.set("https://")
    def load(self, s):
        self.selected_id = s['id']; self.name_var.set(s['name']); self.url_var.set(s['site_url'])
        self.user_var.set(s['username']); self.pass_var.set(s['app_password'])
    def save(self):
        if self.selected_id: self.wp_manager.remove_destination(self.selected_id)
        self.wp_manager.add_destination(self.name_var.get(), self.url_var.get(), self.user_var.get(), self.pass_var.get())
        self.refresh_wp_list(); self.app.refresh_all_crawler_tabs()

class DashboardTab(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.setup_ui()
        
    def setup_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", pady=(20, 30))
        ctk.CTkLabel(header_frame, text="Dashboard Overview", font=("Outfit", 28, "bold"), text_color="white").pack(side="left")
        ctk.CTkLabel(header_frame, text=datetime.now().strftime("%B %d, %Y"), font=("Outfit", 14), text_color="gray70").pack(side="right", anchor="s", pady=5)

        # Stats Cards
        stats_container = ctk.CTkFrame(self, fg_color="transparent")
        stats_container.pack(fill="x", pady=(0, 30))
        
        # Grid layout for cards
        stats_container.grid_columnconfigure(0, weight=1)
        stats_container.grid_columnconfigure(1, weight=1)
        stats_container.grid_columnconfigure(2, weight=1)
        
        self.c1 = self.create_gradient_card(stats_container, 0, "Processed Posts", "0", "#FF9800", "#F44336", "📊")
        self.c2 = self.create_gradient_card(stats_container, 1, "Active Crawlers", "0", "#009688", "#4CAF50", "🚀")
        self.c3 = self.create_gradient_card(stats_container, 2, "Success Rate", "100%", "#3F51B5", "#9C27B0", "✨")

        # Activity Feed
        ctk.CTkLabel(self, text="Activity Feed", font=("Outfit", 18, "bold"), text_color="gray90").pack(anchor="w", pady=(0, 10))
        
        self.log_scroll = ctk.CTkScrollableFrame(self, fg_color="#2b2b2b", corner_radius=10, label_text="")
        self.log_scroll.pack(fill="both", expand=True)

    def create_gradient_card(self, parent, col, title, value, c1, c2, icon):
        # Container for padding
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.grid(row=0, column=col, sticky="nsew", padx=10)
        
        # Gradient Canvas
        card = GradientFrame(container, color1=c1, color2=c2, height=120)
        card.pack(fill="both", expand=True)
        
        # Content inside Canvas (using create_window)
        # Inner frame to hold text with transparent background (simulated)
        # Only CTk labels with bg_color matches the gradient approx or transparent if supported?
        # CTk doesn't support 'transparent' bg on Canvas well.
        # So we place standard tk Labels or use canvas text.
        
        card.create_text(20, 30, text=title, font=("Outfit", 14), fill="white", anchor="w")
        val_id = card.create_text(20, 70, text=value, font=("Outfit", 36, "bold"), fill="white", anchor="w")
        card.create_text(parent.winfo_width()-40, 60, text=icon, font=("Arial", 40), fill="white", anchor="e") # Icon placeholder
        
        # Store update method
        card.val_id = val_id
        return card

    def update_stats(self):
        self.c1.itemconfig(self.c1.val_id, text=str(self.app.stats['processed']))
        
        active_crawlers = 0
        for tab in self.app.task_frames.values():
            if isinstance(tab, CrawlerTab) and tab.is_running:
                active_crawlers += 1
            elif isinstance(tab, AutoWriterTab) and tab.is_running:
                active_crawlers += 1
        self.c2.itemconfig(self.c2.val_id, text=str(active_crawlers))

    def add_log(self, message, type="info"):
        # Icons map
        icons = {"info": "ℹ️", "success": "✅", "error": "⚠️", "warning": "⚠️"}
        colors = {"info": "#2196F3", "success": "#4CAF50", "error": "#F44336", "warning": "#FF9800"}
        
        row = ctk.CTkFrame(self.log_scroll, fg_color="transparent")
        row.pack(fill="x", pady=2)
        
        time_str = datetime.now().strftime("%H:%M")
        
        ctk.CTkLabel(row, text=icons.get(type, "•"), width=30, text_color=colors.get(type, "white")).pack(side="left")
        ctk.CTkLabel(row, text=f"[{time_str}]", text_color="gray60", font=("Consolas", 11)).pack(side="left", padx=5)
        ctk.CTkLabel(row, text=message, text_color="gray90", wraplength=600, justify="left").pack(side="left", padx=5, fill="x", expand=True)

    # Legacy method support
    def log_area(self): return None # Dummy for compatibility? No, better replace usage.

class RewriteApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Rewrite - Premium v1.1.2"); self.geometry("1100x750")
        self.data_dir = os.path.expanduser("~/.airewrite_data")
        if not os.path.exists(self.data_dir): os.makedirs(self.data_dir)
        self.state_file = os.path.join(self.data_dir, "app_state.json")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1) # Main content area
        
        self.task_frames = {} # Map uuid -> (CrawlerTab or AutoWriterTab)
        self.current_frame = None
        self.stats = {"processed": 0, "active": 0, "success_rate": "100%"}
        
        self.setup_sidebar()
        self.setup_main_area()
        self.sheet_manager_tab = SheetManagerTab(self.main_frame, self) # Initialize here
        self.wp_manager_tab = WPManagerTab(self.main_frame, self)
        self.account_manager_tab = AccountTab(self.main_frame, self)
        self.dashboard_tab = DashboardTab(self.main_frame, self)

        self.load_state(); self.show_dashboard()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_sidebar(self):
        # Main Sidebar Frame - mimic the "Glass" look with a dark semi-transparent color if possible, 
        # but for now solid dark #1e1e24 is safer and premium.
        self.sidebar_frame = ctk.CTkFrame(self, width=120, corner_radius=0, fg_color="#18181b") 
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1)
        self.active_nav = ""
        
        logo_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        logo_frame.pack(pady=(30, 30), padx=0)
        # Centered Logo
        # Using an icon or just concise text
        ctk.CTkLabel(logo_frame, text="AIautotool", font=("Arial", 24)).pack() 
        # Or keep text but small
        
        # Navigation Buttons
        self.nav_buttons = {}
        
        self.dashboard_btn = self.create_nav_button("🏠 Dashboard", self.show_dashboard)
        self.sheets_btn = self.create_nav_button("📊 Sheets", self.show_sheets)
        self.wp_btn = self.create_nav_button("🌐 WordPress", self.show_wp)
        self.accounts_btn = self.create_nav_button("👥 Accounts", self.show_accounts)
        
        # Bottom spacer
        ctk.CTkFrame(self.sidebar_frame, fg_color="transparent").pack(expand=True, fill="both")
        
        # Settings/Logout or just empty for now
        ctk.CTkLabel(self.sidebar_frame, text="v1.1.2", font=("Outfit", 10), text_color="gray40").pack(pady=20)

    def create_nav_button(self, text, command):
        # Text format: "Icon Name" e.g. "🏠 Dashboard"
        icon_char = text.split()[0]
        label_text = " ".join(text.split()[1:])
        btn_id = label_text # Dashboard, Sheets, WordPress

        # Container for the button check
        # For the "Glow" effect, we will just use the button itself with corner_radius
        
        # We need a custom frame to hold the vertical layout if we want fine control, 
        # OR just use CTkButton with compound="top"
        
        # New Style:
        # [ Icon ]
        # [ Text ]
        
        # We will wrap it in a frame that handles the "Active" background color
        container = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent", corner_radius=15)
        container.pack(fill="x", pady=8, padx=15)
        
        # Use a label for Icon and Label for Text to control spacing better than a single button
        # Make the whole container clickable
        
        icon_lbl = ctk.CTkLabel(container, text=icon_char, font=("Arial", 28), text_color="gray60")
        icon_lbl.pack(pady=(12, 0))
        
        text_lbl = ctk.CTkLabel(container, text=label_text, font=("Outfit", 12, "bold"), text_color="gray60")
        text_lbl.pack(pady=(2, 12))
        
        # Bind click events
        for w in [container, icon_lbl, text_lbl]:
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>", lambda e: self.on_hover(container, btn_id))
            w.bind("<Leave>", lambda e: self.on_leave(container, btn_id))
            
        self.nav_buttons[btn_id] = {
            "container": container,
            "icon": icon_lbl, 
            "text": text_lbl,
            "id": btn_id
        }
        return container

    def on_hover(self, widget, btn_id):
        if self.active_nav != btn_id:
            widget.configure(fg_color="#27272a") # Slight hover grey

    def on_leave(self, widget, btn_id):
        if self.active_nav != btn_id:
            widget.configure(fg_color="transparent")

    def update_sidebar_selection(self, active_id):
        # Update Nav buttons
        self.active_nav = active_id
        for id, widgets in self.nav_buttons.items():
            container = widgets["container"]
            icon = widgets["icon"]
            lbl = widgets["text"]
            
            if id == active_id:
                container.configure(fg_color="#00BCD4")
                icon.configure(text_color="white")
                lbl.configure(text_color="white")
            else:
                container.configure(fg_color="transparent")
                icon.configure(text_color="gray60")
                lbl.configure(text_color="gray60")
        
        # Update Task tab highlights (Visual feedback in side list)
        # This is now handled by update_sidebar_crawlers which updates the top strip
        self.update_sidebar_crawlers()

    def setup_main_area(self):
        # Top Strip Container
        self.top_strip = ctk.CTkFrame(self, height=50, fg_color="#18181b", corner_radius=0)
        self.top_strip.grid(row=0, column=1, sticky="nsew") 
        self.top_strip.grid_columnconfigure(0, weight=1)
        
        # Horizontal Tabs Scroll Simulation
        self.tabs_strip = ctk.CTkScrollableFrame(self.top_strip, fg_color="transparent", orientation="horizontal", height=45) 
        self.tabs_strip.pack(side="left", fill="both", expand=True, padx=10)
        
        # Quick Actions (+)
        q_actions = ctk.CTkFrame(self.top_strip, fg_color="transparent")
        q_actions.pack(side="right", padx=15)
        
        ctk.CTkButton(q_actions, text="+ Crawler", width=90, height=32, corner_radius=8,
                     command=lambda: self.add_tab("crawler"), fg_color="#1f538d", 
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=5)
                     
        ctk.CTkButton(q_actions, text="+ Writer", width=90, height=32, corner_radius=8,
                     command=lambda: self.add_tab("writer"), fg_color="#106e4a", 
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left", padx=5)

        # Content Area
        self.main_frame = ctk.CTkFrame(self, fg_color="#09090b", corner_radius=0) 
        self.main_frame.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)
        
        def _on_sidebar_click():
            # If we want a separate state for sidebar nav vs task tabs
            pass

    def show_dashboard(self): 
        self.select_frame(self.dashboard_tab)
        self.update_sidebar_selection("Dashboard")
        self.dashboard_tab.update_stats()

    def show_sheets(self): 
        self.select_frame(self.sheet_manager_tab)
        self.update_sidebar_selection("Sheets")

    def show_wp(self): 
        self.select_frame(self.wp_manager_tab)
        self.update_sidebar_selection("WordPress")

    def show_accounts(self):
        self.select_frame(self.account_manager_tab)
        self.update_sidebar_selection("Accounts")
        self.account_manager_tab.refresh_accounts()


    def select_frame(self, f):
        if self.current_frame:
            try:
                if self.current_frame.winfo_exists():
                    self.current_frame.grid_forget()
            except Exception:
                pass
        self.current_frame = f
        if f and f.winfo_exists():
            f.grid(row=0, column=0, sticky="nsew")
        self.update_sidebar_crawlers() # Update top tabs on frame selection

    def add_tab(self, task_type="crawler", initial_url="", config=None):
        import uuid
        uid = config.get("id") if config else str(uuid.uuid4())
        
        if task_type == "crawler" or (config and "url" in config):
            tab = CrawlerTab(self.main_frame, self, initial_url=initial_url, config=config)
        else:
            tab = AutoWriterTab(self.main_frame, self)
            if config: tab.load_from_config(config)
            
        self.task_frames[uid] = tab
        self.update_sidebar_crawlers()
        self.select_frame(tab)
        return uid

    def update_sidebar_crawlers(self):
        # This now updates the TOP strip tabs
        for child in self.tabs_strip.winfo_children():
            child.destroy()
            
        # Add "Dashboard" fake tab? or just highlighting
        
        for uid, tab in self.task_frames.items():
            name = tab.tab_name_var.get() if hasattr(tab, "tab_name_var") else "Task"
            theme_color = "#1f538d" if isinstance(tab, CrawlerTab) else "#10b981"
            
            is_active = (self.current_frame == tab)
            bg = "#27272a" if is_active else "#18181b"
            border_col = theme_color if is_active else "#3f3f46"
            text_col = "white" if is_active else "gray60"
            
            tab_frame = ctk.CTkFrame(self.tabs_strip, fg_color=bg, corner_radius=8, height=36, 
                                     border_width=1, border_color=border_col)
            tab_frame.pack(side="left", padx=4, pady=6)
            
            # Clickable area
            btn = ctk.CTkButton(tab_frame, text=name, 
                               fg_color="transparent", 
                               hover_color="#303036",
                               text_color=text_col,
                               width=100, height=30,
                               anchor="w",
                               command=lambda u=uid: self.select_tab(u))
            btn.pack(side="left", padx=(8, 2), pady=2)
            
            # Type dot
            ctk.CTkLabel(tab_frame, text="●", text_color=theme_color, font=("Arial", 10)).pack(side="left")

            close_btn = ctk.CTkButton(tab_frame, text="×", width=20, height=20, 
                                     fg_color="transparent", hover_color="#ef4444",
                                     text_color="gray50",
                                     command=lambda u=uid: self.remove_tab(u))
            close_btn.pack(side="left", padx=(2, 8))

    def select_tab(self, uid):
        if uid in self.task_frames:
            self.select_frame(self.task_frames[uid])
            self.update_sidebar_crawlers() # Refresh highlights

    def remove_tab(self, uid):
        if uid in self.task_frames:
            tab = self.task_frames[uid]
            if tab.is_running and not messagebox.askyesno("Confirm", "Task is running. Stop and close?"):
                return
            if hasattr(tab, "stop_process"): tab.stop_process()
            if hasattr(tab, "stop_event"): tab.stop_event.set()
            
            if tab == self.current_frame:
                self.show_dashboard()
            tab.destroy()
            del self.task_frames[uid]
            self.update_sidebar_crawlers()
            self.save_state()

    def save_state(self):
        configs = []
        for uid, t in self.task_frames.items():
            if isinstance(t, CrawlerTab):
                configs.append({
                    "id": uid,
                    "type": "crawler",
                    "tab_name": t.tab_name_var.get(),
                    "url": t.url_var.get(), 
                    "include": t.include_var.get(), 
                    "exclude": t.exclude_var.get(), 
                    "prompt": t.system_prompt_var.get(), 
                    "dest_mode": t.dest_mode_var.get(), 
                    "selected_sheet": t.sheet_combo.get(), 
                    "selected_wp": t.wp_combo.get(), 
                    "selected_cat": t.cat_combo.get(),
                    "use_scrapy": t.use_scrapy_var.get(),
                    "title_selector": t.title_selector_var.get(),
                    "content_selector": t.content_selector_var.get(),
                    "pagination_selector": t.pagination_selector_var.get(),
                    "article_selector": t.article_selector_var.get(),
                    "model": t.model_var.get(),
                    "thread_count": t.thread_count_var.get()
                })
            elif isinstance(t, AutoWriterTab):
                configs.append({
                    "id": uid,
                    "type": "writer",
                    "tab_name": t.tab_name_var.get(),
                    "topic": t.topic_var.get(),
                    "titles_queue": t.titles_text.get("1.0", "end"),
                    "dest_mode": t.dest_mode_var.get(),
                    "selected_sheet": t.sheet_combo.get(),
                    "selected_wp": t.wp_combo.get(),
                    "selected_cat": t.cat_combo.get(),
                    "multi_step": t.multi_step_var.get(),
                    "model": t.model_var.get(),
                    "thread_count": t.thread_count_var.get()
                })
        with open(self.state_file, "w") as f: json.dump({"tab_configs": configs}, f, indent=4)

    def load_state(self):
        if not os.path.exists(self.state_file): return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
                if "tab_configs" in data:
                     for c in data["tab_configs"]: 
                         self.add_tab(task_type=c.get("type", "crawler"), config=c)
        except Exception as e:
            print(f"Error loading state: {e}")

    
    def on_close(self):
        """Cleanly close the application by stopping all runnning tasks."""
        print("[Closing App] Stopping all tasks...")
        
        # Stop all running tasks in task frames
        for uid, tab in self.task_frames.items():
            if hasattr(tab, "is_running") and tab.is_running:
                try:
                    if hasattr(tab, "stop_process"):
                        tab.stop_process()
                except Exception as e:
                    print(f"Error stopping tab {uid}: {e}")
        
        # Save app state
        try:
            self.save_state()
        except Exception as e:
            print(f"Error saving state: {e}")
        
        # Small delay to allow threads to receive the stop signal
        # but since they are daemon=True, they will be killed anyway.
        # This just gives them a tiny window to finish a file write if they were just about to.
        self.after(500, self.destroy)

if __name__ == "__main__":
    app = RewriteApp()
    app.mainloop()
