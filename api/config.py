from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    
    DB_URL: str 
    JWT_SECRET: str 
    JWT_ALGORITHM: str 
    JWT_ACCESS_EXPIRY: int = 3600
    JWT_REFRESH_EXPIRY: int = 172800
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        ignore_extra=True,
        case_sensitive=True
    )
    
    
Config = Settings()