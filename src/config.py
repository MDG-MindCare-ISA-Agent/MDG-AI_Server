import os
from pydantic import BaseModel

from dotenv import load_dotenv
load_dotenv() 

class Settings(BaseModel):
    HCX_API_KEY: str
    HCX_MODEL_NAME: str = "HCX-005"

    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASS: str

    RF: float = 0.0284
    RM_DOMESTIC: float = 0.050
    RM_GLOBAL: float = 0.070
    BETA_TTL_DAYS: int = 7

def get_settings() -> Settings:
    return Settings(
        HCX_API_KEY=os.getenv("HCX_API_KEY", ""),
        HCX_MODEL_NAME=os.getenv("HCX_MODEL_NAME", "HCX-005"),
        DB_HOST=os.getenv("DB_HOST", "localhost"),
        DB_PORT=int(os.getenv("DB_PORT", "3306")),
        DB_NAME=os.getenv("DB_NAME", "mdg"),
        DB_USER=os.getenv("DB_USER", "root"),
        DB_PASS=os.getenv("DB_PASS", ""),
        RF=float(os.getenv("RF", "0.0284")),
        RM_DOMESTIC=float(os.getenv("RM_DOMESTIC", "0.050")),
        RM_GLOBAL=float(os.getenv("RM_GLOBAL", "0.070")),
        BETA_TTL_DAYS=int(os.getenv("BETA_TTL_DAYS", "7")),
    )