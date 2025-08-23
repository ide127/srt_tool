import os
import subprocess
from srt_tool_app import utils

def _split_single_srt(srt_path, time_dir, sentence_dir, log_queue):
    """단일 SRT 파일을 분리합니다."""
    srt_file = os.path.basename(srt_path)
    try:
        log_queue.put((f"분리 처리 중: {srt_file}", "DEBUG", False))
        with open(srt_path, "r", encoding="utf-8-sig") as f:
            content = f.read()

        blocks = utils.parse_srt_content(content)
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
        log_queue.put((f"분리 오류 ({srt_file}): {e}", "ERROR", False))
        return False, None

def _translate_single_file(txt_path, instruction_prompt, log_queue):
    """단일 텍스트 파일을 Gemini를 이용해 번역하고, 형식 검증 및 모델 재시도 로직을 포함합니다."""
    filename = os.path.basename(txt_path)
    log_queue.put((f"번역 처리 중: {filename}", "INFO", False))

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            original_content = f.read()
        if not original_content.strip():
            log_queue.put((f"'{filename}' 파일이 비어 있어 건너뜁니다.", "WARNING", False))
            return True
    except Exception as e:
        log_queue.put((f"파일 읽기 오류 ({filename}): {e}", "ERROR", False))
        return False

    models_to_try = ["gemini-1.5-flash", "gemini-1.5-pro"]

    for model_name in models_to_try:
        log_queue.put((f"'{model_name}' 모델로 번역 시도...", "INFO", False))

        try:
            full_prompt = f"{instruction_prompt}\n\n[번역해야 할 것]\n\n{original_content}"
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
                log_queue.put((f"'{model_name}' 모델 실행 실패: {stderr}", "ERROR", False))
                continue

            lines = stdout.strip().split("\n")
            filtered_lines = [line for line in lines if "Loaded cached credentials." not in line]
            translated_content = "\n".join(filtered_lines)

            is_valid, error_line_idx = utils._validate_translation_format(translated_content)
            if is_valid:
                is_sequential, expected_num = utils._validate_sequential_numbering(translated_content)
                if is_sequential:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(translated_content.strip())
                    log_queue.put((f"번역 성공 및 형식/순서 확인: {filename} (모델: {model_name})", "INFO", False))
                    return True
                else:
                    log_queue.put((f"'{model_name}' 모델 번역 결과 순서 오류 발생. (예상: {expected_num}, 파일: {filename})", "WARNING", False))
                    continue
            else:
                log_queue.put((f"'{model_name}' 모델 번역 결과 형식 오류 발생.", "WARNING", False))
                error_lines = translated_content.strip().split('\n')
                start = max(0, error_line_idx - 5)
                end = min(len(error_lines), error_line_idx + 6)

                context_log = [f"오류 발생 지점 (라인 {error_line_idx + 1}):"]
                context_log.append("---------- 오류 컨텍스트 시작 ----------")
                for i in range(start, end):
                    prefix = ">> " if i == error_line_idx else "   "
                    context_log.append(f"   {prefix}{i+1:03d}: {error_lines[i]}")
                context_log.append("---------- 오류 컨텍스트 종료 ----------")
                log_queue.put(("\n".join(context_log), "CONTEXT", True))

        except FileNotFoundError:
            log_queue.put(("\n오류: 'gemini' 명령을 찾을 수 없습니다.\nGemini CLI가 설치되어 있고 시스템 PATH에 등록되어 있는지 확인하세요.", "ERROR", False))
            return False
        except Exception as e:
            log_queue.put((f"예상치 못한 번역 오류 ({filename}, 모델: {model_name}): {e}", "ERROR", False))
            continue

    log_queue.put((f"번역 최종 실패: 모든 모델({', '.join(models_to_try)}) 시도 후에도 형식이 올바르지 않음. ({filename})", "ERROR", False))
    return False

