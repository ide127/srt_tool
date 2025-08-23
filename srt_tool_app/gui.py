import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading
import queue
import logging
import json
from datetime import datetime
from srt_tool_app import utils, core, config

class SrtToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SRT 자막 처리 도구 v5.0 (Policy-Driven)")
        self.geometry("950x850")

        self.policy_widgets = {}
        self.project_data = config.DEFAULT_PROJECT_DATA.copy()
        self.instruction_prompt = ""

        self.ui_elements = []
        self.log_filter_vars = {
            "DEBUG": tk.BooleanVar(value=True), "INFO": tk.BooleanVar(value=True),
            "WARNING": tk.BooleanVar(value=True), "ERROR": tk.BooleanVar(value=True),
            "CONTEXT": tk.BooleanVar(value=True),
        }

        self.setup_logging()
        self.setup_ui()
        self.generate_prompt()

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)

    def setup_ui(self):
        style = ttk.Style(self)
        style.configure("TButton", padding=6, relief="flat", font=("Helvetica", 10))
        style.configure("TLabel", padding=5, font=("Helvetica", 10))
        style.configure("TEntry", padding=5, font=("Helvetica", 10))
        style.configure("TCheckbutton", padding=5)
        style.configure("Accent.TButton", foreground="white", background="#0078D7")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        self.create_splitter_tab()
        self.create_merger_tab()
        self.create_adv_shifter_tab()
        self.create_project_settings_tab()
        self.create_dynamic_translation_tab("5. 자막 번역 (Gemini)", self.run_translation_wrapper)
        self.create_dynamic_translation_tab("6. 원클릭 전체 작업", self.run_one_click_wrapper)

        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progressbar.pack(fill="x", padx=10, pady=5)
        self.create_log_box()

    def create_dynamic_translation_tab(self, tab_name, command_func):
        # ... (implementation is correct from previous step)
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=tab_name)
        main_pane = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        config_frame = ttk.LabelFrame(main_pane, text="번역 정책 설정", padding=10)
        main_pane.add(config_frame, weight=1)
        for key, policy in config.APP_POLICIES.items():
            if policy["type"] == "boolean":
                var = tk.BooleanVar(value=policy["default"])
                cb = ttk.Checkbutton(config_frame, text=policy["label"], variable=var, command=self.generate_prompt)
                cb.pack(anchor="w", padx=5, pady=2)
                self.policy_widgets[key] = var
        ttk.Separator(config_frame, orient=tk.HORIZONTAL).pack(fill='x', pady=10)
        for key, policy in config.PROMPT_POLICIES.items():
            if policy["type"] == "boolean":
                var = tk.BooleanVar(value=policy["default"])
                cb = ttk.Checkbutton(config_frame, text=policy["label"], variable=var, command=self.generate_prompt)
                cb.pack(anchor="w", padx=5, pady=2)
                self.policy_widgets[key] = var
            elif policy["type"] == "choice":
                ttk.Label(config_frame, text=policy["label"]).pack(anchor="w", padx=5, pady=(5,0))
                var = tk.StringVar(value=policy["default"])
                combo = ttk.Combobox(config_frame, textvariable=var, values=list(policy["options"].keys()), state="readonly")
                combo.pack(anchor="w", fill="x", padx=5, pady=2)
                combo.bind("<<ComboboxSelected>>", self.generate_prompt)
                self.policy_widgets[key] = var
        ttk.Label(config_frame, text="직접 프롬프트 추가:").pack(anchor="w", padx=5, pady=(10,0))
        self.direct_prompt_input = tk.Text(config_frame, height=4, wrap="word")
        self.direct_prompt_input.pack(anchor="w", fill="x", expand=True, padx=5, pady=2)
        self.direct_prompt_input.bind("<KeyRelease>", self.generate_prompt)
        action_pane = ttk.Frame(main_pane)
        main_pane.add(action_pane, weight=1)
        preview_frame = ttk.LabelFrame(action_pane, text="생성된 프롬프트 미리보기", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.prompt_preview_text = tk.Text(preview_frame, height=10, wrap="word", state="disabled", bg="#f0f0f0")
        self.prompt_preview_text.pack(fill=tk.BOTH, expand=True)
        profile_action_frame = ttk.Frame(action_pane)
        profile_action_frame.pack(fill='x', expand=True, pady=(10,0))
        save_btn = ttk.Button(profile_action_frame, text="정책 프로필 저장", command=self._save_profile)
        save_btn.pack(side="left", expand=True, fill='x', padx=(0,5))
        self.ui_elements.append(save_btn)
        load_btn = ttk.Button(profile_action_frame, text="프로필 불러오기", command=self._load_profile)
        load_btn.pack(side="left", expand=True, fill='x')
        self.ui_elements.append(load_btn)
        action_text = "SRT 폴더 선택 (원클릭)" if "원클릭" in tab_name else "작업 폴더 선택 (번역)"
        btn = ttk.Button(action_pane, text=action_text, command=command_func, style="Accent.TButton")
        btn.pack(pady=10, ipady=8, fill='x')
        self.ui_elements.append(btn)

    def generate_prompt(self, event=None):
        # ... (implementation is correct from previous step)
        prompt_parts = [config.BASE_PROMPT]
        for key, policy in config.PROMPT_POLICIES.items():
            widget_var = self.policy_widgets.get(key)
            if not widget_var: continue
            if policy["type"] == "boolean" and widget_var.get():
                prompt_parts.append(policy["prompt_text"])
            elif policy["type"] == "choice":
                selection = widget_var.get()
                if selection: prompt_parts.append(policy["options"][selection])
        if self.project_data["characters"] or self.project_data["glossary"]:
            prompt_parts.append("\n9. 통일성 있는 번역을 위해서, 고유명사를 어떻게 번역해야 하는지 알려줄게.\n")
            if self.project_data["characters"]:
                char_list = "\n".join([f"{c['source']} -> {c['target']}" for c in self.project_data["characters"]])
                prompt_parts.append(f"등장인물 (Characters)\n{char_list}")
            if self.project_data["glossary"]:
                gloss_list = "\n".join([f"{g['source']} -> {g['target']}" for g in self.project_data["glossary"]])
                prompt_parts.append(f"\n기타 용어 (Glossary)\n{gloss_list}")
        if hasattr(self, 'direct_prompt_input'):
            direct_input = self.direct_prompt_input.get("1.0", tk.END).strip()
            if direct_input:
                prompt_parts.append("\n[추가 지시사항]\n" + direct_input)
        final_prompt = "\n\n".join(prompt_parts)
        self.instruction_prompt = final_prompt
        if hasattr(self, 'prompt_preview_text'):
            self.prompt_preview_text.config(state="normal")
            self.prompt_preview_text.delete("1.0", tk.END)
            self.prompt_preview_text.insert("1.0", final_prompt)
            self.prompt_preview_text.config(state="disabled")

    def setup_logging(self):
        # ... (same as before)
        self.log_filename = f"srt_tool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S", handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")])
        self.log("로그 파일이 생성되었습니다: " + self.log_filename, "INFO")
    def log(self, message, level="INFO", is_raw=False):
        # ... (same as before)
        if not hasattr(self, "log_text"): return
        log_method = getattr(logging, level.lower(), logging.info)
        log_method(message.strip())
        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}\n"
        if is_raw: full_message = message
        self.log_text.insert(tk.END, full_message, (level,))
        self.log_text.see(tk.END)
        self.update_idletasks()
    def process_log_queue(self):
        # ... (same as before)
        try:
            message, level, is_raw = self.log_queue.get_nowait()
            self.log(message, level, is_raw)
        except queue.Empty: pass
        finally: self.after(100, self.process_log_queue)
    def lock_ui(self):
        # ... (same as before)
        for element in self.ui_elements:
            try: element.config(state="disabled")
            except tk.TclError: pass
    def unlock_ui(self):
        # ... (same as before)
        for element in self.ui_elements:
            try: element.config(state="normal")
            except tk.TclError: pass
    def create_log_box(self):
        # ... (same as before)
        log_container = ttk.Frame(self)
        log_container.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        controls_frame = ttk.Frame(log_container)
        controls_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(controls_frame, text="로그 필터:").pack(side="left", padx=(0, 10))
        for level, var in self.log_filter_vars.items():
            cb = ttk.Checkbutton(controls_frame, text=level, variable=var, command=self._update_log_filter)
            cb.pack(side="left")
        clear_button = ttk.Button(controls_frame, text="로그 지우기", command=self._clear_log)
        clear_button.pack(side="right")
        log_text_frame = ttk.LabelFrame(log_container, text="처리 로그", padding=(10, 5))
        log_text_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_text_frame, height=18, wrap="word", state="normal", font=("Courier New", 9), bg="#f0f0f0", fg="black")
        self.log_text.bind("<KeyPress>", lambda e: "break")
        tags = ["DEBUG", "INFO", "WARNING", "ERROR", "CONTEXT"]
        colors = {"DEBUG": "gray", "INFO": "black", "WARNING": "#E69138", "ERROR": "red", "CONTEXT": "#4A86E8"}
        for tag in tags: self.log_text.tag_configure(tag, foreground=colors[tag])
        self.log_text.tag_configure("ERROR", font=("Courier New", 9, "bold"))
        scrollbar = ttk.Scrollbar(log_text_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    def _update_log_filter(self):
        # ... (same as before)
        for level, var in self.log_filter_vars.items():
            self.log_text.tag_config(level, elide=not var.get())
    def _clear_log(self):
        # ... (same as before)
        self.log_text.delete(1.0, tk.END)
    def create_splitter_tab(self):
        # ... (same as before)
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="1. SRT 분리")
        ttk.Label(tab, text="SRT 파일을 텍스트(시간/문장)로 분리합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        btn = ttk.Button(tab, text="SRT 파일이 있는 폴더 선택", command=self.run_split_wrapper)
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)
    def create_merger_tab(self):
        # ... (same as before, but with the app policy checkbox)
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="2. SRT 병합")
        ttk.Label(tab, text="분리된 텍스트 파일들을 다시 SRT 파일로 병합합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        policy = config.APP_POLICIES["split_multi_line"]
        var = tk.BooleanVar(value=policy["default"])
        cb = ttk.Checkbutton(tab, text=policy["label"], variable=var)
        cb.pack(anchor="w", pady=5)
        self.policy_widgets["split_multi_line"] = var
        self.ui_elements.append(cb)
        btn = ttk.Button(tab, text="분리된 폴더가 있는 폴더 선택", command=self.run_merge_wrapper)
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)
    def create_adv_shifter_tab(self):
        # ... (same as before)
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="3. 시간 일괄 조절")
        ttk.Label(tab, text="폴더 내 모든 SRT 파일의 자막 시간을 일괄 조절합니다.\n('timeShiftedSrt' 폴더에 저장됩니다)", wraplength=400).pack(pady=(0, 10), anchor="w")
        btn_folder = ttk.Button(tab, text="시간 조절할 SRT 폴더 선택", command=lambda: self.adv_shift_folder_var.set(filedialog.askdirectory() or self.adv_shift_folder_var.get()))
        btn_folder.pack(pady=5, ipady=5, anchor="w")
        self.adv_shift_folder_var = tk.StringVar()
        entry_folder = ttk.Entry(tab, textvariable=self.adv_shift_folder_var, width=60)
        entry_folder.pack(fill="x", expand=True, anchor="w")
        option_frame = ttk.Frame(tab)
        option_frame.pack(pady=10, fill="x", expand=True, anchor="w")
        ttk.Label(option_frame, text="자막 번호").pack(side="left", padx=(0, 5))
        self.adv_shift_start_num_entry = ttk.Entry(option_frame, width=8)
        self.adv_shift_start_num_entry.insert(0, "1")
        self.adv_shift_start_num_entry.pack(side="left")
        ttk.Label(option_frame, text="부터").pack(side="left", padx=(0, 15))
        ttk.Label(option_frame, text="시간(초)을").pack(side="left", padx=(0, 5))
        self.adv_shift_seconds_entry = ttk.Entry(option_frame, width=8)
        self.adv_shift_seconds_entry.insert(0, "-3600")
        self.adv_shift_seconds_entry.pack(side="left")
        ttk.Label(option_frame, text="만큼 조절 (예: 1.5, -30)").pack(side="left", padx=(5, 0))
        btn_execute = ttk.Button(tab, text="선택한 폴더에 시간 조절 실행", command=self.run_adv_shift_wrapper)
        btn_execute.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend([btn_folder, entry_folder, self.adv_shift_start_num_entry, self.adv_shift_seconds_entry, btn_execute])
    def create_project_settings_tab(self):
        # ... (same as before)
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="4. 용어/인물 관리")
        main_pane = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        char_frame = ttk.LabelFrame(main_pane, text="등장인물 이름", padding=10)
        main_pane.add(char_frame, weight=1)
        self.char_tree = self._create_treeview(char_frame, ("원어", "번역"))
        self._populate_treeview(self.char_tree, self.project_data["characters"])
        self._create_treeview_controls(char_frame, self.char_tree, "characters")
        gloss_frame = ttk.LabelFrame(main_pane, text="기타 용어", padding=10)
        main_pane.add(gloss_frame, weight=1)
        self.gloss_tree = self._create_treeview(gloss_frame, ("원어", "번역"))
        self._populate_treeview(self.gloss_tree, self.project_data["glossary"])
        self._create_treeview_controls(gloss_frame, self.gloss_tree, "glossary")
    def _create_treeview(self, parent, columns):
        # ... (same as before)
        tree = ttk.Treeview(parent, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150, anchor="w")
        tree.pack(fill="both", expand=True)
        tree.bind("<Double-1>", self._on_treeview_double_click)
        return tree
    def _populate_treeview(self, tree, data):
        # ... (same as before)
        for item in tree.get_children(): tree.delete(item)
        for item in data: tree.insert("", "end", values=(item["source"], item["target"]))
    def _create_treeview_controls(self, parent, tree, data_key):
        # ... (same as before)
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill="x", pady=(5,0))
        add_btn = ttk.Button(controls_frame, text="추가", command=lambda: self._add_treeview_item(tree, data_key))
        add_btn.pack(side="left")
        remove_btn = ttk.Button(controls_frame, text="삭제", command=lambda: self._remove_treeview_item(tree, data_key))
        remove_btn.pack(side="left", padx=5)
    def _add_treeview_item(self, tree, data_key):
        # ... (same as before)
        new_item_values = ("새 항목", "New Item")
        self.project_data[data_key].append({"source": new_item_values[0], "target": new_item_values[1]})
        new_item_id = tree.insert("", "end", values=new_item_values)
        tree.selection_set(new_item_id)
        tree.focus(new_item_id)
        self._edit_treeview_item(new_item_id, tree, is_new=True)
    def _remove_treeview_item(self, tree, data_key):
        # ... (same as before)
        selected_item_ids = tree.selection()
        if not selected_item_ids: return
        indices_to_delete = sorted([tree.index(item_id) for item_id in selected_item_ids], reverse=True)
        for index in indices_to_delete:
            del self.project_data[data_key][index]
        for item_id in selected_item_ids:
            tree.delete(item_id)
        self.generate_prompt()
    def _on_treeview_double_click(self, event):
        # ... (same as before)
        item_id = event.widget.identify_row(event.y)
        if item_id: self._edit_treeview_item(item_id, event.widget)
    def _edit_treeview_item(self, item_id, tree, is_new=False):
        # ... (same as before)
        edit_window = tk.Toplevel(self)
        edit_window.title("항목 편집")
        item_values = tree.item(item_id, "values")
        source_var = tk.StringVar(value=item_values[0])
        target_var = tk.StringVar(value=item_values[1])
        ttk.Label(edit_window, text="원어:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        source_entry = ttk.Entry(edit_window, textvariable=source_var, width=40)
        source_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(edit_window, text="번역:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        target_entry = ttk.Entry(edit_window, textvariable=target_var, width=40)
        target_entry.grid(row=1, column=1, padx=5, pady=5)
        def save_changes():
            new_values = (source_var.get(), target_var.get())
            tree.item(item_id, values=new_values)
            selected_index = tree.index(item_id)
            data_key = "characters" if tree == self.char_tree else "glossary"
            self.project_data[data_key][selected_index] = {"source": new_values[0], "target": new_values[1]}
            self.generate_prompt()
            edit_window.destroy()
        def cancel_changes():
            if is_new: self._remove_treeview_item(tree, "characters" if tree == self.char_tree else "glossary")
            edit_window.destroy()
        btn_frame = ttk.Frame(edit_window)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        save_button = ttk.Button(btn_frame, text="저장", command=save_changes)
        save_button.pack(side="left", padx=5)
        cancel_button = ttk.Button(btn_frame, text="취소", command=cancel_changes)
        cancel_button.pack(side="left", padx=5)
        edit_window.protocol("WM_DELETE_WINDOW", cancel_changes)
        edit_window.transient(self)
        edit_window.grab_set()
        source_entry.focus_set()
        self.wait_window(edit_window)
    def _save_profile(self):
        # ... (same as before)
        profile_data = {"policies": {}, "project_data": self.project_data}
        for key, var in self.policy_widgets.items():
            profile_data["policies"][key] = var.get()
        filepath = filedialog.asksaveasfilename(initialdir="profiles", title="프로필 저장", filetypes=(("JSON files", "*.json"), ("All files", "*.*")), defaultextension=".json")
        if not filepath: return
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=4)
            self.log(f"프로필을 '{os.path.basename(filepath)}'에 저장했습니다.", "INFO")
        except Exception as e:
            messagebox.showerror("저장 오류", f"프로필을 저장하는 중 오류가 발생했습니다: {e}")
    def _load_profile(self):
        # ... (same as before)
        filepath = filedialog.askopenfilename(initialdir="profiles", title="프로필 불러오기", filetypes=(("JSON files", "*.json"), ("All files", "*.*")))
        if not filepath: return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            for key, value in profile_data.get("policies", {}).items():
                if key in self.policy_widgets:
                    self.policy_widgets[key].set(value)
            self.project_data = profile_data.get("project_data", config.DEFAULT_PROJECT_DATA.copy())
            self._populate_treeview(self.char_tree, self.project_data["characters"])
            self._populate_treeview(self.gloss_tree, self.project_data["glossary"])
            self.generate_prompt()
            self.log(f"'{os.path.basename(filepath)}' 프로필을 불러왔습니다.", "INFO")
        except Exception as e:
            messagebox.showerror("불러오기 오류", f"프로필을 불러오는 중 오류가 발생했습니다: {e}")

    def run_generic_thread(self, target_func, *args):
        thread = threading.Thread(target=lambda: self._task_wrapper(target_func, *args), daemon=True)
        thread.start()
    def _task_wrapper(self, target_func, *args):
        self.lock_ui()
        try: target_func(*args)
        finally: self.after(0, self.unlock_ui)
    def run_split_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path: self.run_generic_thread(self._execute_split_all, dir_path)
    def _execute_split_all(self, dir_path):
        self.log("1. 전체 분리 작업 시작...", "INFO")
        time_dir, sentence_dir = os.path.join(dir_path, "txtWithTime"), os.path.join(dir_path, "txtWithSentence")
        os.makedirs(time_dir, exist_ok=True); os.makedirs(sentence_dir, exist_ok=True)
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log("폴더에서 SRT 파일을 찾을 수 없습니다.", "ERROR"); messagebox.showerror("오류", "폴더에서 SRT 파일을 찾을 수 없습니다."); return
        total_files, success_count = len(srt_files), 0
        self.progress_var.set(0)
        for i, srt_file in enumerate(srt_files, 1):
            srt_path = os.path.join(dir_path, srt_file)
            success, _ = core._split_single_srt(srt_path, time_dir, sentence_dir, self.log_queue)
            if success: success_count += 1
            else: core._backup_failed_srt(srt_path, dir_path, self.log_queue)
            self.progress_var.set((i / total_files) * 100)
        self.progress_var.set(0)
        self.log(f"총 {total_files}개 중 {success_count}개 파일 분리 완료.", "INFO")
        messagebox.showinfo("완료", f"총 {total_files}개 파일 분리가 완료되었습니다.")
    def run_merge_wrapper(self):
        dir_path = filedialog.askdirectory(title="분리된 폴더가 있는 폴더를 선택하세요 ('txt...' 폴더 상위)")
        if dir_path: self.run_generic_thread(self._execute_merge_all, dir_path)
    def _execute_merge_all(self, dir_path):
        self.log("병합 작업 시작...", "INFO")
        time_dir, sentence_dir, output_dir = os.path.join(dir_path, "txtWithTime"), os.path.join(dir_path, "txtWithSentence"), os.path.join(dir_path, "updatedSrt")
        os.makedirs(output_dir, exist_ok=True)
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log("병합할 파일을 찾을 수 없습니다.", "ERROR"); return
        total_files, success_count = len(txt_files), 0
        self.progress_var.set(0)
        split_policy = self.policy_widgets.get("split_multi_line").get()
        for i, txt_file in enumerate(txt_files, 1):
            base_name, time_path, sentence_path, output_path = os.path.splitext(txt_file)[0], os.path.join(time_dir, txt_file), os.path.join(sentence_dir, txt_file), os.path.join(output_dir, f"{os.path.splitext(txt_file)[0]}_updated.srt")
            if core._merge_single_srt(time_path, sentence_path, output_path, self.log_queue, split_policy):
                success_count += 1
            else:
                original_srt_path = os.path.join(dir_path, f"{base_name}.srt")
                if os.path.exists(original_srt_path): core._backup_failed_srt(original_srt_path, dir_path, self.log_queue)
            self.progress_var.set((i / total_files) * 100)
        self.progress_var.set(0)
        self.log(f"총 {total_files}개 중 {success_count}개 파일 병합 완료.", "INFO")
        messagebox.showinfo("완료", f"총 {total_files}개 파일 병합이 완료되었습니다.")
    def run_adv_shift_wrapper(self):
        dir_path = self.adv_shift_folder_var.get()
        if not dir_path or not os.path.isdir(dir_path): messagebox.showerror("입력 오류", "유효한 폴더를 선택하세요."); return
        try:
            start_num, offset = int(self.adv_shift_start_num_entry.get()), float(self.adv_shift_seconds_entry.get())
        except ValueError: messagebox.showerror("입력 오류", "자막 번호와 시간(초)에 유효한 숫자를 입력하세요."); return
        self.run_generic_thread(self._execute_adv_shift, dir_path, start_num, offset)
    def _execute_adv_shift(self, dir_path, start_num, offset):
        self.log("시간 일괄 조절 시작...", "INFO")
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files: self.log("폴더에서 SRT 파일을 찾을 수 없습니다.", "ERROR"); return
        total_files, success_count = len(srt_files), 0
        self.progress_var.set(0)
        for i, srt_file in enumerate(srt_files, 1):
            file_path = os.path.join(dir_path, srt_file)
            try:
                self.log(f"처리 중: {srt_file}", "DEBUG")
                with open(file_path, "r", encoding="utf-8-sig") as f: content = f.read()
                blocks = utils.parse_srt_content(content)
                new_srt_content = [f"{b['number']}\n{utils.shift_time_string(b['time'].split(' --> ')[0], offset)} --> {utils.shift_time_string(b['time'].split(' --> ')[1], offset)}\n{b['text']}\n" if int(b['number']) >= start_num else f"{b['number']}\n{b['time']}\n{b['text']}\n" for b in blocks]
                output_dir = os.path.join(dir_path, "timeShiftedSrt")
                os.makedirs(output_dir, exist_ok=True)
                with open(os.path.join(output_dir, srt_file), "w", encoding="utf-8") as f: f.write("".join(new_srt_content))
                success_count += 1
            except Exception as e:
                self.log(f"오류 ({srt_file}): {e}", "ERROR"); core._backup_failed_srt(file_path, dir_path, self.log_queue)
            self.progress_var.set((i / total_files) * 100)
        self.progress_var.set(0)
        self.log(f"총 {total_files}개 중 {success_count}개 파일 시간 조절 완료. 'timeShiftedSrt' 폴더를 확인하세요.", "INFO")
        messagebox.showinfo("완료", f"총 {total_files}개 파일 시간 조절이 완료되었습니다.")
    def run_translation_wrapper(self):
        dir_path = filedialog.askdirectory(title="번역할 폴더('txtWithSentence' 상위)를 선택하세요")
        if not dir_path: return
        self.generate_prompt()
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        if not os.path.isdir(sentence_dir): messagebox.showerror("폴더 없음", f"`txtWithSentence` 폴더를 찾을 수 없습니다."); return
        self.run_generic_thread(self._execute_translation_all, sentence_dir)
    def _execute_translation_all(self, sentence_dir):
        self.log("전체 번역 작업 시작...", "INFO")
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files: self.log("번역할 .txt 파일을 찾을 수 없습니다.", "ERROR"); return
        self.log(f"총 {len(txt_files)}개의 파일에 대한 번역을 시작합니다.", "INFO")
        total_files, success_count = len(txt_files), 0
        self.progress_var.set(0)
        for i, filename in enumerate(txt_files, 1):
            filepath = os.path.join(sentence_dir, filename)
            if core._translate_single_file(filepath, self.instruction_prompt, self.log_queue):
                success_count += 1
            else:
                original_srt_path = os.path.join(os.path.dirname(sentence_dir), f"{os.path.splitext(filename)[0]}.srt")
                if os.path.exists(original_srt_path): core._backup_failed_srt(original_srt_path, os.path.dirname(sentence_dir), self.log_queue)
            self.progress_var.set((i / total_files) * 100)
        self.progress_var.set(0)
        self.log(f"총 {total_files}개 중 {success_count}개 파일 번역 완료.", "INFO")
        messagebox.showinfo("완료", f"총 {total_files}개 파일 번역이 완료되었습니다.")
    def run_one_click_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if not dir_path: return
        self.generate_prompt()
        self.run_generic_thread(self._execute_one_click_workflow, dir_path)
    def _execute_one_click_workflow(self, dir_path):
        self.log("🚀 원클릭 전체 작업을 시작합니다.", "INFO")
        time_dir, sentence_dir, output_dir = os.path.join(dir_path, "txtWithTime"), os.path.join(dir_path, "txtWithSentence"), os.path.join(dir_path, "updatedSrt")
        os.makedirs(time_dir, exist_ok=True); os.makedirs(sentence_dir, exist_ok=True); os.makedirs(output_dir, exist_ok=True)
        srt_files = sorted([f for f in os.listdir(dir_path) if f.lower().endswith(".srt")])
        if not srt_files: messagebox.showwarning("파일 없음", "선택한 폴더에 SRT 파일이 없습니다."); return
        total_files, success_count = len(srt_files), 0
        self.progress_var.set(0)
        split_policy = self.policy_widgets.get("split_multi_line").get()
        for i, srt_file in enumerate(srt_files, 1):
            self.log(f"\n[{i}/{total_files}] '{srt_file}' 작업 시작...", "INFO")
            self.progress_var.set((i / total_files) * 95)
            srt_path, base_name = os.path.join(dir_path, srt_file), os.path.splitext(srt_file)[0]
            split_success, sentence_file_path = core._split_single_srt(srt_path, time_dir, sentence_dir, self.log_queue)
            if not split_success: core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            if not core._translate_single_file(sentence_file_path, self.instruction_prompt, self.log_queue): core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            time_file_path, output_srt_path = os.path.join(time_dir, f"{base_name}.txt"), os.path.join(output_dir, f"{base_name}_updated.srt")
            if not core._merge_single_srt(time_file_path, sentence_file_path, output_srt_path, self.log_queue, split_policy): core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            self.log(f"✅ '{srt_file}' 작업 완료.", "INFO"); success_count += 1
        self.progress_var.set(100)
        self.log(f"\n✅ 모든 작업이 완료되었습니다! (성공: {success_count}/{total_files})", "INFO")
        messagebox.showinfo("작업 완료", f"모든 작업이 완료되었습니다.\n(성공: {success_count}/{total_files})")
        self.progress_var.set(0)
