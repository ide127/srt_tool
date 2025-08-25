import os
import json
import tkinter as tk
from tkinter import filedialog, messagebox, Canvas
import ttkbootstrap as ttk
from ttkbootstrap.constants import *


def get_capcut_projects(base_path):
    """
    지정된 경로에서 CapCut 프로젝트 목록을 가져옵니다.
    draft_info.json 파일만 있어도 프로젝트로 인식합니다.
    """
    projects = {}
    if not os.path.isdir(base_path):
        return projects

    for item in os.listdir(base_path):
        project_dir = os.path.join(base_path, item)
        draft_info_path = os.path.join(project_dir, "draft_info.json")

        if os.path.isdir(project_dir) and os.path.exists(draft_info_path):
            project_name = f"이름 없는 프로젝트 ({item})"
            try:
                with open(draft_info_path, "r", encoding="utf-8") as f:
                    draft_info = json.load(f)
                    name_from_json = draft_info.get("draft_name")
                    if name_from_json:
                        project_name = f"{name_from_json} ({item})"
            except (json.JSONDecodeError, KeyError) as e:
                print(f"프로젝트 정보({item}) 읽기 오류. 폴더 이름을 사용합니다: {e}")

            projects[project_name] = project_dir

    return projects


def time_to_srt_format(time_us):
    """마이크로초를 SRT 시간 형식(HH:MM:SS,ms)으로 변환합니다."""
    if time_us < 0:
        time_us = 0
    time_s = time_us / 1_000_000
    hours, remainder = divmod(time_s, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = round((seconds - int(seconds)) * 1000)
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02},{int(milliseconds):03}"


