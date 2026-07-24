import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Automatically load environment variables from .env if present
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Global configuration settings for MoA Engine."""

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    cc_switch_endpoint: str = os.getenv("CC_SWITCH_ENDPOINT", "https://api.anthropic.com")
    
    timeout_seconds: float = float(os.getenv("MOA_TIMEOUT", "60.0"))
    max_retries: int = int(os.getenv("MOA_MAX_RETRIES", "3"))
    retry_backoff_factor: float = float(os.getenv("MOA_RETRY_BACKOFF", "1.5"))


config = Config()