def _merge_single_srt(time_file_path, sentence_file_path, output_srt_path, log_queue):
    """
    단일 자막 파일을 병합합니다.
    두 줄 이상의 자막은 길이에 비례하여 시간을 나누고 번호를 다시 매깁니다.
    """
    filename = os.path.basename(output_srt_path)
    try:
        log_queue.put((f"병합 처리 중: {filename}", "DEBUG", False))

        if not os.path.exists(time_file_path) or not os.path.exists(sentence_file_path):
            log_queue.put((f"병합에 필요한 파일이 없습니다. 건너뜁니다.", "WARNING", False))
            return False

        with open(time_file_path, "r", encoding="utf-8") as tf:
            time_chunks = tf.read().strip().split("\n\n")
        with open(sentence_file_path, "r", encoding="utf-8") as sf:
            sentence_chunks = sf.read().strip().split("\n\n")

        srt_output = []
        new_block_counter = 1

        for t_chunk, s_chunk in zip(time_chunks, sentence_chunks):
            if not t_chunk or not s_chunk:
                continue

            t_lines = t_chunk.strip().split("\n")
            s_lines = s_chunk.strip().split("\n")

            if len(t_lines) < 2 or len(s_lines) < 1:
                continue

            original_number = t_lines[0]
            time_line = t_lines[1]
            text_lines = [line for line in (s_lines[1:] if s_lines[0].isdigit() and s_lines[0] == original_number else s_lines) if line.strip()]

            if not text_lines:
                continue

            if len(text_lines) == 1:
                srt_output.append(f"{new_block_counter}\n{time_line}\n{text_lines[0]}\n")
                new_block_counter += 1
            else:
                try:
                    start_time_str, end_time_str = time_line.split(" --> ")
                    start_td = utils._time_str_to_timedelta(start_time_str)
                    end_td = utils._time_str_to_timedelta(end_time_str)
                    total_duration_td = end_td - start_td

                    total_len = sum(len(line) for line in text_lines)
                    if total_len == 0: continue

                    current_start_td = start_td
                    for i, line in enumerate(text_lines):
                        line_len = len(line)
                        proportion = line_len / total_len
                        line_duration_td = total_duration_td * proportion

                        line_end_td = current_start_td + line_duration_td
                        if i == len(text_lines) - 1:
                            line_end_td = end_td

                        new_start_str = utils._timedelta_to_time_str(current_start_td)
                        new_end_str = utils._timedelta_to_time_str(line_end_td)

                        srt_output.append(f"{new_block_counter}\n{new_start_str} --> {new_end_str}\n{line}\n")
                        new_block_counter += 1
                        current_start_td = line_end_td
                except Exception as e:
                    log_queue.put((f"자막 시간 분배 중 오류 ({filename}, 블록: {original_number}): {e}", "ERROR", False))
                    srt_output.append(f"{new_block_counter}\n{time_line}\n{'\n'.join(text_lines)}\n")
                    new_block_counter += 1

        with open(output_srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_output))
        return True
    except Exception as e:
        log_queue.put((f"병합 오류 ({filename}): {e}", "ERROR", False))
        return False

def _backup_failed_srt(srt_path, base_dir, log_queue):
    """실패한 원본 SRT 파일을 'failed_srt' 폴더에 백업합니다."""
    try:
        failed_dir = os.path.join(base_dir, "failed_srt")
        os.makedirs(failed_dir, exist_ok=True)

        backup_path = os.path.join(failed_dir, os.path.basename(srt_path))
        if os.path.exists(backup_path):
            return

        with open(srt_path, "rb") as f_in, open(backup_path, "wb") as f_out:
            f_out.write(f_in.read())

        log_queue.put(
            (f"원본 SRT를 'failed_srt' 폴더에 백업: {os.path.basename(srt_path)}", "WARNING", False)
        )
    except Exception as e:
        log_queue.put((f"실패한 SRT 백업 중 오류 발생: {e}", "ERROR", False))
