import os
import json
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
import asyncio
from functools import wraps
from typing import Optional, List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler

from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
from tusclient import client
import aiohttp
from cachetools import TTLCache

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

app = Flask(__name__, static_url_path='', static_folder='static')
CORS(app)
cache = TTLCache(maxsize=100, ttl=300)  # 5-minute cache

VAULT_NAME = "Time Capsule"
CONFIG_FILE = "vault_config.json"
vault_id = None
api_key = None

def load_or_create_vault(api_key):
    global vault_id
    url = "https://api.tusky.io/vaults"
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json={"name": VAULT_NAME})
    
    if response.status_code not in (200, 201):
        raise Exception(f"Failed to create vault: {response.status_code} - {response.text}")
    
    vault_id = response.json().get('id')
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'vault_id': vault_id, 'api_key': api_key}, f)
    print(f"Created and saved new vault: {vault_id}")

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        vault_id = config.get('vault_id')
        api_key = config.get('api_key')
        if vault_id:
            print(f"Using existing vault: {vault_id}")
        else:
            load_or_create_vault(api_key)

class Config:
    TUSKY_API_URL = "https://api.tusky.io"
    UPLOAD_FOLDER = "temp_uploads"
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2.5GB limit
    CHUNK_SIZE = 5 * 1024 * 1024  # 5MB chunks for upload

class TimeCapsuleError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

