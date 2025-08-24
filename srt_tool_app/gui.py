import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import threading
import queue
import logging
from datetime import datetime
from srt_tool_app import utils, core
import ttkbootstrap as tb

class SrtToolApp(tb.Window):
    def __init__(self):
        super().__init__(themename="litera")
        self.title("SRT 자막 처리 도구 v6.1 (File-Based)")
        self.geometry("950x850")

        self.instruction_prompt = ""
        self.policy_var = tk.StringVar()
        self.split_multi_line_var = tk.BooleanVar(value=True)

        self.ui_elements = []
        self.log_filter_vars = {
            "DEBUG": tk.BooleanVar(value=True), "INFO": tk.BooleanVar(value=True),
            "WARNING": tk.BooleanVar(value=True), "ERROR": tk.BooleanVar(value=True),
            "CONTEXT": tk.BooleanVar(value=True),
        }

        self.setup_logging()
        self.setup_ui()

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)

    def setup_ui(self):
        self.notebook = tb.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        self.create_splitter_tab()
        self.create_merger_tab()
        self.create_adv_shifter_tab()
        self.create_translation_tab()
        self.create_one_click_tab()

        self.progress_var = tk.DoubleVar()
        self.progressbar = tb.Progressbar(self, variable=self.progress_var, maximum=100, mode='determinate')
        self.progressbar.pack(fill="x", padx=10, pady=5)
        self.create_log_box()

    def create_splitter_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="1. SRT 분리")
        tb.Label(tab, text="SRT 파일을 텍스트(시간/문장)로 분리합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        btn = tb.Button(tab, text="SRT 파일이 있는 폴더 선택", command=self.run_split_wrapper, bootstyle="primary-outline")
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_merger_tab(self):
        tab = tb.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="2. SRT 병합")
        tb.Label(tab, text="분리된 텍스트 파일들을 다시 SRT 파일로 병합합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        cb = tb.Checkbutton(tab, text="두 줄 이상 자막 자동 분리 (시간 비례 분배)", variable=self.split_multi_line_var, bootstyle="primary")
        cb.pack(anchor="w", pady=5)
        self.ui_elements.append(cb)
        btn = tb.Button(tab, text="분리된 폴더가 있는 폴더 선택", command=self.run_merge_wrapper, bootstyle="primary-outline")
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_adv_shifter_tab(self):
        tab = tb.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="3. 시간 일괄 조절")
        tb.Label(tab, text="폴더 내 모든 SRT 파일의 자막 시간을 일괄 조절합니다.\n('timeShiftedSrt' 폴더에 저장됩니다)", wraplength=400).pack(pady=(0, 10), anchor="w")
        btn_folder = tb.Button(tab, text="시간 조절할 SRT 폴더 선택", command=lambda: self.adv_shift_folder_var.set(filedialog.askdirectory() or self.adv_shift_folder_var.get()), bootstyle="secondary")
        btn_folder.pack(pady=5, ipady=5, anchor="w")
        self.adv_shift_folder_var = tk.StringVar()
        entry_folder = tb.Entry(tab, textvariable=self.adv_shift_folder_var)
        entry_folder.pack(fill="x", expand=True, anchor="w")
        option_frame = tb.Frame(tab)
        option_frame.pack(pady=10, fill="x", expand=True, anchor="w")
        tb.Label(option_frame, text="자막 번호").pack(side="left", padx=(0, 5))
        self.adv_shift_start_num_entry = tb.Entry(option_frame, width=8)
        self.adv_shift_start_num_entry.insert(0, "1")
        self.adv_shift_start_num_entry.pack(side="left")
        tb.Label(option_frame, text="부터").pack(side="left", padx=(0, 15))
        tb.Label(option_frame, text="시간(초)을").pack(side="left", padx=(0, 5))
        self.adv_shift_seconds_entry = tb.Entry(option_frame, width=8)
        self.adv_shift_seconds_entry.insert(0, "-3600")
        self.adv_shift_seconds_entry.pack(side="left")
        tb.Label(option_frame, text="만큼 조절 (예: 1.5, -30)").pack(side="left", padx=(5, 0))
        btn_execute = tb.Button(tab, text="선택한 폴더에 시간 조절 실행", command=self.run_adv_shift_wrapper, bootstyle="primary")
        btn_execute.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend([btn_folder, entry_folder, self.adv_shift_start_num_entry, self.adv_shift_seconds_entry, btn_execute])

    def create_translation_tab(self):
        tab = tb.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="4. 자막 번역 (Gemini)")
        tb.Label(tab, text="`txtWithSentence` 폴더의 자막들을 Gemini CLI를 이용해 한국어로 번역합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        self._create_policy_selection_ui(tab).pack(pady=5, anchor='w')
        tb.Label(tab, text="경고: 이 작업은 파일을 직접 수정하며, 되돌릴 수 없습니다!", foreground="red").pack(pady=(0, 10), anchor="w")
        btn = tb.Button(tab, text="작업 폴더 선택 ('txtWithSentence' 상위)", command=self.run_translation_wrapper, bootstyle="primary")
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_one_click_tab(self):
        tab = tb.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="5. 원클릭 전체 작업")
        tb.Label(tab, text="폴더를 선택하면 각 SRT 파일에 대해 [분리 → 번역 → 병합] 전 과정을 자동으로 처리합니다.", wraplength=400).pack(pady=(0, 10), anchor="w")
        self._create_policy_selection_ui(tab).pack(pady=5, anchor='w')
        tb.Label(tab, text="참고: 시간 조절이 필요하면 '3. 시간 일괄 조절' 탭에서 미리 실행하세요.", foreground="blue").pack(pady=(0, 10), anchor="w")
        btn = tb.Button(tab, text="SRT 파일이 있는 폴더 선택", command=self.run_one_click_wrapper, bootstyle="primary")
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def _create_policy_selection_ui(self, parent_tab):
        policy_frame = tb.Frame(parent_tab)
        tb.Label(policy_frame, text="번역 프롬프트 선택:").pack(side="left", padx=(0, 5))
        try:
            policies = [f for f in os.listdir("prompts") if f.endswith(".txt")]
            if not policies: policies = ["'prompts' 폴더 없음"]
        except FileNotFoundError:
            policies = ["'prompts' 폴더 없음"]
        policy_combo = tb.Combobox(policy_frame, textvariable=self.policy_var, values=policies, width=30, state="readonly")
        policy_combo.pack(side="left")
        if policies and "없음" not in policies[0]:
            self.policy_var.set(policies[0])
        self.ui_elements.append(policy_combo)
        return policy_frame

    def setup_logging(self):
        self.log_filename = f"srt_tool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(level=logging.DEBUG, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S", handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")])
        self.log("로그 파일이 생성되었습니다: " + self.log_filename, "INFO")
    def log(self, message, level="INFO", is_raw=False):
        if not hasattr(self, "log_text"): return
        log_method = getattr(logging, level.lower(), logging.info)
        log_method(message.strip())
        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}\n"
        if is_raw: full_message = message
        self.log_text.insert(tk.END, full_message, (level,))
        self.log_text.see(tk.END)
        self.update_idletasks()
    def process_log_queue(self):
        try:
            message, level, is_raw = self.log_queue.get_nowait()
            self.log(message, level, is_raw)
        except queue.Empty: pass
        finally: self.after(100, self.process_log_queue)
    def lock_ui(self):
        for element in self.ui_elements:
            try: element.config(state="disabled")
            except tk.TclError: pass
    def unlock_ui(self):
        for element in self.ui_elements:
            try: element.config(state="normal")
            except tk.TclError: pass
    def create_log_box(self):
        log_container = tb.Frame(self)
        log_container.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        controls_frame = tb.Frame(log_container)
        controls_frame.pack(fill="x", pady=(0, 5))
        tb.Label(controls_frame, text="로그 필터:").pack(side="left", padx=(0, 10))
        for level, var in self.log_filter_vars.items():
            cb = tb.Checkbutton(controls_frame, text=level, variable=var, command=self._update_log_filter, bootstyle="primary-round-toggle")
            cb.pack(side="left", padx=3)
        clear_button = tb.Button(controls_frame, text="로그 지우기", command=self._clear_log, bootstyle="danger-outline")
        clear_button.pack(side="right")
        log_text_frame = tb.LabelFrame(log_container, text="처리 로그", padding=10)
        log_text_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_text_frame, height=18, wrap="word", state="normal", font=("Courier New", 9), bg="#f0f0f0", fg="black")
        self.log_text.bind("<KeyPress>", lambda e: "break")
        tags = ["DEBUG", "INFO", "WARNING", "ERROR", "CONTEXT"]
        colors = {"DEBUG": "gray", "INFO": "black", "WARNING": "#E69138", "ERROR": "red", "CONTEXT": "#4A86E8"}
        for tag in tags: self.log_text.tag_configure(tag, foreground=colors[tag])
        self.log_text.tag_configure("ERROR", font=("Courier New", 9, "bold"))
        scrollbar = tb.Scrollbar(log_text_frame, command=self.log_text.yview, bootstyle="round")
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    def _update_log_filter(self):
        for level, var in self.log_filter_vars.items():
            self.log_text.tag_config(level, elide=not var.get())
    def _clear_log(self):
        self.log_text.delete(1.0, tk.END)
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
        for i, txt_file in enumerate(txt_files, 1):
            base_name = os.path.splitext(txt_file)[0]
            time_path, sentence_path, output_path = os.path.join(time_dir, txt_file), os.path.join(sentence_dir, txt_file), os.path.join(output_dir, f"{base_name}_updated.srt")
            if core._merge_single_srt(time_path, sentence_path, output_path, self.log_queue, self.split_multi_line_var.get()):
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
    def _load_selected_prompt(self):
        selected_policy = self.policy_var.get()
        if not selected_policy or "없음" in selected_policy:
            messagebox.showerror("오류", "유효한 번역 프롬프트를 선택하세요.")
            return False
        self.instruction_prompt = utils._load_prompt(os.path.join("prompts", selected_policy))
        return True
    def run_translation_wrapper(self):
        if not self._load_selected_prompt(): return
        dir_path = filedialog.askdirectory(title="번역할 폴더('txtWithSentence' 상위)를 선택하세요")
        if not dir_path: return
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
        if not self._load_selected_prompt(): return
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if not dir_path: return
        self.run_generic_thread(self._execute_one_click_workflow, dir_path)
    def _execute_one_click_workflow(self, dir_path):
        self.log("🚀 원클릭 전체 작업을 시작합니다.", "INFO")
        time_dir, sentence_dir, output_dir = os.path.join(dir_path, "txtWithTime"), os.path.join(dir_path, "txtWithSentence"), os.path.join(dir_path, "updatedSrt")
        os.makedirs(time_dir, exist_ok=True); os.makedirs(sentence_dir, exist_ok=True); os.makedirs(output_dir, exist_ok=True)
        srt_files = sorted([f for f in os.listdir(dir_path) if f.lower().endswith(".srt")])
        if not srt_files: messagebox.showwarning("파일 없음", "선택한 폴더에 SRT 파일이 없습니다."); return
        total_files, success_count = len(srt_files), 0
        self.progress_var.set(0)
        for i, srt_file in enumerate(srt_files, 1):
            self.log(f"\n[{i}/{total_files}] '{srt_file}' 작업 시작...", "INFO")
            self.progress_var.set((i / total_files) * 95)
            srt_path, base_name = os.path.join(dir_path, srt_file), os.path.splitext(srt_file)[0]
            split_success, sentence_file_path = core._split_single_srt(srt_path, time_dir, sentence_dir, self.log_queue)
            if not split_success: core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            if not core._translate_single_file(sentence_file_path, self.instruction_prompt, self.log_queue): core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            time_file_path, output_srt_path = os.path.join(time_dir, f"{base_name}.txt"), os.path.join(output_dir, f"{base_name}_updated.srt")
            if not core._merge_single_srt(time_file_path, sentence_file_path, output_srt_path, self.log_queue, self.split_multi_line_var.get()): core._backup_failed_srt(srt_path, dir_path, self.log_queue); continue
            self.log(f"✅ '{srt_file}' 작업 완료.", "INFO"); success_count += 1
        self.progress_var.set(100)
        self.log(f"\n✅ 모든 작업이 완료되었습니다! (성공: {success_count}/{total_files})", "INFO")
        messagebox.showinfo("작업 완료", f"모든 작업이 완료되었습니다.\n(성공: {success_count}/{total_files})")
        self.progress_var.set(0)
