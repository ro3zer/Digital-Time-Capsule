import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path: str = "timecapsule.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    upload_date TEXT NOT NULL,
                    unlock_date TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,  -- 만료 날짜 필드 추가
                    unlocked INTEGER DEFAULT 0,
                    allowed_users TEXT,
                    file_size INTEGER,
                    mime_type TEXT,
                    uploader_id TEXT NOT NULL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS download_tracking (
                    file_id TEXT,
                    user_id TEXT,
                    downloaded INTEGER DEFAULT 0,
                    download_date TEXT,
                    PRIMARY KEY (file_id, user_id),
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            ''')

    def format_date(self, date_str: str) -> str:
        try:
            # 명시적으로 UTC 타임존 설정
            dt = datetime.strptime(date_str, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone.utc)
            
            print(f"Original datetime: {dt}")
            print(f"Datetime timezone: {dt.tzinfo}")
            
            # UTC로 변환
            utc_dt = dt.astimezone(timezone.utc)
            print(f"UTC datetime: {utc_dt}")
            
            return utc_dt.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            return date_str
            
    def get_user_files(self, user_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, filename, upload_date, unlock_date, unlocked, allowed_users, file_size, mime_type
                FROM files 
                ORDER BY upload_date DESC
            """)
            
            files = []
            for row in cursor.fetchall():
                try:
                    # JSON 문자열을 파싱하여 리스트로 변환
                    allowed_users = json.loads(row['allowed_users'])
                    if user_id in allowed_users:
                        files.append({
                            'id': row['id'],
                            'filename': row['filename'],
                            'upload_date': row['upload_date'],
                            'unlock_date': row['unlock_date'],
                            'unlocked': bool(row['unlocked']),
                            'file_size': row['file_size'],
                            'mime_type': row['mime_type']
                        })
                except json.JSONDecodeError:
                    continue  # JSON 파싱 오류 시 해당 캡슐 건너뛰기
            
            return files

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM files 
                WHERE id = ?
            """, (file_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
                
            return {
                'id': row['id'],
                'filename': row['filename'],
                'upload_date': row['upload_date'],
                'unlock_date': row['unlock_date'],
                'unlocked': bool(row['unlocked']),
                'allowed_users': json.loads(row['allowed_users']) if row['allowed_users'] else [],
                'file_size': row['file_size'],
                'mime_type': row['mime_type'],
                'uploader_id': row['uploader_id']  # uploader_id 필드 추가
            }

    def add_file(self, file_id: str, file_data: Dict[str, Any]) -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = datetime.now(timezone.utc)
            unlock_date = datetime.strptime(file_data['unlock_date'], "%Y-%m-%dT%H:%M")
            expiry_date = unlock_date.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                INSERT INTO files 
                (id, filename, upload_date, unlock_date, expiry_date, allowed_users, file_size, mime_type, uploader_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_id,
                file_data['filename'],
                current_time.strftime('%Y-%m-%d %H:%M:%S'),
                self.format_date(file_data['unlock_date']),
                expiry_date,  # 만료 날짜 추가
                json.dumps(file_data['allowed_users']),
                file_data['file_size'],
                file_data['mime_type'],
                file_data['uploader_id']
            ))
            
            for user_id in file_data['allowed_users']:
                cursor.execute('''
                    INSERT INTO download_tracking (file_id, user_id, downloaded)
                    VALUES (?, ?, 0)
                ''', (file_id, user_id))
            
            return file_id

    def delete_file(self, file_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            return cursor.rowcount > 0

    def check_and_update_download(self, file_id: str, user_id: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 다운로드 상태 확인
            cursor.execute('''
                SELECT downloaded FROM download_tracking
                WHERE file_id = ? AND user_id = ?
            ''', (file_id, user_id))
            
            result = cursor.fetchone()
            if not result or result[0] == 1:
                return False
            
            # 다운로드 상태 업데이트
            cursor.execute('''
                UPDATE download_tracking
                SET downloaded = 1, download_date = ?
                WHERE file_id = ? AND user_id = ?
            ''', (datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), file_id, user_id))
            
            # 모든 수신자가 다운로드했는지 확인
            cursor.execute('''
                SELECT COUNT(*) FROM download_tracking
                WHERE file_id = ? AND downloaded = 0
            ''', (file_id,))
            
            remaining_downloads = cursor.fetchone()[0]
            return remaining_downloads == 0  # 모든 수신자가 다운로드했으면 True 반환

    def check_expired_files(self) -> List[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('''
                SELECT id FROM files
                WHERE expiry_date < ? OR unlock_date < ?
            ''', (current_time, current_time))
            
            return [row[0] for row in cursor.fetchall()]

    def delete_expired_files(self, file_ids: List[str]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for file_id in file_ids:
                cursor.execute('DELETE FROM files WHERE id = ?', (file_id,))
                cursor.execute('DELETE FROM download_tracking WHERE file_id = ?', (file_id,))