def error_handler(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except TimeCapsuleError as e:
            return jsonify({'error': e.message}), e.status_code
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    return decorated_function

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

class FileManager:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.tus_client = client.TusClient(
            f"{Config.TUSKY_API_URL}/uploads",
            headers={'Api-Key': api_key}
        )

    async def upload_file(self, file, metadata: Dict[str, Any]) -> str:
        temp_path = os.path.join(Config.UPLOAD_FOLDER, secure_filename(file.filename))
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        
        try:
            file.save(temp_path)
            with open(temp_path, 'rb') as file_stream:
                uploader = self.tus_client.uploader(
                    file_stream=file_stream,
                    metadata=metadata,
                    chunk_size=Config.CHUNK_SIZE
                )
                uploader.upload()
            return uploader.url
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

db = Database()
file_manager = FileManager(api_key)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/files', methods=['GET'])
@error_handler
async def list_files():
    user_id = request.args.get('user_id')
    if not user_id:
        raise TimeCapsuleError("User ID is required")

    print(user_id)

    cache_key = f"files_{user_id}"
    if cache_key in cache:
        return jsonify(cache[cache_key])

    files = db.get_user_files(user_id)
    print(files)
    cache[cache_key] = files
    return jsonify(files)

@app.route('/api/upload', methods=['POST'])
@error_handler
async def upload():
    if 'file' not in request.files:
        raise TimeCapsuleError("Capsule not provided")

    if 'user_id' not in request.form:
        raise TimeCapsuleError("Capsule key is required")

    file = request.files['file']
    if not file.filename:
        raise TimeCapsuleError("Capsule name not provided")

    current_user_id = request.form['user_id']
    allowed_users = request.form.get('allowed_users', '')
    
    if not allowed_users:
        raise TimeCapsuleError("You must specify which users will be granted capsule access")
    
    # 허용된 사용자 목록 처리 개선
    try:
        # 입력이 이미 JSON 문자열인 경우를 처리
        if allowed_users.startswith('['):
            allowed_users_list = json.loads(allowed_users)
        else:
            # 쉼표로 구분된 문자열인 경우를 처리
            allowed_users_list = [user.strip() for user in allowed_users.split(',') if user.strip()]
        
        # 리스트로 변환하고 중복 제거
        allowed_users_list = list(set(allowed_users_list))
        
        if not allowed_users_list:
            raise TimeCapsuleError("No valid capsule key was provided")
            
    except json.JSONDecodeError:
        raise TimeCapsuleError("The format of the allowed capsule receipt key list is incorrect")

    if current_user_id not in allowed_users_list:
        allowed_users_list.append(current_user_id)

    # print(allowed_users_list)

    file_data = {
        'filename': secure_filename(file.filename),
        'unlock_date': request.form['unlock_date'],
        'allowed_users': allowed_users_list,
        'file_size': os.fstat(file.fileno()).st_size,
        'mime_type': file.content_type,
        'uploader_id': current_user_id
    }

    metadata = {
        'filename': file_data['filename'],
        'vaultId': vault_id
    }

    upload_url = await file_manager.upload_file(file, metadata)
    file_id = upload_url.split('/')[-1]
    
    db.add_file(file_id, file_data)
    cache.clear()

    return jsonify({
        'status': 'success',
        'file_id': file_id,
        'url': upload_url
    })

@app.route('/api/download/<file_id>', methods=['GET'])
@error_handler
async def download(file_id: str):
    user_id = request.args.get('user_id')
    if not user_id:
        raise TimeCapsuleError("Capsule key is required", 401)

    file = db.get_file(file_id)
    if not file:
        raise TimeCapsuleError("Capsule not found", 404)

    try:
        current_date = datetime.now(timezone.utc)
        unlock_date = datetime.strptime(file['unlock_date'], '%Y-%m-%d %H:%M:%S')
        unlock_date = unlock_date.replace(tzinfo=timezone.utc)

        if not file.get('unlocked', False) and current_date < unlock_date:
            return jsonify({
                'error': 'This capsule is still locked',
                'message': f'This capsule will be available for viewing at {unlock_date.strftime("%Y-%m-%d %H:%M")}',
                'unlock_date': file['unlock_date']
            }), 403

        allowed_users = file['allowed_users']
        if isinstance(allowed_users, str):
            allowed_users = json.loads(allowed_users)
            
        if user_id not in allowed_users:
            raise TimeCapsuleError("You do not have permission to access the capsule", 403)

        download_url = f"{Config.TUSKY_API_URL}/files/{file_id}/data"
        headers = {'Api-Key': api_key}
        
        response = requests.get(download_url, headers=headers, stream=True)
        if response.status_code != 200:
            raise TimeCapsuleError("Failed to view capsule", response.status_code)

        # 다운로드 상태 업데이트 및 삭제 여부 확인
        should_delete = db.check_and_update_download(file_id, user_id)
        
        # 모든 수신자가 다운로드했다면 캡슐 삭제 처리
        if should_delete:
            async def delete_file():
                try:
                    headers = {
                        'Content-Type': 'application/json',
                        'Api-Key': api_key
                    }
                    
                    trash_response = requests.patch(
                        f"{Config.TUSKY_API_URL}/files/{file_id}",
                        headers=headers,
                        json={'status': 'deleted'}
                    )
                    
                    if trash_response.status_code == 200:
                        requests.delete(
                            f"{Config.TUSKY_API_URL}/trash",
                            headers=headers
                        )
                        db.delete_file(file_id)
                        cache.clear()
                        
                except Exception as e:
                    print(f"Error deleting file: {str(e)}")

            asyncio.create_task(delete_file())

        return Response(
            response.iter_content(chunk_size=8192),
            headers={
                'Content-Disposition': f'attachment; filename="{file["filename"]}"',
                'Content-Type': file['mime_type'] or 'application/octet-stream'
            }
        )
        
    except ValueError as e:
        raise TimeCapsuleError(f"date format error: {str(e)}", 400)
    except requests.RequestException as e:
        raise TimeCapsuleError(f"Download failed: {str(e)}", 500)

@app.route('/api/delete/<file_id>', methods=['DELETE'])
@error_handler
async def delete_file_route(file_id: str):
    user_id = request.args.get('user_id')
    if not user_id:
        raise TimeCapsuleError("Capsule Key is required", 401)

    try:
        file_info = db.get_file(file_id)
        if not file_info:
            raise TimeCapsuleError("Capsule not found", 404)

        if file_info.get('uploader_id') != user_id:
            raise TimeCapsuleError("You do not have permission to delete capsules. Capsules can only be deleted by the user who uploaded them.", 403)

        headers = {
            'Content-Type': 'application/json',
            'Api-Key': api_key
        }

        # First, try to delete from Tusky storage
        trash_response = requests.patch(
            f"{Config.TUSKY_API_URL}/files/{file_id}",
            headers=headers,
            json={'status': 'deleted'}
        )

        if trash_response.status_code != 200:
            print(f"Tusky deletion failed with status: {trash_response.status_code}")
            print(f"Response content: {trash_response.text}")
            raise TimeCapsuleError("Failed to move capsule to trash", trash_response.status_code)

        # Then empty the trash
        delete_response = requests.delete(
            f"{Config.TUSKY_API_URL}/trash",
            headers=headers
        )

        if delete_response.status_code not in [200, 204]:
            print(f"Trash emptying failed with status: {delete_response.status_code}")
            print(f"Response content: {delete_response.text}")
            raise TimeCapsuleError("Failed to empty trash", delete_response.status_code)

        # Finally, delete from local database
        with db.get_connection() as conn:
            cursor = conn.cursor()
            # Delete from download_tracking first due to foreign key constraint
            cursor.execute("DELETE FROM download_tracking WHERE file_id = ?", (file_id,))
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()  # Explicitly commit the transaction

        # Clear the cache after successful deletion
        cache.clear()
        
        return jsonify({'success': True})

    except TimeCapsuleError as e:
        raise e
    except Exception as e:
        print(f"Unexpected error during deletion: {str(e)}")
        raise TimeCapsuleError(str(e), 500)

def check_expired_files():
    with db.get_connection() as conn:
        cursor = conn.cursor()
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        
        # 만료된 캡슐 조회
        cursor.execute("""
            SELECT id FROM files 
            WHERE expiry_date < ? 
        """, (current_time,))
        
        expired_files = cursor.fetchall()
        
        for (file_id,) in expired_files:
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Api-Key': api_key
                }
                
                # Tusky API에서 캡슐 삭제
                trash_response = requests.patch(
                    f"{Config.TUSKY_API_URL}/files/{file_id}",
                    headers=headers,
                    json={'status': 'deleted'}
                )
                
                if trash_response.status_code == 200:
                    requests.delete(
                        f"{Config.TUSKY_API_URL}/trash",
                        headers=headers
                    )
                    
                    # 데이터베이스에서 캡슐 정보 삭제
                    db.delete_file(file_id)
                    cache.clear()
                    print(f"Expired file deleted: {file_id}")
                    
            except Exception as e:
                print(f"Error deleting expired file {file_id}: {str(e)}")

# 스케줄러 초기화 및 시작
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_expired_files, trigger="interval", hours=1)
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
