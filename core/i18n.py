import os
import json

_current_lang = "en"
CONFIG_FILE = ".mini_cli_config.json"

def set_language(lang: str):
    global _current_lang
    if lang in ["en", "de"]:
        _current_lang = lang

def get_language() -> str:
    return _current_lang

def t(en_text: str, de_text: str) -> str:
    if _current_lang == "de":
        return de_text
    return en_text

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(language: str, mode: str, provider: str, agent_providers: dict = None):
    try:
        config = load_config()
        config["language"] = language
        config["mode"] = mode
        config["provider"] = provider
        if agent_providers is not None:
            config["agent_providers"] = agent_providers
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

