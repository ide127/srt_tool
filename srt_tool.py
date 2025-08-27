import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import re
from datetime import datetime, timedelta
import subprocess
import threading
import queue
import logging
import srt
import whisper
import config
import prompts
import ttkbootstrap as tb

# --- Core Processing Functions ---

def get_srt_content_for_llm(srt_path):
    """Reads an SRT file and returns its content as a string with timestamps removed."""
    try:
        with open(srt_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        subs = list(srt.parse(content))
        content_list = []
        for sub in subs:
            content_list.append(str(sub.index))
            content_list.append(sub.content.strip())
            content_list.append("")
        return "\n".join(content_list)
    except Exception as e:
        # Assuming a log_queue is available in the context this is called
        print(f"Error parsing SRT for LLM: {e}")
        return ""

def run_whisper(video_path, cache_dir, log_queue):
    """Runs Whisper on a video file and saves the output as an SRT file."""
    log_queue.put(f"Whisper 모델 '{config.WHISPER_MODEL}'을 로드 중입니다...")
    model = whisper.load_model(config.WHISPER_MODEL)
    log_queue.put("모델 로드 완료. 음성 인식을 시작합니다...")

    result = model.transcribe(video_path, language="hi", verbose=True)

    hindi_srt_path = os.path.join(cache_dir, os.path.basename(video_path) + config.HINDI_SRT_SUFFIX)

    with open(hindi_srt_path, "w", encoding="utf-8") as srt_file:
        for i, segment in enumerate(result['segments'], 1):
            start_time = srt.timedelta_to_srt_timestamp(timedelta(seconds=segment['start']))
            end_time = srt.timedelta_to_srt_timestamp(timedelta(seconds=segment['end']))
            srt_file.write(f"{i}\n")
            srt_file.write(f"{start_time} --> {end_time}\n")
            srt_file.write(f"{segment['text'].strip()}\n\n")

    return hindi_srt_path

def run_dialogue_matcher(hindi_srt_path, english_srt_path, log_queue):
    """Uses an LLM to match dialogues between Hindi and English SRT files."""
    log_queue.put("대사 매칭을 위해 SRT 파일 내용을 준비 중입니다...")
    hindi_content = get_srt_content_for_llm(hindi_srt_path)
    english_content = get_srt_content_for_llm(english_srt_path)

    prompt = prompts.PROMPT_MATCHER.format(
        hindi_srt_content=hindi_content,
        english_srt_content=english_content
    )

    log_queue.put(f"Gemini '{config.MATCHER_MODEL}' 모델로 대사 매칭을 요청합니다...")
    # Placeholder for actual Gemini API call
    # matched_text = call_gemini(prompt, model=config.MATCHER_MODEL)
    log_queue.put("... (LLM API 호출 시뮬레이션) ...")
    # This dummy response simulates a partial match and a NO_MATCH case
    matched_text = """134
Hindi
आप यहाँ कैसे आये?
English
How did you come here?

135
Hindi
मैं एक दोस्त के परिचय से आया हूँ।
English
NO_MATCH

136
Hindi
कौन सा दोस्त?
English
Which friend?
"""
    log_queue.put("대사 매칭 완료. 매칭되지 않은 영어 대사를 확인합니다...")

    # Find unused English lines
    original_english_subs = list(srt.parse(english_content))
    used_english_lines = set(line.strip() for line in re.findall(r'English\n(.*?)\n\n', matched_text, re.DOTALL))

    unmatched_english_lines = []
    for sub in original_english_subs:
        if sub.content.strip() not in used_english_lines:
            unmatched_english_lines.append(f"  - (Line {sub.index}): {sub.content.strip()}")

    if unmatched_english_lines:
        log_queue.put(f"경고: 다음 {len(unmatched_english_lines)}개의 영어 대사가 힌디어 대사와 매칭되지 않았습니다:\n" + "\n".join(unmatched_english_lines))

    return matched_text

def run_translator_and_assemble(matched_text, hindi_srt_path, output_path, log_queue):
    """Parses matched text, translates, and assembles the final SRT."""
    log_queue.put("최종 번역 및 SRT 파일 생성을 시작합니다...")

    hindi_subs = {sub.index: sub for sub in srt.parse(open(hindi_srt_path, 'r', encoding='utf-8-sig').read())}

    matched_blocks = matched_text.strip().split("\n\n")
    final_srt_subs = []

    for block in matched_blocks:
        try:
            parts = block.strip().split("\n")
            hindi_num = int(parts[0])
            hindi_text = parts[2]
            english_text = parts[4]

            if "NO_MATCH" in english_text:
                korean_text = "" # Or some other placeholder
                log_queue.put(f"  - {hindi_num}번 자막은 매칭되는 영어가 없어 건너뜁니다.")
            else:
                log_queue.put(f"  - {hindi_num}번 자막 번역 중...")
                prompt = prompts.PROMPT_TRANSLATOR.format(hindi_text=hindi_text, english_text=english_text)
                # korean_text = call_gemini(prompt, model=config.TRANSLATOR_MODEL)
                korean_text = f"[번역됨] {english_text}" # Placeholder translation

            original_sub = hindi_subs.get(hindi_num)
            if original_sub:
                new_sub = srt.Subtitle(index=hindi_num, start=original_sub.start, end=original_sub.end, content=korean_text)
                final_srt_subs.append(new_sub)
        except Exception as e:
            log_queue.put(f"블록 처리 중 오류 발생: {block[:30]}... 오류: {e}")

    final_srt_content = srt.compose(final_srt_subs)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_srt_content)
    log_queue.put(f"최종 한국어 자막 파일 생성 완료: {output_path}")

