import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import re
from datetime import datetime, timedelta
import subprocess
import threading
import queue
import logging

# --- 설정 상수 ---
# 프롬프트 파일 이름을 이곳에서 관리합니다.
PROMPT_FILENAME = "prompt.txt"

# --- GUI 애플리케이션 ---


class SrtToolApp(tk.Tk):
    @staticmethod
    def _load_prompt(filename):
        """외부 파일에서 프롬프트 내용을 읽어옵니다."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            messagebox.showwarning(
                "프롬프트 파일 없음",
                f"'{filename}' 파일을 찾을 수 없습니다.\n"
                "기본 내장 프롬프트를 사용합니다. 번역 품질이 달라질 수 있습니다.",
            )
            return (
                "You are a helpful assistant that translates subtitles into natural Korean."
            )

    @staticmethod
    def parse_srt_content(content):
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

    @staticmethod
    def shift_time_string(time_str, offset_seconds):
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

    @staticmethod
    def _validate_translation_format(content):
        """번역 결과물의 형식이 올바른지(블록 사이에 빈 줄이 있는지) 검증하고, 오류 라인을 반환합니다."""
        lines = content.strip().split("\n")
        if len(lines) <= 1:
            return True, -1

        for i in range(1, len(lines)):
            if lines[i].strip().isdigit() and lines[i - 1].strip() != "":
                return False, i
        return True, -1

    def __init__(self):
        super().__init__()
        self.title("SRT 자막 처리 도구 v3.0 (Gemini 번역 포함)")
        self.geometry("850x800")

        self.instruction_prompt = SrtToolApp._load_prompt(PROMPT_FILENAME)
        self.ui_elements = []
        self.model_var = tk.StringVar(value="gemini-1.5-pro")

        # 로그 필터 변수
        self.log_filter_vars = {
            "DEBUG": tk.BooleanVar(value=True),
            "INFO": tk.BooleanVar(value=True),
            "WARNING": tk.BooleanVar(value=True),
            "ERROR": tk.BooleanVar(value=True),
            "CONTEXT": tk.BooleanVar(value=True),
        }

        self.setup_logging()

        style = ttk.Style(self)
        style.configure("TButton", padding=6, relief="flat", font=("Helvetica", 10))
        style.configure("TLabel", padding=5, font=("Helvetica", 10))
        style.configure("TEntry", padding=5, font=("Helvetica", 10))
        style.configure("TCheckbutton", padding=5)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(pady=10, padx=10, expand=True, fill="both")

        self.create_splitter_tab()
        self.create_merger_tab()
        self.create_adv_shifter_tab()
        self.create_translator_tab()
        self.create_one_click_tab()

        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progressbar.pack(fill="x", padx=10, pady=5)

        self.create_log_box()

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)

    def setup_logging(self):
        """파일 및 GUI 로깅을 설정합니다."""
        self.log_filename = (
            f"srt_tool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
            handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")],
        )
        self.log("로그 파일이 생성되었습니다: " + self.log_filename, "INFO")

    def log(self, message, level="INFO", is_raw=False):
        """GUI 로그 위젯과 파일에 메시지를 기록합니다."""
        if not hasattr(self, "log_text"):
            return

        log_method = getattr(logging, level.lower(), logging.info)
        log_method(message.strip())

        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] {message}\n"
        if is_raw:
            full_message = message

        self.log_text.insert(tk.END, full_message, (level,))
        self.log_text.see(tk.END)
        self.update_idletasks()

    def process_log_queue(self):
        """백그라운드 스레드의 로그 메시지를 처리합니다."""
        try:
            message, level, is_raw = self.log_queue.get_nowait()
            self.log(message, level, is_raw)
        except queue.Empty:
            pass
        except ValueError: # 이전 버전의 큐 메시지 호환
            try:
                message, is_raw = self.log_queue.get_nowait()
                self.log(message, "INFO", is_raw)
            except (queue.Empty, ValueError):
                pass
        finally:
            self.after(100, self.process_log_queue)

    def lock_ui(self):
        """작업 중 UI를 비활성화합니다."""
        for element in self.ui_elements:
            element.config(state="disabled")

    def unlock_ui(self):
        """작업 완료 후 UI를 활성화합니다."""
        for element in self.ui_elements:
            element.config(state="normal")

    def create_log_box(self):
        log_container = ttk.Frame(self)
        log_container.pack(padx=10, pady=(0, 10), fill="both", expand=True)

        # 컨트롤 프레임 (필터, 클리어 버튼)
        controls_frame = ttk.Frame(log_container)
        controls_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(controls_frame, text="로그 필터:").pack(side="left", padx=(0, 10))
        for level, var in self.log_filter_vars.items():
            cb = ttk.Checkbutton(controls_frame, text=level, variable=var, command=self._update_log_filter)
            cb.pack(side="left")

        clear_button = ttk.Button(controls_frame, text="로그 지우기", command=self._clear_log)
        clear_button.pack(side="right")

        # 로그 텍스트 프레임
        log_text_frame = ttk.LabelFrame(log_container, text="처리 로그", padding=(10, 5))
        log_text_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_text_frame,
            height=18,
            wrap="word",
            state="normal",
            font=("Courier New", 9),
            bg="#f0f0f0",
            fg="black",
        )
        self.log_text.bind("<KeyPress>", lambda e: "break")

        # 태그 설정
        self.log_text.tag_configure("DEBUG", foreground="gray")
        self.log_text.tag_configure("INFO", foreground="black")
        self.log_text.tag_configure("WARNING", foreground="#E69138")
        self.log_text.tag_configure("ERROR", foreground="red", font=("Courier New", 9, "bold"))
        self.log_text.tag_configure("CONTEXT", foreground="#4A86E8")

        scrollbar = ttk.Scrollbar(log_text_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _update_log_filter(self):
        """로그 필터 상태에 따라 태그의 elide 속성을 업데이트합니다."""
        for level, var in self.log_filter_vars.items():
            self.log_text.tag_config(level, elide=not var.get())

    def _clear_log(self):
        """로그 텍스트 박스를 비웁니다."""
        self.log_text.delete(1.0, tk.END)

    def create_splitter_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="1. SRT 분리")
        ttk.Label(
            tab, text="SRT 파일을 텍스트(시간/문장)로 분리합니다.", wraplength=400
        ).pack(pady=(0, 10), anchor="w")
        btn_split = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_split_wrapper
        )
        btn_split.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn_split)

    def create_merger_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="2. SRT 병합")
        ttk.Label(
            tab,
            text="분리된 텍스트 파일들을 다시 SRT 파일로 병합합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        btn_merge = ttk.Button(
            tab, text="분리된 폴더가 있는 폴더 선택", command=self.run_merge_wrapper
        )
        btn_merge.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn_merge)

    def create_adv_shifter_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="3. 시간 일괄 조절")

        ttk.Label(
            tab,
            text="폴더 내 모든 SRT 파일의 자막 시간을 일괄 조절합니다.\n(새로운 '_shifted.srt' 파일로 저장됩니다)",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")

        # 폴더 선택 버튼
        btn_folder = ttk.Button(
            tab,
            text="시간 조절할 SRT 폴더 선택",
            command=lambda: self.adv_shift_folder_var.set(
                filedialog.askdirectory() or self.adv_shift_folder_var.get()
            ),
        )
        btn_folder.pack(pady=5, ipady=5, anchor="w")
        self.adv_shift_folder_var = tk.StringVar()
        entry_folder = ttk.Entry(tab, textvariable=self.adv_shift_folder_var, width=60)
        entry_folder.pack(fill="x", expand=True, anchor="w")

        # 옵션 프레임
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
        ttk.Label(option_frame, text="만큼 조절 (예: 1.5, -30)").pack(
            side="left", padx=(5, 0)
        )

        # 실행 버튼
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
            text="`txtWithSentence` 폴더의 자막들을 Gemini CLI를 이용해 한국어로 번역합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        ttk.Label(
            tab,
            text="경고: 이 작업은 파일을 직접 수정하며, 되돌릴 수 없습니다!",
            foreground="red",
        ).pack(pady=(0, 10), anchor="w")
        model_selection_frame = self._create_model_selection_ui(tab)
        model_selection_frame.pack(pady=5, anchor='w')

        btn_translate = ttk.Button(
            tab,
            text="작업 폴더 선택 ('txtWithSentence' 상위)",
            command=self.run_translation_wrapper,
        )
        btn_translate.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn_translate)

    def _create_model_selection_ui(self, parent_tab):
        """번역 모델 선택 UI를 생성하고 반환합니다."""
        AVAILABLE_MODELS = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.5-pro"]

        model_frame = ttk.Frame(parent_tab)
        ttk.Label(model_frame, text="번역 모델 선택:").pack(side="left", padx=(0, 5))

        model_combo = ttk.Combobox(
            model_frame,
            textvariable=self.model_var,
            values=AVAILABLE_MODELS,
            width=20,
            state="readonly"
        )
        model_combo.pack(side="left")
        self.ui_elements.append(model_combo)

        return model_frame

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

        model_selection_frame = self._create_model_selection_ui(tab)
        model_selection_frame.pack(pady=5, anchor='w')

        btn_oneclick = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_one_click_wrapper
        )
        btn_oneclick.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn_oneclick)

    # --- 코어 로직 실행 함수 ---

    def _split_single_srt(self, srt_path, time_dir, sentence_dir):
        """단일 SRT 파일을 분리합니다."""
        srt_file = os.path.basename(srt_path)
        try:
            self.log_queue.put((f"분리 처리 중: {srt_file}", "DEBUG", False))
            with open(srt_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            blocks = SrtToolApp.parse_srt_content(content)
            base_name = os.path.splitext(srt_file)[0]

            time_file_path = os.path.join(time_dir, f"{base_name}.txt")
            sentence_file_path = os.path.join(sentence_dir, f"{base_name}.txt")

            with open(time_file_path, "w", encoding="utf-8") as tf, open(
                sentence_file_path, "w", encoding="utf-8"
            ) as sf:
                for block in blocks:
                    tf.write(f"{block['number']}\n{block['time']}\n\n")
                    sf.write(f"{block['number']}\n{block['text']}\n\n")
            return True, sentence_file_path
        except Exception as e:
            self.log_queue.put((f"분리 오류 ({srt_file}): {e}", "ERROR", False))
            return False, None

    def _translate_single_file(self, txt_path, primary_model="gemini-1.5-pro"):
        """단일 텍스트 파일을 Gemini를 이용해 번역하고, 형식 검증 및 모델 재시도 로직을 포함합니다."""
        filename = os.path.basename(txt_path)
        self.log_queue.put((f"번역 처리 중: {filename}", "INFO", False))

        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                original_content = f.read()
            if not original_content.strip():
                self.log_queue.put((f"'{filename}' 파일이 비어 있어 건너뜁니다.", "WARNING", False))
                return True
        except Exception as e:
            self.log_queue.put((f"파일 읽기 오류 ({filename}): {e}", "ERROR", False))
            return False

        # --- 모델 순차 시도 로직 ---
        models_to_try = [primary_model]
        if primary_model != "gemini-2.5-pro":
            models_to_try.append("gemini-2.5-pro")

        for model_name in models_to_try:
            self.log_queue.put((f"'{model_name}' 모델로 번역 시도...", "DEBUG", False))

            try:
                full_prompt = f"{self.instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
                command = ["gemini", "-m", model_name]
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )
                stdout, stderr = process.communicate(full_prompt)

                if process.returncode != 0:
                    self.log_queue.put((f"'{model_name}' 모델 실행 실패: {stderr}", "ERROR", False))
                    continue # 다음 모델로 재시도

                lines = stdout.strip().split("\n")
                filtered_lines = [line for line in lines if "Loaded cached credentials." not in line]
                translated_content = "\n".join(filtered_lines)

                is_valid, error_line_idx = SrtToolApp._validate_translation_format(translated_content)
                if is_valid:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(translated_content.strip())
                    self.log_queue.put((f"번역 성공 및 형식 확인: {filename} (모델: {model_name})", "INFO", False))
                    return True
                else:
                    self.log_queue.put((f"'{model_name}' 모델 번역 결과 형식 오류 발생.", "WARNING", False))
                    error_lines = translated_content.strip().split('\n')
                    start = max(0, error_line_idx - 5)
                    end = min(len(error_lines), error_line_idx + 6)

                    context_log = [f"오류 발생 지점 (라인 {error_line_idx + 1}):"]
                    context_log.append("---------- 오류 컨텍스트 시작 ----------")
                    for i in range(start, end):
                        prefix = ">> " if i == error_line_idx else "   "
                        context_log.append(f"   {prefix}{i+1:03d}: {error_lines[i]}")
                    context_log.append("---------- 오류 컨텍스트 종료 ----------")
                    self.log_queue.put(("\n".join(context_log), "CONTEXT", True))

            except FileNotFoundError:
                self.log_queue.put(("\n오류: 'gemini' 명령을 찾을 수 없습니다.\nGemini CLI가 설치되어 있고 시스템 PATH에 등록되어 있는지 확인하세요.", "ERROR", False))
                return False
            except Exception as e:
                self.log_queue.put((f"예상치 못한 번역 오류 ({filename}, 모델: {model_name}): {e}", "ERROR", False))
                continue

        self.log_queue.put((f"번역 최종 실패: 모든 모델({', '.join(models_to_try)}) 시도 후에도 형식이 올바르지 않음. ({filename})", "ERROR", False))
        return False

    def _merge_single_srt(self, time_file_path, sentence_file_path, output_srt_path):
        """단일 자막 파일을 병합합니다."""
        filename = os.path.basename(output_srt_path)
        try:
            self.log_queue.put((f"병합 처리 중: {filename}", "DEBUG", False))
            if not os.path.exists(time_file_path) or not os.path.exists(
                sentence_file_path
            ):
                self.log_queue.put(
                    (f"병합에 필요한 파일이 없습니다. 건너뜁니다.", "WARNING", False)
                )
                return False

            with open(time_file_path, "r", encoding="utf-8") as tf:
                time_content = tf.read().strip().split("\n\n")
            with open(sentence_file_path, "r", encoding="utf-8") as sf:
                sentence_content = sf.read().strip().split("\n\n")

            srt_output = []
            for t_chunk, s_chunk in zip(time_content, sentence_content):
                if not t_chunk or not s_chunk:
                    continue
                t_lines = t_chunk.strip().split("\n")
                s_lines = s_chunk.strip().split("\n")

                if len(t_lines) < 2 or len(s_lines) < 1:
                    continue

                number, time_line = t_lines[0], t_lines[1]
                text_lines = (
                    s_lines[1:]
                    if s_lines[0].isdigit() and s_lines[0] == number
                    else s_lines
                )
                joined_text = "\n".join(text_lines)
                srt_output.append(f"{number}\n{time_line}\n{joined_text}\n")

            with open(output_srt_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_output))
            return True
        except Exception as e:
            self.log_queue.put((f"병합 오류 ({filename}): {e}", "ERROR", False))
            return False

    def _backup_failed_srt(self, srt_path, base_dir):
        """실패한 원본 SRT 파일을 'failed_srt' 폴더에 백업합니다."""
        try:
            failed_dir = os.path.join(base_dir, "failed_srt")
            os.makedirs(failed_dir, exist_ok=True)

            backup_path = os.path.join(failed_dir, os.path.basename(srt_path))
            if os.path.exists(backup_path):
                return

            with open(srt_path, "rb") as f_in, open(backup_path, "wb") as f_out:
                f_out.write(f_in.read())

            self.log_queue.put(
                (f"원본 SRT를 'failed_srt' 폴더에 백업: {os.path.basename(srt_path)}", "WARNING", False)
            )
        except Exception as e:
            self.log_queue.put((f"실패한 SRT 백업 중 오류 발생: {e}", "ERROR", False))

    # --- 래퍼 및 스레드 실행 함수들 ---

    def run_generic_thread(self, target_func, *args):
        """스레드에서 함수를 실행하고 UI를 잠금/해제하는 템플릿입니다."""

        def task_wrapper():
            self.lock_ui()
            try:
                target_func(*args)
            finally:
                self.after(0, self.unlock_ui)

        thread = threading.Thread(target=task_wrapper, daemon=True)
        thread.start()

    def _execute_split_all(self, dir_path):
        """폴더 내 모든 SRT를 분리하는 작업"""
        self.log_queue.put(
            (f"1. 전체 분리 작업 시작... (대상 폴더: {dir_path})", "INFO", False)
        )
        time_dir = os.path.join(dir_path, "txtWithTime")
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        os.makedirs(time_dir, exist_ok=True)
        os.makedirs(sentence_dir, exist_ok=True)

        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("폴더에서 SRT 파일을 찾을 수 없습니다.", "ERROR", False))
            messagebox.showerror("오류", "폴더에서 SRT 파일을 찾을 수 없습니다.")
            return

        total_files = len(srt_files)
        self.progress_var.set(0)
        success_count = 0
        for i, srt_file in enumerate(srt_files, 1):
            srt_path = os.path.join(dir_path, srt_file)
            success, _ = self._split_single_srt(srt_path, time_dir, sentence_dir)
            if success:
                success_count += 1
            else:
                self._backup_failed_srt(srt_path, dir_path)
            self.progress_var.set((i / total_files) * 100)

        self.progress_var.set(0)
        self.log_queue.put(
            (f"총 {total_files}개 중 {success_count}개 파일 분리 완료.", "INFO", False)
        )
        messagebox.showinfo(
            "완료",
            f"총 {total_files}개 중 {success_count}개 파일 분리가 완료되었습니다.",
        )

    def run_split_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(self._execute_split_all, dir_path)

    def _execute_merge_all(self, dir_path):
        """폴더 내 모든 텍스트를 병합하는 작업"""
        self.log_queue.put((f"병합 작업 시작... (대상 폴더: {dir_path})", "INFO", False))
        time_dir = os.path.join(dir_path, "txtWithTime")
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        output_dir = os.path.join(dir_path, "updatedSrt")
        os.makedirs(output_dir, exist_ok=True)

        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("병합할 파일을 찾을 수 없습니다.", "ERROR", False))
            return

        total_files = len(txt_files)
        self.progress_var.set(0)
        success_count = 0
        main_dir = os.path.dirname(time_dir)
        for i, txt_file in enumerate(txt_files, 1):
            base_name = os.path.splitext(txt_file)[0]
            time_path = os.path.join(time_dir, txt_file)
            sentence_path = os.path.join(sentence_dir, txt_file)
            output_path = os.path.join(output_dir, f"{base_name}_updated.srt")
            if self._merge_single_srt(time_path, sentence_path, output_path):
                success_count += 1
            else:
                # 병합 실패 시 원본 SRT 백업
                original_srt_name = f"{base_name}.srt"
                original_srt_path = os.path.join(main_dir, original_srt_name)
                if os.path.exists(original_srt_path):
                    self._backup_failed_srt(original_srt_path, main_dir)
            self.progress_var.set((i / total_files) * 100)

        self.progress_var.set(0)
        self.log_queue.put(
            (f"총 {total_files}개 중 {success_count}개 파일 병합 완료.", "INFO", False)
        )
        messagebox.showinfo(
            "완료",
            f"총 {len(txt_files)}개 중 {success_count}개 파일 병합이 완료되었습니다.",
        )

    def run_merge_wrapper(self):
        dir_path = filedialog.askdirectory(
            title="분리된 폴더가 있는 폴더를 선택하세요 ('txt...' 폴더 상위)"
        )
        if dir_path:
            self.run_generic_thread(self._execute_merge_all, dir_path)

    def _execute_adv_shift(self, dir_path, start_num, offset):
        """폴더 내 모든 SRT 파일의 시간을 일괄 조절하는 작업"""
        self.log_queue.put((f"시간 일괄 조절 시작... (대상 폴더: {dir_path})", "INFO", False))
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("폴더에서 SRT 파일을 찾을 수 없습니다.", "ERROR", False))
            return

        total_files = len(srt_files)
        self.progress_var.set(0)
        success_count = 0
        for i, srt_file in enumerate(srt_files, 1):
            file_path = os.path.join(dir_path, srt_file)
            try:
                self.log_queue.put((f"처리 중: {srt_file}", "DEBUG", False))
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()

                blocks = SrtToolApp.parse_srt_content(content)
                new_srt_content = []
                for block in blocks:
                    new_time = block["time"]
                    if int(block["number"]) >= start_num:
                        start_time, end_time = block["time"].split(" --> ")
                        new_start = SrtToolApp.shift_time_string(start_time, offset)
                        new_end = SrtToolApp.shift_time_string(end_time, offset)
                        new_time = f"{new_start} --> {new_end}"

                    new_srt_content.append(
                        f"{block['number']}\n{new_time}\n{block['text']}\n"
                    )

                base_name, ext = os.path.splitext(srt_file)
                output_path = os.path.join(dir_path, f"{base_name}_shifted{ext}")
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(new_srt_content))
                success_count += 1
            except Exception as e:
                self.log_queue.put((f"오류 ({srt_file}): {e}", "ERROR", False))
                self._backup_failed_srt(file_path, dir_path)
            self.progress_var.set((i / total_files) * 100)

        self.progress_var.set(0)
        self.log_queue.put(
            (f"총 {total_files}개 중 {success_count}개 파일 시간 조절 완료.", "INFO", False)
        )
        messagebox.showinfo(
            "완료",
            f"총 {len(srt_files)}개 중 {success_count}개 파일 시간 조절이 완료되었습니다.",
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

        self.run_generic_thread(self._execute_adv_shift, dir_path, start_num, offset)

    def _execute_translation_all(self, sentence_dir, model_name):
        """폴더 내 모든 파일을 번역"""
        self.log_queue.put(("전체 번역 작업 시작...", "INFO", False))
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("번역할 .txt 파일을 찾을 수 없습니다.", "ERROR", False))
            return

        self.log_queue.put(
            (f"총 {len(txt_files)}개의 파일에 대한 번역을 시작합니다. (주 모델: {model_name})", "INFO", False)
        )
        total_files = len(txt_files)
        self.progress_var.set(0)
        success_count = 0
        main_dir = os.path.dirname(sentence_dir)
        for i, filename in enumerate(txt_files, 1):
            filepath = os.path.join(sentence_dir, filename)
            if self._translate_single_file(filepath, model_name):
                success_count += 1
            else:
                # 번역 실패 시 원본 SRT 백업
                original_srt_name = os.path.splitext(filename)[0] + ".srt"
                original_srt_path = os.path.join(main_dir, original_srt_name)
                if os.path.exists(original_srt_path):
                    self._backup_failed_srt(original_srt_path, main_dir)
            self.progress_var.set((i / total_files) * 100)

        self.progress_var.set(0)
        self.log_queue.put(
            (f"총 {total_files}개 중 {success_count}개 파일 번역 완료.", "INFO", False)
        )
        messagebox.showinfo(
            "완료",
            f"총 {len(txt_files)}개 중 {success_count}개 파일 번역이 완료되었습니다.",
        )

    def run_translation_wrapper(self):
        dir_path = filedialog.askdirectory(
            title="번역할 폴더('txtWithSentence' 상위)를 선택하세요"
        )
        if not dir_path:
            return
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        if not os.path.isdir(sentence_dir):
            messagebox.showerror(
                "폴더 없음", f"`txtWithSentence` 폴더를 찾을 수 없습니다."
            )
            return
        self.run_generic_thread(self._execute_translation_all, sentence_dir, self.model_var.get())

    def _execute_one_click_workflow(self, dir_path, model_name):
        """원클릭 워크플로우: SRT 파일 단위로 분리-번역-병합을 순차 실행"""
        self.log_queue.put((f"🚀 원클릭 전체 작업을 시작합니다. (주 모델: {model_name})", "INFO", False))

        time_dir = os.path.join(dir_path, "txtWithTime")
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        output_dir = os.path.join(dir_path, "updatedSrt")
        os.makedirs(time_dir, exist_ok=True)
        os.makedirs(sentence_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        srt_files = sorted(
            [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        )
        if not srt_files:
            messagebox.showwarning("파일 없음", "선택한 폴더에 SRT 파일이 없습니다.")
            return

        total_files = len(srt_files)
        self.progress_var.set(0)
        success_count = 0

        for i, srt_file in enumerate(srt_files, 1):
            self.log_queue.put(
                (f"\n[{i}/{total_files}] '{srt_file}' 작업 시작...", "INFO", False)
            )
            self.progress_var.set((i / total_files) * 95) # 95% for processing, 5% for finalization
            srt_path = os.path.join(dir_path, srt_file)
            base_name = os.path.splitext(srt_file)[0]

            # 1. 분리
            split_success, sentence_file_path = self._split_single_srt(
                srt_path, time_dir, sentence_dir
            )
            if not split_success:
                self._backup_failed_srt(srt_path, dir_path)
                continue

            # 2. 번역
            if not self._translate_single_file(sentence_file_path, model_name):
                self._backup_failed_srt(srt_path, dir_path)
                continue

            # 3. 병합
            time_file_path = os.path.join(time_dir, f"{base_name}.txt")
            output_srt_path = os.path.join(output_dir, f"{base_name}_updated.srt")
            if not self._merge_single_srt(
                time_file_path, sentence_file_path, output_srt_path
            ):
                self._backup_failed_srt(srt_path, dir_path)
                continue

            self.log_queue.put((f"✅ '{srt_file}' 작업 완료.", "INFO", False))
            success_count += 1

        self.progress_var.set(100)
        self.log_queue.put(
            (
                f"\n✅ 모든 작업이 완료되었습니다! (성공: {success_count}/{total_files})",
                "INFO",
                False,
            )
        )
        messagebox.showinfo(
            "작업 완료",
            f"모든 작업이 완료되었습니다.\n(성공: {success_count}/{total_files})",
        )
        self.progress_var.set(0)

    def run_one_click_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(self._execute_one_click_workflow, dir_path, self.model_var.get())


if __name__ == "__main__":
    app = SrtToolApp()
    app.mainloop()
