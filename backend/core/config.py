
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str    = "Banner Automation Testing"
    app_version: str = "1.0.0"
    debug: bool      = False

    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/bannermind.db"

   
    ollama_base_url:      str = "http://localhost:11434"
    ollama_vision_model:  str = "llava:latest"   
    ollama_text_model:    str = "qwen2.5:7b"   

    # ── Playwright 
    playwright_headless: bool = True
    playwright_timeout:  int  = 60_000

    # ── Paths 
    screenshot_dir: Path = BASE_DIR / "screenshots"
    report_dir:     Path = BASE_DIR / "reports"

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    class Config:
        env_file = BASE_DIR / ".env"


settings = Settings()
settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
settings.report_dir.mkdir(parents=True, exist_ok=True)