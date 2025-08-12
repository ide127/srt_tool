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

# --- 핵심 로직 ---


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


def _validate_translation_format(content):
    """번역 결과물의 형식이 올바른지(블록 사이에 빈 줄이 있는지) 검증합니다."""
    lines = content.strip().split("\n")
    if len(lines) <= 1:
        return True  # 내용이 거의 없으면 검증 통과

    # 1번 라인 이후부터, 숫자만 있는 라인 앞에는 반드시 빈 라인이 있어야 함
    for i in range(1, len(lines)):
        # 현재 라인이 번호이고, 이전 라인이 비어있지 않다면 형식 오류
        if lines[i].strip().isdigit() and lines[i - 1].strip() != "":
            return False
    return True


# --- GUI 애플리케이션 ---


class SrtToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SRT 자막 처리 도구 v3.0 (Gemini 번역 포함)")
        self.geometry("850x750")

        self.instruction_prompt = _load_prompt(PROMPT_FILENAME)
        self.ui_elements = []

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
        self.create_adv_shifter_tab()  # 새로 개편된 시간 조절 탭
        self.create_translator_tab()
        self.create_one_click_tab()

        self.create_log_box()

        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)

    def setup_logging(self):
        """파일 및 GUI 로깅을 설정합니다."""
        self.log_filename = (
            f"srt_tool_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(message)s",
            datefmt="%H:%M:%S",
            handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")],
        )
        self.log("로그 파일이 생성되었습니다: " + self.log_filename)

    def log(self, message, is_raw=False):
        """GUI 로그 위젯과 파일에 메시지를 기록합니다."""
        if not hasattr(self, "log_text"):
            return

        self.log_text.config(state="normal")
        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
        if is_raw:
            full_message = message

        self.log_text.insert(tk.END, full_message)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()
        logging.info(message.strip())

    def process_log_queue(self):
        """백그라운드 스레드의 로그 메시지를 처리합니다."""
        try:
            message, is_raw = self.log_queue.get_nowait()
            self.log(message, is_raw)
        except queue.Empty:
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
        log_frame = ttk.LabelFrame(self, text="처리 로그", padding=(10, 5))
        log_frame.pack(padx=10, pady=(0, 10), fill="both", expand=True)
        self.log_text = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            state="disabled",
            font=("Courier New", 9),
            bg="#f0f0f0",
            fg="black",
        )
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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
        btn_translate = ttk.Button(
            tab,
            text="작업 폴더 선택 ('txtWithSentence' 상위)",
            command=self.run_translation_wrapper,
        )
        btn_translate.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.append(btn_translate)

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
            self.log_queue.put((f"  - 분리 처리 중: {srt_file}", False))
            with open(srt_path, "r", encoding="utf-8-sig") as f:
                content = f.read()

            blocks = parse_srt_content(content)
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
            self.log_queue.put((f"  - 분리 오류 ({srt_file}): {e}", False))
            return False, None

    def _translate_single_file(self, txt_path):
        """단일 텍스트 파일을 Gemini를 이용해 번역하고, 형식 검증 및 재시도합니다."""
        filename = os.path.basename(txt_path)
        self.log_queue.put((f"  - 번역 처리 중: {filename}", False))

        max_retries = 3
        retries = 0

        while retries < max_retries:
            if retries > 0:
                self.log_queue.put(
                    (
                        f"    - 번역 형식 오류. 재시도... ({retries}/{max_retries})",
                        False,
                    )
                )

            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    original_content = f.read()

                if not original_content.strip():
                    self.log_queue.put(
                        (f"  - '{filename}' 파일이 비어 있어 건너뜁니다.", False)
                    )
                    return True

                full_prompt = f"{self.instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
                command = ["gemini", "-m", "gemini-1.5-flash"]
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                )

                stdout, stderr = process.communicate(full_prompt)

                if process.returncode == 0:
                    # 불필요한 CLI 메시지 필터링
                    lines = stdout.strip().split("\n")
                    filtered_lines = [
                        line
                        for line in lines
                        if "Loaded cached credentials." not in line
                    ]
                    translated_content = "\n".join(filtered_lines)

                    # 형식 검증
                    if _validate_translation_format(translated_content):
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(translated_content.strip())
                        self.log_queue.put(
                            (f"  - 번역 성공 및 형식 확인: {filename}", False)
                        )
                        return True
                    else:
                        retries += 1
                        continue  # 형식이 틀렸으므로 재시도
                else:
                    self.log_queue.put((f"  - 번역 실패 ({filename}): {stderr}", False))
                    return False

            except FileNotFoundError:
                self.log_queue.put(
                    (
                        "\n오류: 'gemini' 명령을 찾을 수 없습니다.\nGemini CLI가 설치되어 있고 시스템 PATH에 등록되어 있는지 확인하세요.",
                        False,
                    )
                )
                return False
            except Exception as e:
                self.log_queue.put(
                    (f"\n  - 예상치 못한 번역 오류 ({filename}): {e}", False)
                )
                return False

        self.log_queue.put(
            (f"  - 번역 실패: 최대 재시도 횟수({max_retries}) 초과. {filename}", False)
        )
        return False

    def _merge_single_srt(self, time_file_path, sentence_file_path, output_srt_path):
        """단일 자막 파일을 병합합니다."""
        filename = os.path.basename(output_srt_path)
        try:
            self.log_queue.put((f"  - 병합 처리 중: {filename}", False))
            if not os.path.exists(time_file_path) or not os.path.exists(
                sentence_file_path
            ):
                self.log_queue.put(
                    (f"  - 병합에 필요한 파일이 없습니다. 건너뜁니다.", False)
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
            self.log_queue.put((f"  - 병합 오류 ({filename}): {e}", False))
            return False

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
            (f"1. 전체 분리 작업 시작... (대상 폴더: {dir_path})", False)
        )
        time_dir = os.path.join(dir_path, "txtWithTime")
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        os.makedirs(time_dir, exist_ok=True)
        os.makedirs(sentence_dir, exist_ok=True)

        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("오류: 폴더에서 SRT 파일을 찾을 수 없습니다.", False))
            messagebox.showerror("오류", "폴더에서 SRT 파일을 찾을 수 없습니다.")
            return

        success_count = 0
        for srt_file in srt_files:
            srt_path = os.path.join(dir_path, srt_file)
            success, _ = self._split_single_srt(srt_path, time_dir, sentence_dir)
            if success:
                success_count += 1

        self.log_queue.put(
            (f"총 {len(srt_files)}개 중 {success_count}개 파일 분리 완료.", False)
        )
        messagebox.showinfo(
            "완료",
            f"총 {len(srt_files)}개 중 {success_count}개 파일 분리가 완료되었습니다.",
        )

    def run_split_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(self._execute_split_all, dir_path)

    def _execute_merge_all(self, dir_path):
        """폴더 내 모든 텍스트를 병합하는 작업"""
        self.log_queue.put((f"병합 작업 시작... (대상 폴더: {dir_path})", False))
        time_dir = os.path.join(dir_path, "txtWithTime")
        sentence_dir = os.path.join(dir_path, "txtWithSentence")
        output_dir = os.path.join(dir_path, "updatedSrt")
        os.makedirs(output_dir, exist_ok=True)

        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("오류: 병합할 파일을 찾을 수 없습니다.", False))
            return

        success_count = 0
        for txt_file in txt_files:
            base_name = os.path.splitext(txt_file)[0]
            time_path = os.path.join(time_dir, txt_file)
            sentence_path = os.path.join(sentence_dir, txt_file)
            output_path = os.path.join(output_dir, f"{base_name}_updated.srt")
            if self._merge_single_srt(time_path, sentence_path, output_path):
                success_count += 1

        self.log_queue.put(
            (f"총 {len(txt_files)}개 중 {success_count}개 파일 병합 완료.", False)
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
        self.log_queue.put((f"시간 일괄 조절 시작... (대상 폴더: {dir_path})", False))
        srt_files = [f for f in os.listdir(dir_path) if f.lower().endswith(".srt")]
        if not srt_files:
            self.log_queue.put(("오류: 폴더에서 SRT 파일을 찾을 수 없습니다.", False))
            return

        success_count = 0
        for srt_file in srt_files:
            try:
                self.log_queue.put((f"  - 처리 중: {srt_file}", False))
                file_path = os.path.join(dir_path, srt_file)
                with open(file_path, "r", encoding="utf-8-sig") as f:
                    content = f.read()

                blocks = parse_srt_content(content)
                new_srt_content = []
                for block in blocks:
                    new_time = block["time"]
                    if int(block["number"]) >= start_num:
                        start_time, end_time = block["time"].split(" --> ")
                        new_start = shift_time_string(start_time, offset)
                        new_end = shift_time_string(end_time, offset)
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
                self.log_queue.put((f"  - 오류 ({srt_file}): {e}", False))

        self.log_queue.put(
            (f"총 {len(srt_files)}개 중 {success_count}개 파일 시간 조절 완료.", False)
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

    def _execute_translation_all(self, sentence_dir):
        """폴더 내 모든 파일을 번역"""
        self.log_queue.put(("전체 번역 작업 시작...", False))
        txt_files = [f for f in os.listdir(sentence_dir) if f.lower().endswith(".txt")]
        if not txt_files:
            self.log_queue.put(("번역할 .txt 파일을 찾을 수 없습니다.", False))
            return

        self.log_queue.put(
            (f"총 {len(txt_files)}개의 파일에 대한 번역을 시작합니다.", False)
        )
        success_count = 0
        for filename in txt_files:
            filepath = os.path.join(sentence_dir, filename)
            if self._translate_single_file(filepath):
                success_count += 1

        self.log_queue.put(
            (f"총 {len(txt_files)}개 중 {success_count}개 파일 번역 완료.", False)
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
        self.run_generic_thread(self._execute_translation_all, sentence_dir)

    def _execute_one_click_workflow(self, dir_path):
        """원클릭 워크플로우: SRT 파일 단위로 분리-번역-병합을 순차 실행"""
        self.log_queue.put(("🚀 원클릭 전체 작업을 시작합니다.", False))

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
        success_count = 0

        for i, srt_file in enumerate(srt_files, 1):
            self.log_queue.put(
                (f"\n[{i}/{total_files}] '{srt_file}' 작업 시작...", False)
            )
            srt_path = os.path.join(dir_path, srt_file)
            base_name = os.path.splitext(srt_file)[0]

            # 1. 분리
            split_success, sentence_file_path = self._split_single_srt(
                srt_path, time_dir, sentence_dir
            )
            if not split_success:
                continue

            # 2. 번역
            if not self._translate_single_file(sentence_file_path):
                continue

            # 3. 병합
            time_file_path = os.path.join(time_dir, f"{base_name}.txt")
            output_srt_path = os.path.join(output_dir, f"{base_name}_updated.srt")
            if not self._merge_single_srt(
                time_file_path, sentence_file_path, output_srt_path
            ):
                continue

            self.log_queue.put((f"✅ '{srt_file}' 작업 완료.", False))
            success_count += 1

        self.log_queue.put(
            (
                f"\n✅ 모든 작업이 완료되었습니다! (성공: {success_count}/{total_files})",
                False,
            )
        )
        messagebox.showinfo(
            "작업 완료",
            f"모든 작업이 완료되었습니다.\n(성공: {success_count}/{total_files})",
        )

    def run_one_click_wrapper(self):
        dir_path = filedialog.askdirectory(title="SRT 파일이 있는 폴더를 선택하세요")
        if dir_path:
            self.run_generic_thread(self._execute_one_click_workflow, dir_path)


if __name__ == "__main__":
    app = SrtToolApp()
    app.mainloop()
