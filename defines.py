import os
import os.path

MODELS = [
    "deepseek-r1",
]

QUERY_URL = "https://panservice.mail.wo.cn/wohome/ai/assistant/query"

PROXIES = os.environ.get("PROXIES", None)
API_KEYS : list[str] = os.environ.get("API_KEYS", "").split(",")
AUTHORIZATION_TOKEN : str = os.environ.get("AUTHORIZATION_TOKEN", "")
PROMPT_CHARS_LIMIT : int = int(os.environ.get("PROMPT_CHARS_LIMIT", 5000))
