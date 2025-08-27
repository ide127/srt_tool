# --- Application Configuration ---

# Model names
WHISPER_MODEL = "large-v3"
MATCHER_MODEL = "gemini-1.5-pro"
TRANSLATOR_MODEL = "gemini-1.5-pro"

# Directory and file settings
CACHE_DIR_NAME = ".srt_tool_cache"
HINDI_SRT_SUFFIX = ".hi.srt"
MATCHED_TEXT_SUFFIX = ".matched.txt"
KOREAN_SRT_SUFFIX = ".ko.srt"
LOG_FILE_SUFFIX = ".log"

# Processing settings
FORCE_REPROCESS = False # If True, will re-run Whisper and Matcher even if cache files exist.
