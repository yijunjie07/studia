"""Maintainer-sponsored shared service, intentionally distributed with the app.

This is a public client credential, not a private user key. Enforce its spending
and model limits at the provider; client-side hiding cannot protect it.
"""
from ai.client import AIConfig


DEFAULT_PROFILE_ID = "builtin-default"
DEFAULT_PROVIDER_NAME = "默认供应商"


def default_config():
    return AIConfig(
        base_url="https://mochif.com/v1",
        model="gemini-3.8-flash",
        provider_name=DEFAULT_PROVIDER_NAME,
        api_key="sk-l4HgtBSCj9vgMUrL49RUDFYakcokDMGIx3Z5wQ8xMRnigTjW",
    )
