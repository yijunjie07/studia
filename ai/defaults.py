"""Built-in provider. Its key is not shipped with the code: set STUDIA_DEFAULT_API_KEY to enable it."""
import os

from ai.client import AIConfig


DEFAULT_PROFILE_ID = "builtin-default"
DEFAULT_PROVIDER_NAME = "默认供应商"
DEFAULT_KEY_ENV = "STUDIA_DEFAULT_API_KEY"


def default_config():
    """The built-in provider, or None when no key is configured."""
    key = os.environ.get(DEFAULT_KEY_ENV, "").strip()
    if not key:
        return None
    return AIConfig(
        base_url="https://mochif.com/v1",
        model="gemini-3.8-flash",
        api_format="chat_completions",
        provider_name=DEFAULT_PROVIDER_NAME,
        api_key=key,
    )
