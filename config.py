import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_env_path)

PROJECT_ROOT = Path(__file__).resolve().parent
EXCEL_PATH = Path(os.getenv("EXCEL_PATH", PROJECT_ROOT / "datos.xlsx"))
IMAGES_FOLDER = Path(os.getenv("IMAGES_FOLDER", PROJECT_ROOT / "fotos"))
DELAY_SECONDS = int(os.getenv("DELAY_SECONDS", "10"))
AGROADS_BASE_URL = os.getenv("AGROADS_BASE_URL", "https://www.agroads.com.ar")
AGROADS_EMAIL = os.getenv("AGROADS_EMAIL", "")
AGROADS_PASSWORD = os.getenv("AGROADS_PASSWORD", "")
BROWSER_USER_DATA = os.getenv("BROWSER_USER_DATA", "")

if not EXCEL_PATH.is_absolute():
    EXCEL_PATH = PROJECT_ROOT / EXCEL_PATH
if not IMAGES_FOLDER.is_absolute():
    IMAGES_FOLDER = PROJECT_ROOT / IMAGES_FOLDER
if BROWSER_USER_DATA and not Path(BROWSER_USER_DATA).is_absolute():
    BROWSER_USER_DATA = str(PROJECT_ROOT / BROWSER_USER_DATA)
