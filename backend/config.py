import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Project root
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env file from root
load_dotenv(ROOT_DIR / ".env")

class Settings(BaseSettings):
    # MinerU API 配置
    mineru_api_url: str = "http://localhost:8000"
    mineru_api_key: Optional[str] = None
    
    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 目录配置
    input_dir: Path = ROOT_DIR / "input"
    output_dir: Path = ROOT_DIR / "output"
    
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()

# Ensure directories exist
os.makedirs(settings.input_dir, exist_ok=True)
os.makedirs(settings.output_dir, exist_ok=True)