# --- GUI Application ---

class App(tb.Window):
    def __init__(self):
        super().__init__(themename="litera")
        self.title("SRT Synchronizer & Translator v1.0")
        self.geometry("900x700")

        self.video_dir = tk.StringVar()
        self.srt_dir = tk.StringVar()

        self.log_queue = queue.Queue()
        self.setup_logging()
        self.create_widgets()
        self.after(100, self.process_log_queue)

    def create_widgets(self):
        main_frame = tb.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        folder_frame = tb.Labelframe(main_frame, text="폴더 선택", padding=15)
        folder_frame.pack(fill=tk.X, pady=(0, 10))
        tb.Label(folder_frame, text="영상 폴더:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        tb.Entry(folder_frame, textvariable=self.video_dir, state="readonly").grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        tb.Button(folder_frame, text="선택...", command=lambda: self.select_folder(self.video_dir), bootstyle="secondary").grid(row=0, column=2, padx=5, pady=5)
        tb.Label(folder_frame, text="영어 자막 폴더:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        tb.Entry(folder_frame, textvariable=self.srt_dir, state="readonly").grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        tb.Button(folder_frame, text="선택...", command=lambda: self.select_folder(self.srt_dir), bootstyle="secondary").grid(row=1, column=2, padx=5, pady=5)
        folder_frame.grid_columnconfigure(1, weight=1)

        self.start_button = tb.Button(main_frame, text="전체 작업 시작", command=self.start_processing_wrapper, bootstyle="primary")
        self.start_button.pack(fill=tk.X, ipady=10, pady=(10, 10))

        log_frame = tb.Labelframe(main_frame, text="처리 로그", padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", state="normal", font=("Courier New", 9))
        self.log_text.bind("<KeyPress>", lambda e: "break")
        scrollbar = tb.Scrollbar(log_frame, command=self.log_text.yview, bootstyle="round")
        self.log_text.config(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def select_folder(self, var):
        folder_path = filedialog.askdirectory()
        if folder_path: var.set(folder_path)

    def setup_logging(self):
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        self.log_filename = os.path.join(log_dir, f"log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S", handlers=[logging.FileHandler(self.log_filename, encoding="utf-8")])

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="normal")
        logging.info(message)
        self.update_idletasks()

    def process_log_queue(self):
        try:
            message = self.log_queue.get_nowait()
            self.log(message)
        except queue.Empty: pass
        finally: self.after(100, self.process_log_queue)

    def start_processing_wrapper(self):
        video_dir = self.video_dir.get()
        srt_dir = self.srt_dir.get()
        if not video_dir or not srt_dir:
            messagebox.showerror("오류", "영상 폴더와 자막 폴더를 모두 선택해야 합니다.")
            return
        self.start_button.config(state="disabled")
        thread = threading.Thread(target=self.process_all_episodes, args=(video_dir, srt_dir), daemon=True)
        thread.start()

    def process_all_episodes(self, video_dir, srt_dir):
        self.log_queue.put("=== 전체 작업 시작 ===")
        try:
            video_files = {os.path.splitext(f)[0]: os.path.join(video_dir, f) for f in os.listdir(video_dir) if f.endswith((".mp4", ".mkv"))}
            srt_files = {os.path.splitext(f)[0]: os.path.join(srt_dir, f) for f in os.listdir(srt_dir) if f.endswith(".srt")}
        except Exception as e:
            self.log_queue.put(f"폴더를 읽는 중 오류 발생: {e}"); return

        matched_episodes = sorted(list(set(video_files.keys()) & set(srt_files.keys())))
        if not matched_episodes:
            self.log_queue.put("처리할 에피소드를 찾지 못했습니다. 파일 이름을 확인하세요 (예: ep_01.mp4, ep_01.srt)."); return

        self.log_queue.put(f"총 {len(matched_episodes)}개의 에피소드를 처리합니다: {', '.join(matched_episodes)}")

        cache_dir = os.path.join(os.getcwd(), config.CACHE_DIR_NAME)
        os.makedirs(cache_dir, exist_ok=True)

        for i, ep_name in enumerate(matched_episodes):
            self.log_queue.put(f"\n--- ({i+1}/{len(matched_episodes)}) 에피소드 '{ep_name}' 처리 시작 ---")
            video_path = video_files[ep_name]
            english_srt_path = srt_files[ep_name]
            final_srt_path = os.path.join(srt_dir, ep_name + config.KOREAN_SRT_SUFFIX)

            try:
                hindi_srt_path = os.path.join(cache_dir, os.path.basename(video_path) + config.HINDI_SRT_SUFFIX)
                if not os.path.exists(hindi_srt_path) or config.FORCE_REPROCESS:
                    self.log_queue.put("1. Whisper로 힌디어 자막 추출 중... (시간이 오래 걸릴 수 있습니다)")
                    hindi_srt_path = core.run_whisper(video_path, cache_dir, self.log_queue)
                    self.log_queue.put(f"   -> 힌디어 자막 생성 완료: {os.path.basename(hindi_srt_path)}")
                else:
                    self.log_queue.put("1. 캐시된 힌디어 자막을 사용합니다.")

                matched_text_path = os.path.join(cache_dir, os.path.basename(video_path) + config.MATCHED_TEXT_SUFFIX)
                if not os.path.exists(matched_text_path) or config.FORCE_REPROCESS:
                    self.log_queue.put("2. Gemini로 힌디어-영어 대사 매칭 중...")
                    matched_text = core.run_dialogue_matcher(hindi_srt_path, english_srt_path, self.log_queue)
                    with open(matched_text_path, 'w', encoding='utf-8') as f: f.write(matched_text)
                    self.log_queue.put("   -> 대사 매칭 완료.")
                else:
                    self.log_queue.put("2. 캐시된 매칭 데이터를 사용합니다.")
                    with open(matched_text_path, 'r', encoding='utf-8') as f: matched_text = f.read()

                core.run_translator_and_assemble(matched_text, hindi_srt_path, final_srt_path, self.log_queue)

                self.log_queue.put(f"--- '{ep_name}' 처리 완료 ---")
            except Exception as e:
                self.log_queue.put(f"!!! '{ep_name}' 처리 중 심각한 오류 발생: {e} !!!")
                continue

        self.log_queue.put("=== 모든 작업 완료 ===")
        self.start_button.config(state="normal")

if __name__ == "__main__":
    app = App()
    app.mainloop()
