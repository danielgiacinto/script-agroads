import sys
import traceback

from config import EXCEL_PATH, IMAGES_FOLDER

from agroads_bot import run

if __name__ == "__main__":
    try:
        run(EXCEL_PATH, IMAGES_FOLDER)
        input("\nPresione Enter para cerrar...")
    except Exception as e:
        print("\n--- ERROR ---", flush=True)
        traceback.print_exc()
        input("\nPresione Enter para cerrar...")
        sys.exit(1)
