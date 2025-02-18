import os
import json
import tempfile
from database import Database
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

from rate_limiter import RateLimiter, rate_limit

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

rate_limiter = RateLimiter(
    requests_per_minute=40,  # 분당 60개 요청 제한
    requests_per_hour=1000   # 시간당 1000개 요청 제한
)

app = Flask(__name__, static_url_path='', static_folder='static')
CORS(app)
cache = TTLCache(maxsize=100, ttl=5)  # 5 sec

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
@rate_limit(rate_limiter)
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
@rate_limit(rate_limiter)
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
@rate_limit(rate_limiter)
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
                'message': f'This capsule will be unlocked at {unlock_date.strftime("%Y-%m-%d %H:%M")}',
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
@rate_limit(rate_limiter)
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
