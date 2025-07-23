import os
import shutil
import time
import logging
from datetime import datetime, timedelta

# 🔧 설정
SOURCE_DB = "consulting.db"
BACKUP_FOLDER = "backup"
BACKUP_INTERVAL = 3600        # 1시간 (초 단위)
RETENTION_DAYS = 7            # 7일 보관

# ✅ 로그 설정 (Render에서도 보이도록)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def backup_database():
    try:
        if not os.path.exists(BACKUP_FOLDER):
            os.makedirs(BACKUP_FOLDER)
            logging.info(f"📁 backup 폴더 생성됨: {BACKUP_FOLDER}")

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_filename = f"consulting_{timestamp}.db"
        backup_path = os.path.join(BACKUP_FOLDER, backup_filename)

        shutil.copy2(SOURCE_DB, backup_path)
        logging.info(f"[✔] 백업 생성됨: {backup_path}")
    except Exception as e:
        logging.error(f"[❌] 백업 실패: {e}")

def delete_old_backups():
    try:
        now = datetime.now()
        for filename in os.listdir(BACKUP_FOLDER):
            filepath = os.path.join(BACKUP_FOLDER, filename)
            if os.path.isfile(filepath):
                created_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if (now - created_time) > timedelta(days=RETENTION_DAYS):
                    os.remove(filepath)
                    logging.info(f"[✘] 오래된 백업 삭제됨: {filepath}")
    except Exception as e:
        logging.error(f"[❌] 오래된 백업 삭제 실패: {e}")

def run_backup_loop():
    logging.info("🔁 백업 루프 시작됨")
    while True:
        backup_database()
        delete_old_backups()
        time.sleep(BACKUP_INTERVAL)
