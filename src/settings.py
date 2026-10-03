from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "ADC Irradiation Work Order"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"

    # LLM — output luôn theo JSON schema; nhiệt độ 0 để trích xuất ổn định (AGENTS.md §3)
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_s: float = Field(default=30.0, gt=0)

    # Gemini — đọc PDF, OCR, trích xuất ticket (ADR-0010)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"  # 3.8-flash hay 503 quá tải (30/09/2026)
    gemini_timeout_s: float = Field(default=60.0, gt=0)

    # Order Agent chọn provider (ADR-0013): gemini (mặc định, ADR-0010) | openai — dùng OPENAI_API_KEY
    order_agent_provider: Literal["gemini", "openai"] = "gemini"
    openai_order_model: str = ""  # rỗng → MODEL_NAME; model phải đọc được file PDF (vd gpt-4o-mini)
    openai_order_timeout_s: float = Field(default=60.0, gt=0)  # đọc cả file PDF lâu hơn lời gọi LLM thường

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Giả định throughput mô phỏng (ADC-002)
    throughput_config_path: str = "src/config/throughput.yaml"
    seed_dir: str = "src/seed"  # orders.json, incidents.json cho POST /api/demo/reset (T-025)

    # Lưu UTC, hiển thị giờ địa phương: lý do xếp lịch và `date=` của GET /api/schedule (ADC-003)
    local_utc_offset: str = "+07:00"

    # Upload PDF (ADC-001)
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 10
    max_pdf_pages: int = 20

    # Google OAuth (ADC-008)
    google_client_id: str = ""
    google_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    allowed_email_domains: str = ""  # rỗng → không ai đăng ký được (fail-closed)
    bootstrap_admin_emails: str = ""  # email được tạo ACTIVE + ADMIN ở lần đăng nhập đầu
    session_ttl_hours: int = 12  # hết hạn sau N giờ không hoạt động
    session_cookie_secure: bool = True
    oauth_state_ttl_min: int = 10
    frontend_url: str = "http://localhost:3000"  # đích chuyển hướng sau callback

    # Feature flags (dự phòng khi demo/pitch)
    feature_ocr: bool = True
    feature_ai_message_draft: bool = True
    feature_ai_explanation: bool = True  # Scheduler Agent giải thích phương án sự cố (T-034)
    feature_demo_login: bool = False
    demo_reset_enabled: bool = False
    feature_random_estimate: bool = False  # DEMO: ước tính thời lượng ngẫu nhiên 4–8h thay mô hình ADC-002

    @field_validator("local_utc_offset")
    @classmethod
    def _offset(cls, v: str) -> str:
        datetime.strptime(v, "%z")
        return v

    @property
    def local_tz(self) -> timezone:
        return datetime.strptime(self.local_utc_offset, "%z").tzinfo  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
