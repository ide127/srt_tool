import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import re
from datetime import datetime, timedelta
import subprocess
import threading
import queue
import logging
import shutil
from typing import List, Dict, Tuple, Optional


# --- 기본 설정 클래스 ---
class CONFIG:
    """애플리케이션의 주요 설정을 관리하는 클래스"""

    PROMPT_FILENAME: str = "prompt.txt"
    BASE_MODEL: str = "gemini-2.5-flash"
    PRO_MODEL: str = "gemini-2.5-pro"
    LOG_LEVELS: List[str] = ["DEBUG", "INFO", "WARNING", "ERROR"]

    # 생성될 폴더 이름
    TIME_DIR_NAME: str = "txtWithTime"
    SENTENCE_DIR_NAME: str = "txtWithSentence"
    UPDATED_SRT_DIR_NAME: str = "updatedSrt"
    FAILED_SRT_DIR_NAME: str = "failed_srt"


# --- 핵심 로직 ---


def _load_prompt(filename: str) -> str:
    """외부 파일에서 프롬프트 내용을 읽어옵니다."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # 파일이 없을 경우 경고 메시지를 한 번만 표시하기 위해 print 사용
        print(f"WARNING: '{filename}' 파일을 찾을 수 없어 기본 프롬프트를 사용합니다.")
        return (
            "You are a helpful assistant that translates subtitles into natural Korean."
        )


def parse_srt_content(content: str) -> List[Dict[str, str]]:
    """SRT 파일 내용을 파싱하여 블록 리스트로 반환합니다."""
    blocks = []
    time_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
    )
    content_chunks = content.strip().split("\n\n")
    block_counter = 1
    for chunk in content_chunks:
        lines = chunk.strip().split("\n")
        if not lines or not lines[0]:
            continue
        time_line, time_line_index = None, -1
        for i, line in enumerate(lines):
            if time_pattern.search(line):
                time_line, time_line_index = line, i
                break
        if time_line:
            number_part = lines[:time_line_index]
            text_part = lines[time_line_index + 1 :]
            number_str = "\n".join(number_part).strip()
            if not number_str or not number_str.isdigit():
                number_str = str(block_counter)
            blocks.append(
                {
                    "number": number_str,
                    "time": time_line.strip(),
                    "text": "\n".join(text_part).strip(),
                }
            )
            block_counter += 1
    return blocks


def shift_time_string(time_str: str, offset_seconds: float) -> str:
    """시간 문자열을 주어진 초만큼 이동시킵니다."""
    is_comma = "," in time_str
    time_format = "%H:%M:%S.%f"
    try:
        dt_obj = datetime.strptime(time_str.strip().replace(",", "."), time_format)
    except ValueError:
        return time_str.strip()
    delta = timedelta(seconds=offset_seconds)
    new_dt_obj = dt_obj + delta
    if new_dt_obj < datetime.strptime("00:00:00.000", time_format):
        new_dt_obj = datetime.strptime("00:00:00.000", time_format)
    new_time_str = new_dt_obj.strftime(time_format)[:-3]
    return new_time_str.replace(".", ",") if is_comma else new_time_str


def _validate_translation_format(content: str) -> Tuple[bool, int]:
    """
    번역 결과물의 형식을 검증합니다.
    Returns: Tuple[bool, int]: (형식 유효 여부, 오류 발생 라인 인덱스)
    """
    lines = content.strip().split("\n")
    if len(lines) <= 1:
        return True, -1
    for i in range(1, len(lines)):
        if lines[i].strip().isdigit() and lines[i - 1].strip() != "":
            return False, i
    return True, -1


# --- GUI 애플리케이션 ---
class SrtToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SRT 자막 처리 도구 v4.1 (Gemini 번역 포함)")
        self.geometry("950x800")

        self.instruction_prompt = _load_prompt(CONFIG.PROMPT_FILENAME)
        self.ui_elements = []
        self.all_logs: List[Dict[str, str]] = []

        self.setup_logging()
        self.setup_styles()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        self.create_splitter_tab()
        self.create_merger_tab()
        self.create_adv_shifter_tab()
        self.create_translator_tab()
        self.create_one_click_tab()

        self.create_log_box()
        self.create_status_bar()

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)
        self.log("INFO", f"애플리케이션 시작. 프롬프트: '{CONFIG.PROMPT_FILENAME}'")
        if "helpful assistant" in self.instruction_prompt:
            self.log(
                "WARNING",
                f"'{CONFIG.PROMPT_FILENAME}' 파일을 찾을 수 없어 기본 프롬프트를 사용합니다.",
            )

    def setup_styles(self):
        style = ttk.Style(self)
        style.configure("TButton", padding=6, relief="flat", font=("Helvetica", 10))
        style.configure("TLabel", padding=5, font=("Helvetica", 10))
        style.configure("TEntry", padding=5, font=("Helvetica", 10))
        style.configure("TCheckbutton", padding=5)

    def setup_logging(self):
        self.log_filename = (
            f"srt_tool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")],
        )

    def log(self, level: str, message: str, details: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "timestamp": timestamp,
            "level": level,
            "message": message,
            "details": details,
        }
        self.all_logs.append(log_entry)
        logging.log(logging.getLevelName(level), f"{message} {details}".strip())

        if hasattr(self, "log_filter_var"):  # UI가 생성되었는지 확인
            current_filter = self.log_filter_var.get()
            if CONFIG.LOG_LEVELS.index(level) >= CONFIG.LOG_LEVELS.index(
                current_filter
            ):
                item_id = self.log_tree.insert(
                    "", "end", values=(timestamp, level, message)
                )
                self.log_tree.yview_moveto(1)
                self.log_tree.see(item_id)
                self.log_tree.tag_configure(
                    level, foreground=self.get_level_color(level)
                )
                self.log_tree.item(item_id, tags=(level,))
        self.update_idletasks()

    def get_level_color(self, level: str) -> str:
        return {
            "INFO": "black",
            "DEBUG": "grey",
            "WARNING": "orange",
            "ERROR": "red",
        }.get(level, "black")

    def process_log_queue(self):
        try:
            level, message, details = self.log_queue.get_nowait()
            self.log(level, message, details)
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_log_queue)

    def lock_ui(self, status_message: str = "작업 중..."):
        self.status_var.set(status_message)
        for element in self.ui_elements:
            try:
                element.config(state="disabled")
            except tk.TclError:
                pass  # 이미 파괴된 위젯일 경우 무시

    def unlock_ui(self):
        self.status_var.set("준비")
        for element in self.ui_elements:
            try:
                element.config(state="normal")
            except tk.TclError:
                pass

    def create_status_bar(self):
        self.status_var = tk.StringVar()
        self.status_var.set("준비")
        status_bar = ttk.Label(
            self, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", padding=5
        )
        status_bar.pack(side="bottom", fill="x")

    def create_log_box(self):
        log_frame = ttk.LabelFrame(self, text="처리 로그", padding=(10, 5))
        log_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)

        filter_frame = ttk.Frame(log_frame)
        filter_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(filter_frame, text="로그 레벨 필터:").pack(side="left")
        self.log_filter_var = tk.StringVar(value="INFO")
        log_filter_menu = ttk.Combobox(
            filter_frame,
            textvariable=self.log_filter_var,
            values=CONFIG.LOG_LEVELS,
            state="readonly",
            width=10,
        )
        log_filter_menu.pack(side="left", padx=5)
        log_filter_menu.bind("<<ComboboxSelected>>", self.refresh_log_display)

        columns = ("timestamp", "level", "message")
        self.log_tree = ttk.Treeview(log_frame, columns=columns, show="headings")
        self.log_tree.heading("timestamp", text="시간", anchor="w")
        self.log_tree.heading("level", text="레벨", anchor="w")
        self.log_tree.heading("message", text="메시지", anchor="w")
        self.log_tree.column("timestamp", width=80, stretch=False)
        self.log_tree.column("level", width=80, stretch=False)
        self.log_tree.column("message", width=600)

        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_tree.yview
        )
        self.log_tree.configure(yscrollcommand=scrollbar.set)

        self.log_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.log_context_menu = tk.Menu(self, tearoff=0)
        self.log_context_menu.add_command(
            label="선택 항목 복사", command=self.copy_log_selection
        )
        self.log_tree.bind("<Button-3>", self.show_log_context_menu)

    def refresh_log_display(self, event=None):
        for item in self.log_tree.get_children():
            self.log_tree.delete(item)
        filter_level = self.log_filter_var.get()
        filter_index = CONFIG.LOG_LEVELS.index(filter_level)
        for log in self.all_logs:
            if CONFIG.LOG_LEVELS.index(log["level"]) >= filter_index:
                item_id = self.log_tree.insert(
                    "", "end", values=(log["timestamp"], log["level"], log["message"])
                )
                self.log_tree.tag_configure(
                    log["level"], foreground=self.get_level_color(log["level"])
                )
                self.log_tree.item(item_id, tags=(log["level"],))
        self.log_tree.yview_moveto(1)

    def show_log_context_menu(self, event):
        if self.log_tree.focus():
            self.log_context_menu.post(event.x_root, event.y_root)

    def copy_log_selection(self):
        selected_item_id = self.log_tree.focus()
        if not selected_item_id:
            return
        item_values = self.log_tree.item(selected_item_id, "values")
        timestamp, message = item_values[0], item_values[2]
        selected_log = next(
            (
                log
                for log in reversed(self.all_logs)
                if log["timestamp"] == timestamp and log["message"] == message
            ),
            None,
        )
        if selected_log:
            clipboard_text = f"[{selected_log['timestamp']}][{selected_log['level']}] {selected_log['message']}"
            if selected_log["details"]:
                clipboard_text += f"\n--- 상세 정보 ---\n{selected_log['details']}"
            self.clipboard_clear()
            self.clipboard_append(clipboard_text)
            self.log("DEBUG", "클립보드에 로그 복사 완료.")

    # --- 탭 생성 함수들 ---
    def create_splitter_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="1. SRT 분리")
        ttk.Label(
            tab, text="SRT 파일을 텍스트(시간/문장)로 분리합니다.", wraplength=400
        ).pack(pady=(0, 10), anchor="w")
        btn = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_split_wrapper
        )
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_merger_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="2. SRT 병합")
        ttk.Label(
            tab,
            text="분리된 텍스트 파일들을 다시 SRT 파일로 병합합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        btn = ttk.Button(
            tab, text="분리된 폴더가 있는 폴더 선택", command=self.run_merge_wrapper
        )
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_adv_shifter_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="3. 시간 일괄 조절")
        ttk.Label(
            tab,
            text="폴더 내 모든 SRT 파일의 시간을 조절하여 새 파일로 저장합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        folder_frame = ttk.Frame(tab)
        folder_frame.pack(fill="x", expand=True, pady=5)
        self.adv_shift_folder_var = tk.StringVar()
        entry_folder = ttk.Entry(
            folder_frame, textvariable=self.adv_shift_folder_var, width=60
        )
        entry_folder.pack(side="left", fill="x", expand=True)
        btn_folder = ttk.Button(
            folder_frame,
            text="폴더 선택",
            command=lambda: self.adv_shift_folder_var.set(
                filedialog.askdirectory() or self.adv_shift_folder_var.get()
            ),
        )
        btn_folder.pack(side="left", padx=(5, 0))
        option_frame = ttk.Frame(tab)
        option_frame.pack(pady=10, fill="x", expand=True, anchor="w")
        ttk.Label(option_frame, text="자막 번호").pack(side="left")
        self.adv_shift_start_num_entry = ttk.Entry(option_frame, width=8)
        self.adv_shift_start_num_entry.insert(0, "1")
        self.adv_shift_start_num_entry.pack(side="left", padx=(5, 0))
        ttk.Label(option_frame, text="부터").pack(side="left", padx=(5, 15))
        ttk.Label(option_frame, text="시간(초)을").pack(side="left")
        self.adv_shift_seconds_entry = ttk.Entry(option_frame, width=8)
        self.adv_shift_seconds_entry.insert(0, "0")
        self.adv_shift_seconds_entry.pack(side="left", padx=(5, 0))
        ttk.Label(option_frame, text="만큼 조절 (예: 1.5, -3600)").pack(
            side="left", padx=(5, 0)
        )
        btn_execute = ttk.Button(
            tab, text="선택한 폴더에 시간 조절 실행", command=self.run_adv_shift_wrapper
        )
        btn_execute.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend(
            [
                btn_folder,
                entry_folder,
                self.adv_shift_start_num_entry,
                self.adv_shift_seconds_entry,
                btn_execute,
            ]
        )

    def create_translator_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="4. 자막 번역 (Gemini)")
        ttk.Label(
            tab,
            text=f"`{CONFIG.SENTENCE_DIR_NAME}` 폴더의 자막들을 Gemini CLI를 이용해 번역합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        ttk.Label(
            tab,
            text="경고: 이 작업은 파일을 직접 수정하며, 되돌릴 수 없습니다!",
            foreground="red",
        ).pack(pady=(0, 10), anchor="w")
        btn = ttk.Button(
            tab,
            text=f"작업 폴더 선택 ('{CONFIG.SENTENCE_DIR_NAME}' 상위)",
            command=self.run_translation_wrapper,
        )
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    def create_one_click_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="5. 원클릭 전체 작업")
        ttk.Label(
            tab,
            text="폴더를 선택하면 각 SRT 파일에 대해 [분리 → 번역 → 병합] 전 과정을 자동으로 처리합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        ttk.Label(
            tab,
            text="참고: 시간 조절이 필요하면 '3. 시간 일괄 조절' 탭에서 미리 실행하세요.",
            foreground="blue",
        ).pack(pady=(0, 10), anchor="w")
        btn = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_one_click_wrapper
        )
        btn.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn)

    # --- 코어 로직 실행 함수 ---
    def _split_single_srt(
        self, srt_path: str, time_dir: str, sentence_dir: str
    ) -> Tuple[bool, Optional[str]]:
        srt_file = os.path.basename(srt_path)
        try:
            self.log_queue.put(("DEBUG", f"분리 시작: {srt_file}", f"경로: {srt_path}"))
            with open(srt_path, "r", encoding="utf-8-sig") as f:
                content = f.read()
            blocks = parse_srt_content(content)
            base_name = os.path.splitext(srt_file)[0]
            sentence_file_path = os.path.join(sentence_dir, f"{base_name}.txt")
            with open(
                os.path.join(time_dir, f"{base_name}.txt"), "w", encoding="utf-8"
            ) as tf, open(sentence_file_path, "w", encoding="utf-8") as sf:
                for block in blocks:
                    tf.write(f"{block['number']}\n{block['time']}\n\n")
                    sf.write(f"{block['number']}\n{block['text']}\n\n")
            return True, sentence_file_path
        except Exception as e:
            self.log_queue.put(("ERROR", f"분리 오류 발생: {srt_file}", str(e)))
            return False, None

    def _translate_single_file(self, txt_path: str) -> bool:
        filename = os.path.basename(txt_path)
        max_retries = 3
        for attempt in range(max_retries):
            model = CONFIG.BASE_MODEL if attempt == 0 else CONFIG.PRO_MODEL
            msg = (
                f"번역 처리 중: {filename}"
                if attempt == 0
                else f"번역 재시도: {filename}"
            )
            self.log_queue.put(("INFO", msg, f"모델: {model}"))
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                if not original_content.strip():
                    self.log_queue.put(("INFO", f"파일이 비어 있어 건너뜀: {filename}"))
                    return True
                full_prompt = f"{self.instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
                command = ["gemini", "-m", model]
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                stdout, stderr = process.communicate(timeout=120)
                if process.returncode == 0:
                    lines = stdout.strip().split("\n")
                    filtered_lines = [
                        line
                        for line in lines
                        if "Loaded cached credentials." not in line
                    ]
                    translated_content = "\n".join(filtered_lines)
                    is_valid, error_line_idx = _validate_translation_format(
                        translated_content
                    )
                    if is_valid:
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(translated_content.strip())
                        self.log_queue.put(
                            (
                                "INFO",
                                f"번역 성공 및 형식 확인: {filename}",
                                f"사용한 모델: {model}",
                            )
                        )
                        return True
                    else:
                        error_lines = translated_content.strip().split("\n")
                        start, end = max(0, error_line_idx - 5), min(
                            len(error_lines), error_line_idx + 6
                        )
                        context = "\n".join(
                            f"{i+1:03d}: {line}"
                            for i, line in enumerate(error_lines[start:end], start)
                        )
                        self.log_queue.put(
                            (
                                "WARNING",
                                f"번역 형식 오류 감지: {filename}",
                                f"오류 추정 라인: {error_line_idx+1}\n---\n{context}\n---",
                            )
                        )
                else:
                    self.log_queue.put(
                        ("ERROR", f"Gemini CLI 오류: {filename}", stderr)
                    )
                    return False
            except subprocess.TimeoutExpired:
                self.log_queue.put(
                    (
                        "ERROR",
                        f"Gemini 번역 시간 초과: {filename}",
                        "120초 내에 응답이 없습니다.",
                    )
                )
                return False
            except Exception as e:
                self.log_queue.put(("ERROR", f"번역 중 예외 발생: {filename}", str(e)))
                return False
        self.log_queue.put(
            ("ERROR", f"최대 재시도({max_retries}) 초과. 번역 최종 실패: {filename}")
        )
        return False

    def _merge_single_srt(
        self, time_file_path: str, sentence_file_path: str, output_srt_path: str
    ) -> bool:
        filename = os.path.basename(output_srt_path)
        try:
            self.log_queue.put(("DEBUG", f"병합 시작: {filename}"))
            if not os.path.exists(time_file_path) or not os.path.exists(
                sentence_file_path
            ):
                self.log_queue.put(("WARNING", f"병합 필요 파일 없음: {filename}"))
                return False
            with open(time_file_path, "r", encoding="utf-8") as tf:
                time_content = tf.read().strip().split("\n\n")
            with open(sentence_file_path, "r", encoding="utf-8") as sf:
                sentence_content = sf.read().strip().split("\n\n")
            srt_output = []
            for t_chunk, s_chunk in zip(time_content, sentence_content):
                if not t_chunk or not s_chunk:
                    continue
                t_lines, s_lines = t_chunk.strip().split("\n"), s_chunk.strip().split(
                    "\n"
                )
                if len(t_lines) < 2 or len(s_lines) < 1:
                    continue
                number, time_line = t_lines[0], t_lines[1]
                text_lines = (
                    s_lines[1:]
                    if s_lines[0].isdigit() and s_lines[0] == number
                    else s_lines
                )
                # *** SYNTAX ERROR FIX HERE ***
                joined_text = "\n".join(text_lines)
                srt_output.append(f"{number}\n{time_line}\n{joined_text}\n")
            with open(output_srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_output))
            return True
        except Exception as e:
            self.log_queue.put(("ERROR", f"병합 오류: {filename}", str(e)))
            return False

    # --- UI 래퍼 함수들 ---
    def run_generic_thread(
        self, target_func, *args, status_message: str = "작업 중..."
    ):
        def task_wrapper():
            self.lock_ui(status_message)
            try:
                target_func(*args)
            finally:
                self.after(0, self.unlock_ui)

        threading.Thread(target=task_wrapper, daemon=True).start()

    def run_split_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(
                self._execute_split_all, dir_path, status_message="SRT 파일 분리 중..."
            )

    def run_merge_wrapper(self):
        dir_path = filedialog.askdirectory(
            title=f"'{CONFIG.TIME_DIR_NAME}' 등이 있는 폴더를 선택하세요"
        )
        if dir_path:
            self.run_generic_thread(
                self._execute_merge_all, dir_path, status_message="SRT 파일 병합 중..."
            )

    def run_adv_shift_wrapper(self):
        dir_path = self.adv_shift_folder_var.get()
        if not dir_path or not os.path.isdir(dir_path):
            messagebox.showerror("입력 오류", "유효한 폴더를 선택하세요.")
            return
        try:
            start_num = int(self.adv_shift_start_num_entry.get())
            offset = float(self.adv_shift_seconds_entry.get())
        except ValueError:
            messagebox.showerror(
                "입력 오류", "자막 번호와 시간(초)에 유효한 숫자를 입력하세요."
            )
            return
        self.run_generic_thread(
            self._execute_adv_shift,
            dir_path,
            start_num,
            offset,
            status_message="시간 일괄 조절 중...",
        )

    def run_translation_wrapper(self):
        dir_path = filedialog.askdirectory(
            title=f"'{CONFIG.SENTENCE_DIR_NAME}'가 있는 폴더를 선택하세요"
        )
        if dir_path:
            sentence_dir = os.path.join(dir_path, CONFIG.SENTENCE_DIR_NAME)
            if not os.path.isdir(sentence_dir):
                messagebox.showerror(
                    "폴더 없음",
                    f"`{CONFIG.SENTENCE_DIR_NAME}` 폴더를 찾을 수 없습니다.",
                )
                return
            self.run_generic_thread(
                self._execute_translation_all,
                sentence_dir,
                status_message="자막 번역 중...",
            )

    def run_one_click_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(
                self._execute_one_click_workflow,
                dir_path,
                status_message="원클릭 전체 작업 중...",
            )

    # --- 백그라운드 작업 함수들 ---
    def _execute_split_all(self, dir_path: str):
        self.log_queue.put(("INFO", "전체 분리 작업 시작", f"대상: {dir_path}"))
        time_dir = os.path.join(dir_path, CONFIG.TIME_DIR_NAME)
        os.makedirs(time_dir, exist_ok=True)
        sentence_dir = os.path.join(dir_path, CONFIG.SENTENCE_DIR_NAME)
        os.makedirs(sentence_dir, exist_ok=True)
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("WARNING", "분리할 SRT 파일을 찾을 수 없습니다."))
            return

        success_count = 0
        for srt_file in srt_files:
            if self._split_single_srt(
                os.path.join(dir_path, srt_file), time_dir, sentence_dir
            )[0]:
                success_count += 1

        self.log_queue.put(
            ("INFO", f"분리 작업 완료. {success_count}/{len(srt_files)}개 성공.")
        )

    def _execute_merge_all(self, dir_path: str):
        self.log_queue.put(("INFO", "전체 병합 작업 시작", f"대상: {dir_path}"))
        time_dir = os.path.join(dir_path, CONFIG.TIME_DIR_NAME)
        sentence_dir = os.path.join(dir_path, CONFIG.SENTENCE_DIR_NAME)
        output_dir = os.path.join(dir_path, CONFIG.UPDATED_SRT_DIR_NAME)
        os.makedirs(output_dir, exist_ok=True)
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("WARNING", "병합할 파일을 찾을 수 없습니다."))
            return

        success_count = 0
        for txt_file in txt_files:
            base_name = os.path.splitext(txt_file)[0]
            if self._merge_single_srt(
                os.path.join(time_dir, txt_file),
                os.path.join(sentence_dir, txt_file),
                os.path.join(output_dir, f"{base_name}_updated.srt"),
            ):
                success_count += 1

        self.log_queue.put(
            ("INFO", f"병합 작업 완료. {success_count}/{len(txt_files)}개 성공.")
        )

    def _execute_adv_shift(self, dir_path: str, start_num: int, offset: float):
        self.log_queue.put(
            (
                "INFO",
                "시간 일괄 조절 시작",
                f"대상: {dir_path}, 시작번호: {start_num}, 조절값: {offset}초",
            )
        )
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("WARNING", "시간 조절할 SRT 파일을 찾을 수 없습니다."))
            return

        success_count = 0
        for srt_file in srt_files:
            try:
                file_path = os.path.join(dir_path, srt_file)
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    blocks = parse_srt_content(f.read())
                new_srt_content = []
                for block in blocks:
                    new_time = block["time"]
                    if int(block["number"]) >= start_num:
                        start_time, end_time = block["time"].split(" --> ")
                        new_time = f"{shift_time_string(start_time, offset)} --> {shift_time_string(end_time, offset)}"
                    new_srt_content.append(
                        f"{block['number']}\n{new_time}\n{block['text']}\n"
                    )

                base_name, ext = os.path.splitext(srt_file)
                output_path = os.path.join(dir_path, f"{base_name}_shifted{ext}")
                # *** PREVENTIVE FIX HERE ***
                final_content = "\n".join(new_srt_content)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(final_content)
                success_count += 1
                self.log_queue.put(("DEBUG", f"시간 조절 완료: {srt_file}"))
            except Exception as e:
                self.log_queue.put(("ERROR", f"시간 조절 오류: {srt_file}", str(e)))

        self.log_queue.put(
            ("INFO", f"시간 조절 완료. {success_count}/{len(srt_files)}개 성공.")
        )

    def _execute_translation_all(self, sentence_dir: str):
        self.log_queue.put(("INFO", "전체 번역 작업 시작", f"대상: {sentence_dir}"))
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("WARNING", "번역할 파일을 찾을 수 없습니다."))
            return

        success_count = 0
        for filename in txt_files:
            if self._translate_single_file(os.path.join(sentence_dir, filename)):
                success_count += 1

        self.log_queue.put(
            ("INFO", f"번역 작업 완료. {success_count}/{len(txt_files)}개 성공.")
        )

    def _execute_one_click_workflow(self, dir_path: str):
        self.log_queue.put(("INFO", "🚀 원클릭 전체 작업 시작", f"대상: {dir_path}"))
        time_dir = os.path.join(dir_path, CONFIG.TIME_DIR_NAME)
        os.makedirs(time_dir, exist_ok=True)
        sentence_dir = os.path.join(dir_path, CONFIG.SENTENCE_DIR_NAME)
        os.makedirs(sentence_dir, exist_ok=True)
        output_dir = os.path.join(dir_path, CONFIG.UPDATED_SRT_DIR_NAME)
        os.makedirs(output_dir, exist_ok=True)
        failed_dir = os.path.join(dir_path, CONFIG.FAILED_SRT_DIR_NAME)
        os.makedirs(failed_dir, exist_ok=True)

        srt_files = sorted(
            [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        )
        if not srt_files:
            self.log_queue.put(("WARNING", "작업할 SRT 파일이 없습니다."))
            return

        total, success_count = len(srt_files), 0
        for i, srt_file in enumerate(srt_files, 1):
            self.status_var.set(f"원클릭 작업 중... [{i}/{total}] {srt_file}")
            self.log_queue.put(("INFO", f"[{i}/{total}] '{srt_file}' 작업 시작..."))
            srt_path, base_name = (
                os.path.join(dir_path, srt_file),
                os.path.splitext(srt_file)[0],
            )

            # 실패 시 백업을 위한 플래그
            is_failed = False

            split_ok, sentence_path = self._split_single_srt(
                srt_path, time_dir, sentence_dir
            )
            if not split_ok:
                is_failed = True

            if not is_failed:
                if not self._translate_single_file(sentence_path):
                    is_failed = True

            if not is_failed:
                time_path = os.path.join(time_dir, f"{base_name}.txt")
                output_path = os.path.join(output_dir, f"{base_name}_updated.srt")
                if not self._merge_single_srt(time_path, sentence_path, output_path):
                    is_failed = True

            if is_failed:
                self.log_queue.put(
                    ("ERROR", f"'{srt_file}' 처리 실패. 원본을 백업합니다.")
                )
                shutil.copy(srt_path, os.path.join(failed_dir, srt_file))
                continue

            self.log_queue.put(("INFO", f"✅ '{srt_file}' 작업 완료."))
            success_count += 1

        self.log_queue.put(
            ("INFO", f"🎉 모든 작업 완료! (성공: {success_count}/{total})")
        )
        if success_count < total:
            self.log_queue.put(
                (
                    "WARNING",
                    f"일부 파일 실패. '{CONFIG.FAILED_SRT_DIR_NAME}' 폴더를 확인하세요.",
                )
            )


if __name__ == "__main__":
    app = SrtToolApp()
    app.mainloop()
