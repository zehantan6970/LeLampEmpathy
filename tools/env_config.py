"""Unified DashScope/Qwen credential loading.

Resolution order (first hit wins):
1. Environment variables DASHSCOPE_API_KEY / WORKSPACE_ID / APP_ID
2. A .env file at the repository root (copy .env.example -> .env and fill in)
"""
import os

from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = ("DASHSCOPE_API_KEY", "WORKSPACE_ID", "APP_ID")


def load_llm_config() -> dict:
    cfg = {}
    repo_env = os.path.join(ROOT, ".env")
    if os.path.exists(repo_env):
        cfg.update({k: v for k, v in dotenv_values(repo_env).items() if v})
    for k in KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    if not cfg.get("DASHSCOPE_API_KEY"):
        raise RuntimeError(
            "DASHSCOPE_API_KEY not found. Set it as an environment variable, "
            "or copy .env.example to .env and fill in your DashScope API key. "
            "Get a key at https://bailian.console.aliyun.com/")
    return cfg
