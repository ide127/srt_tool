import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import re
from datetime import datetime, timedelta
import subprocess
import threading
import queue
import logging

# --- 핵심 로직 ---


def parse_srt_content(content):
    """SRT 파일 내용을 파싱하여 블록 리스트로 반환합니다."""
    blocks = []
    # 더 유연한 시간 패턴 (콤마 또는 점 허용)
    time_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
    )
    # 빈 줄을 기준으로 청크 분리
    content_chunks = content.strip().split("\n\n")
    block_counter = 1
    for chunk in content_chunks:
        lines = chunk.strip().split("\n")
        if not lines or not lines[0]:
            continue

        time_line, time_line_index = None, -1
        # 시간 정보 라인 찾기
        for i, line in enumerate(lines):
            if time_pattern.search(line):
                time_line, time_line_index = line, i
                break

        if time_line:
            # 시간 라인 위는 번호, 아래는 텍스트로 간주
            number_part = lines[:time_line_index]
            text_part = lines[time_line_index + 1 :]
            number_str = "\n".join(number_part).strip()

            # 번호가 없거나 숫자가 아니면 자동 카운터 사용
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
        # 마이크로초 부분만 남기고 파싱
        dt_obj = datetime.strptime(time_str.strip().replace(",", "."), time_format)
    except ValueError:
        # 잘못된 형식일 경우 원본 반환
        return time_str.strip()

    delta = timedelta(seconds=offset_seconds)
    new_dt_obj = dt_obj + delta

    # 시간이 0보다 작아지면 0으로 고정
    if new_dt_obj < datetime.strptime("00:00:00.000", time_format):
        new_dt_obj = datetime.strptime("00:00:00.000", time_format)

    # 다시 밀리초(3자리)로 포맷팅
    new_time_str = new_dt_obj.strftime(time_format)[:-3]
    return new_time_str.replace(".", ",") if is_comma else new_time_str


# --- GUI 애플리케이션 ---


class SrtToolApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SRT 자막 처리 도구 v2.0 (Gemini 번역 포함)")
        self.geometry("850x750")

        # UI 잠금 상태를 관리하기 위한 변수 (MOVED TO THE TOP)
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
        self.create_shifter_tab()
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
            handlers=[
                logging.FileHandler(self.log_filename, encoding="utf-8"),
            ],
        )
        self.log("로그 파일이 생성되었습니다: " + self.log_filename)

    def log(self, message, is_raw=False):
        """GUI 로그 위젯과 파일에 메시지를 기록합니다."""
        if not hasattr(self, "log_text"):
            return

        # GUI에 로그 추가
        self.log_text.config(state="normal")
        full_message = f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n"
        if is_raw:
            full_message = message  # 원본 메시지 그대로 사용

        self.log_text.insert(tk.END, full_message)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.update_idletasks()

        # 파일에 로그 기록 (줄바꿈이 없는 raw 메시지도 줄바꿈 추가)
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

        self.split_time_shift_var = tk.BooleanVar(value=True)
        cb_split = ttk.Checkbutton(
            tab,
            text="2번 자막부터 1시간 자동 차감 (e.g., 01:00:05 -> 00:00:05)",
            variable=self.split_time_shift_var,
        )
        cb_split.pack(pady=5, anchor="w")

        btn_split = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_split_wrapper
        )
        btn_split.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend([btn_split, cb_split])

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

    def create_shifter_tab(self):
        tab = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tab, text="3. 시간 조절")

        ttk.Label(
            tab,
            text="SRT 파일의 전체 자막 시간을 일괄적으로 조절합니다.",
            wraplength=400,
        ).pack(pady=(0, 10), anchor="w")
        shift_frame = ttk.Frame(tab)
        shift_frame.pack(pady=5, fill="x")

        ttk.Label(shift_frame, text="조절할 시간(초):").pack(side="left", padx=(0, 5))
        self.shift_seconds_entry = ttk.Entry(shift_frame, width=10)
        self.shift_seconds_entry.pack(side="left")
        ttk.Label(shift_frame, text="(예: 1.5, -30)").pack(side="left", padx=(5, 0))

        btn_shift = ttk.Button(
            tab, text="시간 조절할 SRT 파일 선택", command=self.run_shift_wrapper
        )
        btn_shift.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend([self.shift_seconds_entry, btn_shift])

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

        self.oneclick_time_shift_var = tk.BooleanVar(value=True)
        cb_oneclick = ttk.Checkbutton(
            tab,
            text="분리 시, 2번 자막부터 1시간 자동 차감",
            variable=self.oneclick_time_shift_var,
        )
        cb_oneclick.pack(pady=5, anchor="w")

        ttk.Label(
            tab,
            text="이 작업은 시간이 오래 걸릴 수 있으며, 파일을 직접 수정합니다.",
            foreground="blue",
        ).pack(pady=(0, 10), anchor="w")
        btn_oneclick = ttk.Button(
            tab, text="SRT 파일이 있는 폴더 선택", command=self.run_one_click_wrapper
        )
        btn_oneclick.pack(pady=10, ipady=5, anchor="w")
        self.ui_elements.extend([btn_oneclick, cb_oneclick])

    # --- 코어 로직 실행 함수 (단일 파일 처리 위주로 재구성) ---

    def _split_single_srt(self, srt_path, time_dir, sentence_dir, apply_time_shift):
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
                    time_to_write = block["time"]

                    if apply_time_shift:
                        try:
                            # 2번 블록부터 시간 조정
                            if int(block["number"]) >= 2:
                                start_time, end_time = block["time"].split(" --> ")
                                new_start = shift_time_string(start_time, -3600)
                                new_end = shift_time_string(end_time, -3600)
                                time_to_write = f"{new_start} --> {new_end}"
                        except (ValueError, IndexError):
                            pass  # 실패 시 원본 시간 사용

                    tf.write(f"{block['number']}\n{time_to_write}\n\n")
                    sf.write(f"{block['number']}\n{block['text']}\n\n")
            return True, sentence_file_path
        except Exception as e:
            self.log_queue.put((f"  - 분리 오류 ({srt_file}): {e}", False))
            return False, None

    def _translate_single_file(self, txt_path):
        """단일 텍스트 파일을 Gemini를 이용해 번역합니다."""
        filename = os.path.basename(txt_path)
        self.log_queue.put((f"  - 번역 처리 중: {filename}", False))
        try:
            instruction_prompt = """너는 드라마와 영화의 자막을 자연스럽게 잘 번역하는 유능한 번역가야. 나는 너에게 dhruv tara 라는 드라마의 자막을 보여줄거야. 너는 이 자막을 자연스러운 한국어로 변환하면 돼. 변환 할 때는 아래 요구사항을 준수하도록 해. 

1. 넘버링 정보에 맞추어서 영어 문장만 한국어로 replace 할 것. 
2. [dramatic music]이나 
Dhruv Tara - Samay Sadi Se Pare_EP-38
STORY:ZWC0055774 
LANG: GBR 처럼 대사가 아닌 정보를 전달하는 자막은 생략하고 넘버링만 남길 것.
3. 자연스러운 한국어 구어체를 사용할 것. 의미관계를 문맥적으로 잘 파악해서 한국어 특유의 성질을 잘 살릴 것 (예를들면 존댓말/반말). 단순히 단어를 직역하는 것이 아니라, 문맥과 뉘앙스를 고려하여 가장 적절한 번역을 제공할 것. 번역 요청을 받은 후, 문장 구조와 어휘 선택에 세심한 주의를 기울여 번역할 것. 
4. 문장의 끝을 알리는 . 만 생략할 것. 왜냐하면 서로 대화를 하는 구어체인거니까. '.'만 생략하도록 하고 그 외, 예를들면 '?'들은 남겨놓도록 해. 
5. 번역 결과만 출력하도록 하고 그 외 안내 사항은 답변에 추가하지마. 
6. 대사를 ''로 묶거나 하는 등의 간결한 작업과 거리가 먼 짓을 하지 말 것. 설령 기존 자막에 ''이 있더라도 제거하도록 할 것.
7. 통일성 있는 번역을 위해서, 고유명사를 어떻게 번역해야 하는지 알려줄게. 

주요 인물 (Main Characters)
영어 이름 (English Name) 한국어 이름 (Korean Name)
Tara Priya Singh Saxena 타라 프리야 싱 사크세나
Dr. Dhruv Saxena 닥터 드루브 사크세나

왕실 인물 (Royal Family of Vallabhgarh)
영어 이름 (English Name) 한국어 이름 (Korean Name)
Saraswati Singh 사라스와티 싱
Mahaveer Singh 마하비르 싱
Udaybhan Singh 우다이반 싱
Tilottama 틸로타마
Anusuya 아누수야

드루브의 가족 (Dhruv's Family - 21세기)
영어 이름 (English Name) 한국어 이름 (Korean Name)
Lalita Saxena 라리타 사크세나
Ravi Saxena 라비 사크세나
Vidya Saxena 비디야 사크세나
Jai Saxena 자이 사크세나
Ayesha Malhotra Saxena 아이샤 말호트라 사크세나
Sanjay Saxena 산제이 사크세나
Manya Saxena 마냐 사크세나
Shaurya Saxena 샤우르야 사크세나

기타 중요 인물 (Other Important Characters)
영어 이름 (English Name) 한국어 이름 (Korean Name)
Senapati Samrat Singh 세나파티 삼라트 싱
Shyam Mohini 샴 모히니
Ranchod / Lord Krishna 란초드 / 크리슈나
Surya Pratap 수리야 프라탑
Meenakshi 미나크시
Miti 미티

그리고 예시를 보여줄게
-------------------
[기존]
1
00:00:00,000 --> 00:00:00,320
Dhruv Tara Samay Sadi Se Pare EP - 31
STORY: ZWC0055696
LANG: GBR

2
01:01:10,000 --> 01:01:11,400
Hello, madam!

3
01:01:11,560 --> 01:01:13,880
Please connect me to Dr Dhruv.

4
01:01:14,120 --> 01:01:16,280
Dr Dhruv hasn't come
to the hospital today.

5
01:01:16,360 --> 01:01:17,480
He is on leave.

6
01:01:17,800 --> 01:01:19,760
[music playing]

7
01:01:25,440 --> 01:01:27,160
Oh, he didn't come.

[처리 후]
1

2
안녕하세요, 사모님!

3
닥터 드루브 좀 바꿔주세요

4
닥터 드루브는 오늘 병원에 안 오셨어요

5
휴가 중이세요

6

7
아, 안 오셨구나

-------------------
이런 식으로 작업을 하면 돼
"""
            with open(txt_path, "r", encoding="utf-8") as f:
                original_content = f.read()

            if not original_content.strip():
                self.log_queue.put(
                    (f"  - '{filename}' 파일이 비어 있어 건너뜁니다.", False)
                )
                return True

            full_prompt = (
                f"{instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
            )

            # Gemini CLI 명령어에 flash 모델 지정
            command = ["gemini", "-m", "gemini-2.5-flash"]
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            translated_content, stderr = process.communicate(full_prompt)

            if process.returncode == 0:
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(translated_content.strip())
                self.log_queue.put((f"  - 번역 성공: {filename}", False))
                return True
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

                # 파일 형식 불일치 방어 코드
                if len(t_lines) < 2 or len(s_lines) < 1:
                    continue

                number, time_line = t_lines[0], t_lines[1]
                # 번역 결과에서 번호가 누락될 경우를 대비
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
                # 메인 스레드에서 UI를 잠금 해제하도록 예약
                self.after(0, self.unlock_ui)

        thread = threading.Thread(target=task_wrapper, daemon=True)
        thread.start()

    def _execute_split_all(self, dir_path, apply_time_shift):
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
            success, _ = self._split_single_srt(
                srt_path, time_dir, sentence_dir, apply_time_shift
            )
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
            apply_shift = self.split_time_shift_var.get()
            self.run_generic_thread(self._execute_split_all, dir_path, apply_shift)

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
            messagebox.showerror("오류", "'txtWithSentence' 폴더에 파일이 없습니다.")
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

    def _execute_shift(self, file_path, offset):
        """단일 파일 시간 조절"""
        self.log_queue.put(
            (
                f"시간 조절 시작: {os.path.basename(file_path)} (조절값: {offset}초)",
                False,
            )
        )
        try:
            with open(file_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
            new_lines = []
            time_pattern = re.compile(
                r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
            )
            for line in lines:
                match = time_pattern.search(line)
                if match:
                    new_start = shift_time_string(match.group(1), offset)
                    new_end = shift_time_string(match.group(2), offset)
                    new_lines.append(f"{new_start} --> {new_end}\n")
                else:
                    new_lines.append(line)

            dir_name, file_name = os.path.split(file_path)
            base_name, ext = os.path.splitext(file_name)
            output_path = os.path.join(dir_name, f"{base_name}_shifted{ext}")

            with open(output_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            self.log_queue.put((f"시간 조절 완료. 파일 저장: {output_path}", False))
            messagebox.showinfo(
                "완료",
                f"시간 조절이 완료되었습니다.\n파일이 '{output_path}'로 저장되었습니다.",
            )
        except Exception as e:
            self.log_queue.put((f"파일 처리 중 오류: {e}", False))
            messagebox.showerror("오류", f"파일 처리 중 오류가 발생했습니다: {e}")

    def run_shift_wrapper(self):
        try:
            offset = float(self.shift_seconds_entry.get())
        except ValueError:
            messagebox.showerror("입력 오류", "시간(초)에 유효한 숫자를 입력하세요.")
            return
        file_path = filedialog.askopenfilename(
            title="시간을 조절할 SRT 파일 선택", filetypes=[("SRT files", "*.srt")]
        )
        if file_path:
            self.run_generic_thread(self._execute_shift, file_path, offset)

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

    def _execute_one_click_workflow(self, dir_path, apply_time_shift):
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
            self.log_queue.put(("작업할 SRT 파일이 없습니다.", False))
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
                srt_path, time_dir, sentence_dir, apply_time_shift
            )
            if not split_success:
                self.log_queue.put(
                    (f"'{srt_file}' 분리 실패. 다음 파일로 넘어갑니다.", False)
                )
                continue

            # 2. 번역
            translate_success = self._translate_single_file(sentence_file_path)
            if not translate_success:
                self.log_queue.put(
                    (f"'{srt_file}' 번역 실패. 다음 파일로 넘어갑니다.", False)
                )
                continue

            # 3. 병합
            time_file_path = os.path.join(time_dir, f"{base_name}.txt")
            output_srt_path = os.path.join(output_dir, f"{base_name}_updated.srt")
            merge_success = self._merge_single_srt(
                time_file_path, sentence_file_path, output_srt_path
            )
            if not merge_success:
                self.log_queue.put(
                    (f"'{srt_file}' 병합 실패. 다음 파일로 넘어갑니다.", False)
                )
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
            apply_shift = self.oneclick_time_shift_var.get()
            self.run_generic_thread(
                self._execute_one_click_workflow, dir_path, apply_shift
            )


if __name__ == "__main__":
    app = SrtToolApp()
    app.mainloop()
