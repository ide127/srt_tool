import os
import subprocess
from srt_tool_app import utils
import srt

def _split_single_srt(srt_path, time_dir, sentence_dir, log_queue):
    """단일 SRT 파일을 분리합니다."""
    srt_file = os.path.basename(srt_path)
    try:
        log_queue.put((f"분리 처리 중: {srt_file}", "DEBUG"))
        with open(srt_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        blocks = utils.parse_srt_content(content)
        base_name = os.path.splitext(srt_file)[0]
        time_file_path = os.path.join(time_dir, f"{base_name}.txt")
        sentence_file_path = os.path.join(sentence_dir, f"{base_name}.txt")
        with open(time_file_path, "w", encoding="utf-8") as tf, open(sentence_file_path, "w", encoding="utf-8") as sf:
            for block in blocks:
                tf.write(f"{block.index}\n{utils._timedelta_to_time_str(block.start)} --> {utils._timedelta_to_time_str(block.end)}\n\n")
                sf.write(f"{block.index}\n{block.content}\n\n")
        return True, sentence_file_path
    except Exception as e:
        log_queue.put((f"분리 오류 ({srt_file}): {e}", "ERROR"))
        return False, None

def _translate_single_file(txt_path, instruction_prompt, log_queue):
    """단일 텍스트 파일을 Gemini를 이용해 번역하고, 형식 검증 및 모델 재시도 로직을 포함합니다."""
    filename = os.path.basename(txt_path)
    log_queue.put((f"번역 처리 중: {filename}", "INFO"))
    try:
        with open(txt_path, "r", encoding="utf-8") as f: original_content = f.read()
        if not original_content.strip():
            log_queue.put((f"'{filename}' 파일이 비어 있어 건너뜁니다.", "WARNING")); return True
    except Exception as e:
        log_queue.put((f"파일 읽기 오류 ({filename}): {e}", "ERROR")); return False

    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro"]
    for model_name in models_to_try:
        log_queue.put((f"'{model_name}' 모델로 번역 시도...", "INFO"))
        try:
            full_prompt = f"{instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
            command = ["gemini", "-m", model_name]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
            stdout, stderr = process.communicate(full_prompt)
            if process.returncode != 0:
                log_queue.put((f"'{model_name}' 모델 실행 실패: {stderr}", "ERROR")); continue

            translated_content = "\n".join([l for l in stdout.strip().split("\n") if "Loaded cached credentials." not in l])
            is_valid_format, error_line_idx = utils._validate_translation_format(translated_content)
            if not is_valid_format:
                log_queue.put((f"'{model_name}' 모델 번역 결과 형식 오류 발생.", "WARNING"))
                lines = translated_content.strip().split('\n')
                start, end = max(0, error_line_idx - 5), min(len(lines), error_line_idx + 6)
                context_log = [f"오류 발생 지점 (라인 {error_line_idx + 1}):", "---------- 오류 컨텍스트 시작 ----------"]
                context_log.extend([f"   {'>> ' if i == error_line_idx else '   '}{i+1:03d}: {lines[i]}" for i in range(start, end)])
                context_log.append("---------- 오류 컨텍스트 종료 ----------")
                log_queue.put(("\n".join(context_log), "CONTEXT", True)); continue

            is_sequential, expected_num = utils._validate_sequential_numbering(translated_content)
            if not is_sequential:
                log_queue.put((f"'{model_name}' 모델 번역 결과 순서 오류 발생. (예상: {expected_num}, 파일: {filename})", "WARNING")); continue

            with open(txt_path, "w", encoding="utf-8") as f: f.write(translated_content.strip())
            log_queue.put((f"번역 성공 및 형식/순서 확인: {filename} (모델: {model_name})", "INFO")); return True
        except FileNotFoundError:
            log_queue.put(("\n'gemini' 명령을 찾을 수 없습니다. Gemini CLI가 설치되어 있고 시스템 PATH에 등록되어 있는지 확인하세요.", "ERROR")); return False
        except Exception as e:
            log_queue.put((f"예상치 못한 번역 오류 ({filename}, 모델: {model_name}): {e}", "ERROR")); continue

    log_queue.put((f"번역 최종 실패: 모든 모델 시도 후에도 실패. ({filename})", "ERROR")); return False

def _merge_single_srt(time_file_path, sentence_file_path, output_srt_path, log_queue, split_multi_line):
    filename = os.path.basename(output_srt_path)
    try:
        log_queue.put((f"병합 처리 중: {filename}", "DEBUG"))
        if not os.path.exists(time_file_path) or not os.path.exists(sentence_file_path):
            log_queue.put(("병합에 필요한 파일이 없습니다. 건너뜁니다.", "WARNING")); return False
        with open(time_file_path, "r", encoding="utf-8") as tf: time_chunks = tf.read().strip().split("\n\n")
        with open(sentence_file_path, "r", encoding="utf-8") as sf: sentence_chunks = sf.read().strip().split("\n\n")

        final_subs = []
        new_block_counter = 1
        for t_chunk, s_chunk in zip(time_chunks, sentence_chunks):
            if not t_chunk or not s_chunk: continue
            t_lines, s_lines = t_chunk.strip().split("\n"), s_chunk.strip().split("\n")
            if len(t_lines) < 2 or len(s_lines) < 1: continue
            original_number, time_line = t_lines[0], t_lines[1]
            text_lines = [line for line in (s_lines[1:] if s_lines[0].isdigit() and s_lines[0] == original_number else s_lines) if line.strip()]
            if not text_lines: continue

            if split_multi_line and len(text_lines) > 1:
                try:
                    start_str, end_str = time_line.split(" --> ")
                    start_td, end_td = utils._time_str_to_timedelta(start_str), utils._time_str_to_timedelta(end_str)
                    total_duration_td, total_len = end_td - start_td, sum(len(line) for line in text_lines)
                    if total_len == 0: continue
                    current_start_td = start_td
                    for i, line in enumerate(text_lines):
                        proportion = len(line) / total_len
                        line_duration_td = total_duration_td * proportion
                        line_end_td = current_start_td + line_duration_td if i < len(text_lines) - 1 else end_td
                        final_subs.append(srt.Subtitle(index=new_block_counter, start=current_start_td, end=line_end_td, content=line))
                        new_block_counter += 1
                        current_start_td = line_end_td
                except Exception as e:
                    log_queue.put((f"자막 시간 분배 중 오류 ({filename}, 블록: {original_number}): {e}", "ERROR"))
                    final_subs.append(srt.Subtitle(index=new_block_counter, start=utils._time_str_to_timedelta(t_lines[1].split(" --> ")[0]), end=utils._time_str_to_timedelta(t_lines[1].split(" --> ")[1]), content="\n".join(text_lines)))
                    new_block_counter += 1
            else:
                final_subs.append(srt.Subtitle(index=new_block_counter, start=utils._time_str_to_timedelta(t_lines[1].split(" --> ")[0]), end=utils._time_str_to_timedelta(t_lines[1].split(" --> ")[1]), content="\n".join(text_lines)))
                new_block_counter += 1
        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write(srt.compose(final_subs))
        return True
    except Exception as e:
        log_queue.put((f"병합 오류 ({filename}): {e}", "ERROR")); return False

def _backup_failed_srt(srt_path, base_dir, log_queue):
    try:
        failed_dir = os.path.join(base_dir, "failed_srt")
        os.makedirs(failed_dir, exist_ok=True)
        backup_path = os.path.join(failed_dir, os.path.basename(srt_path))
        if os.path.exists(backup_path): return
        with open(srt_path, "rb") as f_in, open(backup_path, "wb") as f_out: f_out.write(f_in.read())
        log_queue.put((f"원본 SRT를 'failed_srt' 폴더에 백업: {os.path.basename(srt_path)}", "WARNING"))
    except Exception as e:
        log_queue.put((f"실패한 SRT 백업 중 오류 발생: {e}", "ERROR"))
