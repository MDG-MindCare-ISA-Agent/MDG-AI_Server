from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from .config import get_settings

_settings = get_settings()

def get_engine() -> Engine:
    url = (
        f"mysql+pymysql://{_settings.DB_USER}:{_settings.DB_PASS}"
        f"@{_settings.DB_HOST}:{_settings.DB_PORT}/{_settings.DB_NAME}"
    )
    engine = create_engine(url, pool_pre_ping=True)
    return engine

RF = _settings.RF
RM_DOMESTIC = _settings.RM_DOMESTIC
RM_GLOBAL = _settings.RM_GLOBAL
BETA_TTL_DAYS = _settings.BETA_TTL_DAYS
SETTINGS = _settings