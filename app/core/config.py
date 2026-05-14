from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR.parent / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    app_name: str = 'Mobile Complaints Emergency Simulation'
    api_prefix: str = '/api/v1'
    secret_key: str = 'CHANGE_ME_IN_PRODUCTION'
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = f'sqlite:///{DATA_DIR / "mobile_complaints.sqlite3"}'
    model_config = SettingsConfigDict(env_file=str(BASE_DIR.parent / '.env'), extra='ignore')

settings = Settings()
