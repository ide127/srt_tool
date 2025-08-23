"""
Application Configuration and Policy Definitions
"""

# Base prompt that forms the foundation of all generated prompts
BASE_PROMPT = """너는 드라마와 영화의 자막을 자연스럽게 잘 번역하는 유능한 번역가야. 나는 너에게 자막 텍스트를 보여줄거야. 너는 이 자막을 자연스러운 한국어로 변환하면 돼. 변환 할 때는 아래 요구사항을 준수하도록 해.

1. 넘버링 정보에 맞추어서 영어 문장만 한국어로 replace 할 것. 각 대사 라인마다 한줄 띄워쓰기가 되어 있는 기존 포맷을 유지할 것.
"""

# Policies that affect the core application logic (not the prompt itself)
APP_POLICIES = {
    "split_multi_line": {
        "type": "boolean",
        "label": "두 줄 이상 자막 자동 분리 (시간 비례 분배)",
        "default": True
    }
}

# Policies that are used to dynamically generate the Gemini prompt
PROMPT_POLICIES = {
    "omit_metadata": {
        "type": "boolean",
        "label": "메타데이터 자막 생략 (e.g., [music playing])",
        "prompt_text": "2. [dramatic music]이나 STORY:, LANG: 와 같이 대사가 아닌 정보를 전달하는 자막은 생략하고 넘버링만 남길 것.",
        "default": True
    },
    "sentence_ending": {
        "type": "choice",
        "label": "문장 끝맺음 처리",
        "options": {
            "omit_period": "4. 문장의 끝을 알리는 '.' 만 생략할 것. 왜냐하면 서로 대화를 하는 구어체인거니까. '?'나 '!' 등 다른 부호는 남겨놓도록 해.",
            "keep_all": "4. 문장의 끝을 알리는 부호('.', '?', '!')를 모두 유지할 것."
        },
        "default": "omit_period"
    },
    "quote_handling": {
        "type": "boolean",
        "label": "따옴표(') 제거",
        "prompt_text": "6. 대사를 ''로 묶거나 하는 등의 간결한 작업과 거리가 먼 짓을 하지 말 것. 설령 기존 자막에 ''이 있더라도 제거하도록 할 것.",
        "default": True
    },
    "multi_line_sentence": {
        "type": "choice",
        "label": "여러 줄에 걸친 문장 처리",
        "options": {
            "combine": "7. 하나의 문장이라면 길더라도 두줄로 나누지 말고 한줄에 모두 적어. 기존 영어 문장으로는 두줄로 나누어져 있더라도, 변환할 때는 한줄로 번역해서 넣어놔.",
            "keep_lines": "7. 기존 자막이 여러 줄로 나뉘어 있다면, 번역 결과도 동일하게 여러 줄로 나누어 표시할 것."
        },
        "default": "combine"
    },
    "dash_dialogue": {
        "type": "choice",
        "label": "'-' 동시 대화 처리",
        "options": {
            "split_no_dash": "8. 두 사람의 대사가 하나의 자막 라인에 있다면, '-' 라는 기호로 두줄에 나누어서 작성되어 있을텐데, 번역 할 때는 '-' 기호를 붙이지 말고 그냥 두 줄로만 나누어놔.",
            "split_with_dash": "8. 두 사람의 대사가 하나의 자막 라인에 있다면, '-' 라는 기호로 두줄에 나누어서 작성되어 있을텐데, 번역 할 때도 '-' 기호를 유지하여 각 줄을 구분해줘."
        },
        "default": "split_no_dash"
    }
}

# Placeholder for character and glossary data structure
# This will be managed by the UI and saved in profile files
DEFAULT_PROJECT_DATA = {
    "characters": [
        {"source": "Tara Priya Singh Saxena", "target": "타라 프리야 싱 사크세나"},
        {"source": "Dr. Dhruv Saxena", "target": "닥터 드루브 사크세나"}
    ],
    "glossary": [
        {"source": "Vallabhgarh", "target": "발라브가르"}
    ]
}
