"""Configuration management for the loan approval system."""

from dotenv import load_dotenv
load_dotenv()        # ← must come before BaseSettings reads .env

from pathlib import Path
from typing import Optional, Any

import yaml
import openai

from pydantic_settings import BaseSettings     # <-- the only BaseSettings
from pydantic import Field



class DatabaseSettings(BaseSettings):
    """Database configuration."""
    url: str = Field(default="sqlite:///./data/app.db")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=5)
    max_overflow: int = Field(default=10)


class VectorSettings(BaseSettings):
    """Vector store configuration."""
    host: str = Field(default="localhost")
    port: int = Field(default=6333)
    collection_name: str = Field(default="policy_chunks")
    embedding_size: int = Field(default=1536)


class LLMSettings(BaseSettings):
    """LLM and embedding model configuration."""
    chat_model: str = Field(default="gpt-4o-mini")
    chat_fallback_model: str = Field(default="gpt-4o")
    embedding_model: str = Field(default="text-embedding-3-small")
    max_tokens: int = Field(default=300)
    temperature: float = Field(default=0.1)
    timeout: int = Field(default=30)


class RiskSettings(BaseSettings):
    """Risk assessment thresholds."""
    hard_decline_threshold: float = Field(default=0.8)
    approve_threshold: float = Field(default=0.65)
    counter_threshold: float = Field(default=0.5)


class BankSettings(BaseSettings):
    """Bank-specific settings."""
    health_constant: float = Field(default=0.82)


class ScrapeSettings(BaseSettings):
    """Market data scraping configuration."""
    schedule_cron: str = Field(default="0 8,14 * * *")
    timeout: int = Field(default=30)
    retry_count: int = Field(default=3)
    stale_threshold_hours: int = Field(default=48)


class AuthSettings(BaseSettings):
    """Authentication configuration."""
    secret_key: str = Field(default="")
    algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=1440)


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""
    requests_per_minute: int = Field(default=30)
    burst_size: int = Field(default=10)


class APISettings(BaseSettings):
    """API server configuration."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    reload: bool = Field(default=False)
    workers: int = Field(default=1)


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO")
    format: str = Field(default="json")
    enable_audit: bool = Field(default=True)


class PerformanceSettings(BaseSettings):
    """Performance targets."""
    target_p95_ms: int = Field(default=1000)
    websocket_timeout: int = Field(default=300)


class DataSettings(BaseSettings):
    """Data file paths."""
    customer_file: str = Field(default="data/Clientbase_scored.csv")
    policy_pdf: str = Field(default="data/cpcdc-commercial-lending-program-loan-policy.pdf")
    policy_chunks: str = Field(default="data/policy_chunks_enriched.jsonl")
    market_cache: str = Field(default="data/market_cache.sqlite")
    data_dictionary: str = Field(default="docs/data_dictionary.json")


class ChatSettings(BaseSettings):
    """Chat history configuration."""
    enable_chat_history: bool = Field(default=False, alias="ENABLE_CHAT_HISTORY")
    history_turns: int = Field(default=8, alias="HISTORY_TURNS")


class IntentSettings(BaseSettings):
    """Intent classification configuration."""
    heuristic_strong: float = Field(default=0.80, alias="INTENT_HEURISTIC_STRONG")       # heuristic confidence to skip judge
    judge_enabled: bool = Field(default=True, alias="INTENT_JUDGE_ENABLED")              # feature flag
    judge_model: str = Field(default="gpt-4o-mini", alias="INTENT_JUDGE_MODEL")          # LLM model for judge
    judge_threshold: float = Field(default=0.70, alias="INTENT_JUDGE_THRESHOLD")         # minimum confidence to accept judge override


class AppSettings(BaseSettings):
    """Main application settings."""
    
    # Environment variables
    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    qdrant_url: Optional[str] = Field(default=None, alias="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(default=None, alias="QDRANT_API_KEY")
    jwt_secret: str = Field(alias="JWT_SECRET")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: Optional[str] = Field(default=None, alias="API_HOST")
    api_port: Optional[int] = Field(default=None, alias="API_PORT")
    
    # OpenAI client (will be initialized after instantiation)
    openai_client: Optional[Any] = Field(default=None, exclude=True)
    
    # Configuration sections
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    vector: VectorSettings = Field(default_factory=VectorSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    bank: BankSettings = Field(default_factory=BankSettings)
    scrape: ScrapeSettings = Field(default_factory=ScrapeSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    api: APISettings = Field(default_factory=APISettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    intent: IntentSettings = Field(default_factory=IntentSettings)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_ignore_empty = True
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_yaml_config()
        self._apply_env_overrides()
        self._initialize_openai_client()

    def _initialize_openai_client(self):
        """Initialize OpenAI client."""
        try:
            if self.openai_api_key:
                self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
                print(f"OpenAI client initialized successfully")
            else:
                self.openai_client = None
                print("Warning: OPENAI_API_KEY not set - OpenAI features will be disabled")
        except Exception as e:
            self.openai_client = None
            print(f"Failed to initialize OpenAI client: {e}")

    def _load_yaml_config(self):
        """Load configuration from YAML file."""
        config_path = Path("config.yaml")
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
            
            # Update settings with YAML values
            for section_name, section_config in yaml_config.items():
                if hasattr(self, section_name) and isinstance(section_config, dict):
                    section = getattr(self, section_name)
                    for key, value in section_config.items():
                        if hasattr(section, key):
                            setattr(section, key, value)

    def _apply_env_overrides(self):
        """Apply environment variable overrides to nested settings."""
        if self.database_url:
            self.database.url = self.database_url
        if self.jwt_secret:
            self.auth.secret_key = self.jwt_secret
        if self.log_level:
            self.logging.level = self.log_level
        if self.api_host:
            self.api.host = self.api_host
        if self.api_port:
            self.api.port = self.api_port

    @property
    def qdrant_host_port(self) -> tuple[str, int]:
        """Get Qdrant host and port, with environment override."""
        if self.qdrant_url:
            # Parse URL like http://localhost:6333
            url_parts = self.qdrant_url.replace("http://", "").replace("https://", "")
            if ":" in url_parts:
                host, port = url_parts.split(":")
                return host, int(port)
            return url_parts, self.vector.port
        return self.vector.host, self.vector.port


# Global settings instance
settings = AppSettings() 