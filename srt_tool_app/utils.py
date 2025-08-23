import re
from datetime import datetime, timedelta
from tkinter import messagebox

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
    """번역 결과물의 형식이 올바른지(블록 사이에 빈 줄이 있는지) 검증하고, 오류 라인을 반환합니다."""
    lines = content.strip().split("\n")
    if len(lines) <= 1:
        return True, -1

    for i in range(1, len(lines)):
        if lines[i].strip().isdigit() and lines[i - 1].strip() != "":
            return False, i
    return True, -1

def _time_str_to_timedelta(time_str):
    """SRT 시간 문자열을 timedelta 객체로 변환합니다."""
    time_format = "%H:%M:%S.%f"
    try:
        dt_obj = datetime.strptime(time_str.strip().replace(",", "."), time_format)
        return timedelta(
            hours=dt_obj.hour,
            minutes=dt_obj.minute,
            seconds=dt_obj.second,
            microseconds=dt_obj.microsecond,
        )
    except ValueError:
        return timedelta()

def _timedelta_to_time_str(td_obj):
    """timedelta 객체를 SRT 시간 문자열(쉼표 포맷)으로 변환합니다."""
    total_seconds = td_obj.total_seconds()
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d},{milliseconds:03d}"

def _validate_sequential_numbering(content):
    """
    Checks if the subtitle numbers in the content are sequential (1, 2, 3...).
    Returns (True, -1) if valid.
    Returns (False, expected_number) if a gap is found.
    """
    blocks = parse_srt_content(content)
    expected_number = 1
    for block in blocks:
        try:
            current_number = int(block['number'])
            if current_number != expected_number:
                return False, expected_number
            expected_number += 1
        except (ValueError, KeyError):
            return False, expected_number
    return True, -1
