from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings."""
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

    # Application
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"

    # LLM Configuration
    llm_provider: Literal["bedrock", "mock"] = "bedrock"
    use_mock_llm: bool = False

    # AWS Bedrock Settings
    aws_region: str = "eu-central-1"
    bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_model_temperature: float = 0.3
    bedrock_model_max_tokens: int = 300

    # AWS Credentials (Optional - if not provided, will use AWS CLI/IAM role)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None  # For temporary credentials

    # Storage
    data_dir: Path = Path("./data")
    seed_dir: Path = Path("./data/seed")
    runtime_dir: Path = Path("./data/runtime")

    def __init__(self, **kwargs):
        """Create directories on startup."""
        super().__init__(**kwargs)
        self.seed_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @property
    def has_aws_credentials(self) -> bool:
        """Check if explicit AWS credentials are provided."""
        return bool(self.aws_access_key_id and self.aws_secret_access_key)


settings = Settings()