import os
import shutil
import time
from datetime import datetime, timedelta

SOURCE_DB = "consulting.db"
BACKUP_FOLDER = "backup"
BACKUP_INTERVAL = 3600  # 1시간마다 백업 (초 단위)
RETENTION_DAYS = 7      # 7일 이상 된 백업은 자동 삭제

def backup_database():
    if not os.path.exists(BACKUP_FOLDER):
        os.makedirs(BACKUP_FOLDER)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = f"consulting_{timestamp}.db"
    backup_path = os.path.join(BACKUP_FOLDER, backup_filename)

    shutil.copy2(SOURCE_DB, backup_path)
    print(f"[✔] Backup created: {backup_path}")

def delete_old_backups():
    now = datetime.now()
    for filename in os.listdir(BACKUP_FOLDER):
        filepath = os.path.join(BACKUP_FOLDER, filename)
        if os.path.isfile(filepath):
            created_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            if (now - created_time) > timedelta(days=RETENTION_DAYS):
                os.remove(filepath)
                print(f"[✘] Old backup deleted: {filepath}")

def run_backup_loop():
    while True:
        try:
            backup_database()
            delete_old_backups()
        except Exception as e:
            print(f"[!] Error during backup: {e}")
        time.sleep(BACKUP_INTERVAL)
