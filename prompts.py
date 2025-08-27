# --- Prompt Templates for LLM Tasks ---

# 1. Prompt for Dialogue Matching
PROMPT_MATCHER = """
You are a precise data processing assistant. Your task is to merge two SRT files, one in Hindi and one in English, based on semantic meaning.

The goal is to create a new, unified text block that uses the numbering and dialogue from the Hindi SRT as the primary reference, and finds the corresponding English dialogue for each line.

RULES:
1.  Use the Hindi SRT as the baseline. Iterate through every numbered entry in the Hindi SRT.
2.  For each Hindi dialogue line, find the single best-matching English dialogue line from the English SRT based on semantic meaning.
3.  The numbering of the English SRT is irrelevant and should be ignored.
4.  If you find a confident match, format the output exactly as follows, with no extra text or explanations:
    {Hindi Number}
    Hindi
    {Hindi Dialogue}
    English
    {English Dialogue}
5.  If you cannot find a confident semantic match for a Hindi line, you MUST use the token 'NO_MATCH' for the English part. For example:
    {Hindi Number}
    Hindi
    {Hindi Dialogue}
    English
    NO_MATCH
6.  Ensure every numbered entry from the Hindi SRT is present in your output. Do not skip any Hindi numbers.

Here are the two SRT files.

[HINDI SRT START]
{hindi_srt_content}
[HINDI SRT END]

[ENGLISH SRT START]
{english_srt_content}
[ENGLISH SRT END]
"""


# 2. Prompt for Translation
PROMPT_TRANSLATOR = """
You are a professional subtitle translator, specializing in translating for dramas and movies. Your task is to translate the given [English Text] into natural, modern Korean.

-   **Use the [Original Hindi Text] as critical context.** It will help you understand the original nuance, tone, honorifics (존댓말/반말), and any cultural specifics that might be lost in the English translation.
-   Provide only the final Korean translation, with no extra labels, quotes, or explanations.

[Original Hindi Text]:
{hindi_text}

[English Text to Translate]:
{english_text}

[Korean Translation]:
"""