def extract_srt_from_draft_info(project_path, output_dir):
    """draft_info.json 파일에서 자막을 추출하여 SRT 파일로 저장합니다."""
    draft_info_path = os.path.join(project_path, "draft_info.json")
    if not os.path.exists(draft_info_path):
        return "오류: draft_info.json 파일을 찾을 수 없습니다."

    try:
        with open(draft_info_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        texts = data.get("materials", {}).get("texts", [])
        tracks = data.get("tracks", [])

        subtitles = []
        text_id_map = {text["id"]: text for text in texts}

        for track in tracks:
            if track.get("type") == "text":
                for segment in track.get("segments", []):
                    material_id = segment.get("material_id")
                    if material_id in text_id_map:
                        text_info = text_id_map[material_id]
                        timerange = segment.get("target_timerange", {})
                        start_time = timerange.get("start", 0)
                        duration = timerange.get("duration", 0)

                        try:
                            content_json = json.loads(text_info.get("content", "{}"))
                            subtitle_text = content_json.get("text", "").strip()
                        except (json.JSONDecodeError, TypeError):
                            subtitle_text = ""

                        if subtitle_text:
                            subtitles.append(
                                {
                                    "start": start_time,
                                    "end": start_time + duration,
                                    "text": subtitle_text,
                                }
                            )

        if not subtitles:
            return "정보: 이 프로젝트에는 자막 데이터가 없습니다."

        subtitles.sort(key=lambda s: s["start"])

        srt_content = ""
        for i, sub in enumerate(subtitles):
            start_str = time_to_srt_format(sub["start"])
            end_str = time_to_srt_format(sub["end"])
            srt_content += f"{i + 1}\n"
            srt_content += f"{start_str} --> {end_str}\n"
            srt_content += f"{sub['text']}\n\n"

        draft_name = data.get("draft_name", os.path.basename(project_path))
        safe_project_name = "".join(
            c for c in draft_name if c.isalnum() or c in (" ", "_")
        ).rstrip()
        output_filename = f"{safe_project_name}_{os.path.basename(project_path)}.srt"
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write(srt_content)

        return f"성공: '{safe_project_name}' 자막 저장 완료"

    except json.JSONDecodeError:
        return "오류: draft_info.json 파일 형식이 올바르지 않습니다."
    except Exception as e:
        return f"알 수 없는 오류 발생: {e}"


class App(ttk.Window):
    def __init__(self):
        super().__init__(themename="vapor")
        self.title("CapCut 자막 추출기 (다중 선택 지원)")
        self.geometry("750x600")

        self.default_capcut_path = os.path.expanduser(
            "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
        )
        self.projects = {}
        self.check_vars = {}

        # 메인 프레임
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=BOTH, expand=YES)

        # 경로 프레임
        path_frame = ttk.LabelFrame(
            main_frame, text="1. CapCut 프로젝트 폴더 선택", padding=10
        )
        path_frame.pack(fill=X, pady=5)

        self.path_entry = ttk.Entry(path_frame, bootstyle="info")
        self.path_entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        self.path_entry.insert(0, self.default_capcut_path)
        ttk.Button(
            path_frame,
            text="폴더 선택",
            command=self.browse_path,
            bootstyle="outline-info",
        ).pack(side=LEFT, padx=(0, 5))
        ttk.Button(
            path_frame,
            text="새로고침",
            command=self.refresh_projects,
            bootstyle="outline-success",
        ).pack(side=LEFT)

        # 목록 프레임 (스크롤 가능한 체크박스 리스트)
        list_outer_frame = ttk.LabelFrame(
            main_frame, text="2. 자막을 추출할 프로젝트 선택", padding=10
        )
        list_outer_frame.pack(fill=BOTH, expand=YES, pady=5)

        # 전체 선택/해제 프레임
        select_all_frame = ttk.Frame(list_outer_frame)
        select_all_frame.pack(fill=X, pady=(0, 5))
        ttk.Button(
            select_all_frame,
            text="전체 선택",
            command=lambda: self.toggle_all(True),
            bootstyle="link-primary",
        ).pack(side=LEFT)
        ttk.Button(
            select_all_frame,
            text="전체 해제",
            command=lambda: self.toggle_all(False),
            bootstyle="link-danger",
        ).pack(side=LEFT, padx=10)

        canvas = Canvas(list_outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            list_outer_frame,
            orient="vertical",
            command=canvas.yview,
            bootstyle="round-info",
        )
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 하단 프레임
        bottom_frame = ttk.LabelFrame(main_frame, text="3. 추출 실행", padding=10)
        bottom_frame.pack(fill=X, pady=5)

        self.progress = ttk.Progressbar(
            bottom_frame, bootstyle="success-striped", mode="determinate"
        )
        self.progress.pack(fill=X, expand=YES, pady=5)

        self.extract_button = ttk.Button(
            bottom_frame,
            text="선택한 프로젝트 모두 추출",
            command=self.extract_multiple_subtitles,
            bootstyle="success",
        )
        self.extract_button.pack(pady=5)

        self.refresh_projects()

    def browse_path(self):
        path = filedialog.askdirectory(
            initialdir=os.path.expanduser("~/Movies/CapCut/User Data/Projects")
        )
        if path:
            self.path_entry.delete(0, END)
            self.path_entry.insert(0, path)
            self.refresh_projects()

    def refresh_projects(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        path = self.path_entry.get()
        if not path:
            ttk.Label(
                self.scrollable_frame, text="CapCut 프로젝트 폴더를 먼저 선택해주세요."
            ).pack()
            return

        self.projects = get_capcut_projects(path)
        self.check_vars = {}

        if not self.projects:
            ttk.Label(
                self.scrollable_frame,
                text="프로젝트를 찾을 수 없습니다. 폴더를 확인해주세요.",
                bootstyle="secondary",
            ).pack(pady=10)
        else:
            for name in sorted(self.projects.keys()):
                var = tk.BooleanVar()
                cb = ttk.Checkbutton(
                    self.scrollable_frame, text=name, variable=var, bootstyle="primary"
                )
                cb.pack(anchor="w", padx=5, pady=2)
                self.check_vars[name] = var

    def toggle_all(self, state):
        for var in self.check_vars.values():
            var.set(state)

    def extract_multiple_subtitles(self):
        selected_projects = [name for name, var in self.check_vars.items() if var.get()]

        if not selected_projects:
            messagebox.showwarning("경고", "목록에서 프로젝트를 하나 이상 선택하세요.")
            return

        # 결과 폴더 생성 (스크립트 실행 위치 기준)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        srt_output_dir = os.path.join(script_dir, "SRT_Results")
        os.makedirs(srt_output_dir, exist_ok=True)

        total_projects = len(selected_projects)
        self.progress["maximum"] = total_projects
        self.progress["value"] = 0

        results = []
        for i, project_name in enumerate(selected_projects):
            project_path = self.projects.get(project_name)
            if project_path:
                result = extract_srt_from_draft_info(project_path, srt_output_dir)
                results.append(result)

            # 진행 상황 업데이트
            self.progress["value"] = i + 1
            self.update_idletasks()

        messagebox.showinfo(
            "추출 완료",
            f"총 {total_projects}개의 프로젝트 중 {len(results)}개 처리 완료.\n결과 폴더: {srt_output_dir}",
        )
        self.progress["value"] = 0


if __name__ == "__main__":
    try:
        import ttkbootstrap
    except ImportError:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "오류",
            "ttkbootstrap 라이브러리가 필요합니다.\n터미널에서 'pip install ttkbootstrap'을 실행해주세요.",
        )
        exit()

    app = App()
    app.mainloop()
