        let progressInterval;
        let isUploading = false;

        // 파일 업로드
        document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const form = e.target;
            
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                showToast('Enter the capsule key', true);
                return;
            }
        
            const allowedUsers = document.getElementById('allowedUsers').value.trim();
            if (!allowedUsers) {
                showToast('Please specify who you want to grant capsule access to', true);
                return;
            }
            
            try {
                form.classList.add('loading');
                
                const formData = new FormData();
                const file = document.getElementById('file').files[0];
                const unlockDate = document.getElementById('unlockDate').value;
                const allowedUsersList = allowedUsers
                    .split(',')
                    .map(user => user.trim())
                    .filter(user => user);
        
                formData.append('file', file);
                formData.append('unlock_date', unlockDate);
                formData.append('allowed_users', JSON.stringify(allowedUsersList));
                formData.append('user_id', userId);
        
                const progressContainer = document.getElementById('progressContainer');
                const progress = document.getElementById('progress');
                const progressText = document.getElementById('progressText');
                
                progressContainer.style.display = 'block';
                progress.style.width = '0%';
                
                startSimulatedProgress();
        
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
        
                if (!response.ok) {
                    throw new Error(await response.text());
                }
        
                completeProgress();
                showToast('Capsule has been locked successfully!');
                
                // Reset form and all UI elements
                resetForm();
                
                await loadUserFiles();
            } catch (error) {
                stopSimulatedProgress();
                showToast(error.message, true);
                progress.style.backgroundColor = 'var(--error-color)';
                progressText.textContent = 'Failed Lock';
            } finally {
                form.classList.remove('loading');
                progressContainer.style.display = 'none';
                progress.style.width = '0%';
            }
        });

        // 파일 목록 로드
        async function loadUserFiles() {
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                console.log(userId)
                showToast('Enter the capsule key', true);
                return;
            }

            console.log(userId)

            try {
                const response = await fetch(`/api/files?user_id=${userId}`);
                if (!response.ok) throw new Error(await response.text());
                
                const files = await response.json();
                const fileList = document.getElementById('fileList');
                fileList.innerHTML = '';

                files.forEach(file => {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'file-item glass-card rounded-xl p-4 flex items-center justify-between';
                    fileItem.innerHTML = `
                        <div class="flex-1 min-w-0 mr-4">
                            <h3 class="font-medium truncate">
                                ${file.filename}
                            </h3>
                            <p class="text-sm text-gray-400">Unlock Time: ${formatDate(file.unlock_date)}</p>
                        </div>
                        <div class="flex space-x-2 flex-shrink-0">
                            <button onclick="downloadFile('${file.id}')"
                                    class="btn bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700">
                                Unlock
                            </button>
                            <button onclick="deleteFile('${file.id}')"
                                    class="btn bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700">
                                Del
                            </button>
                        </div>
                    `;
                    fileList.appendChild(fileItem);
                });
            } catch (error) {
                showToast(error.message, true);
            }
        }

        // 파일 다운로드
        async function downloadFile(fileId) {
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                showToast('Enter the capsule key', true);
                return;
            }
        
            try {
                const response = await fetch(`/api/download/${fileId}?user_id=${userId}`);
                
                if (response.status === 403) {
                    const errorData = await response.json();
                    if (errorData.unlock_date) {
                        const localTime = formatDate(errorData.unlock_date);
                        showToast(`This capsule will be unlocked at ${localTime}`, true);
                    } else {
                        showToast(errorData.message || errorData.error, true);
                    }
                    return;
                }
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Failed to download');
                }
        
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'download';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
        
                showToast('Capsule has been downloaded successfully!');
                
                await loadUserFiles();
            } catch (error) {
                showToast(error.message, true);
            }
        }

        // 파일 삭제
        async function deleteFile(fileId) {
            const userId = document.getElementById('userId').value.trim();
            if (!userId) {
                showToast('Enter the capsule key', true);
                return;
            }
        
            if (!confirm('Are you sure you want to delete this capsule?')) return;
        
            try {
                const response = await fetch(`/api/delete/${fileId}?user_id=${userId}`, {
                    method: 'DELETE'
                });
        
                const data = await response.json();
        
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to delete capsule');
                }
                
                showToast('The capsule has been deleted successfully!');
                
                // Clear any cached data
                const fileList = document.getElementById('fileList');
                fileList.innerHTML = '';
                
                // Force a fresh reload of the file list
                await new Promise(resolve => setTimeout(resolve, 500)); // Small delay to ensure deletion is processed
                await loadUserFiles();
                
            } catch (error) {
                console.error('Delete error:', error);
                showToast(error.message, true);
            }
        }

        // 자동으로 파일 목록 로드 (사용자 ID가 있는 경우)
        document.addEventListener('DOMContentLoaded', () => {
            const userId = document.getElementById('userId').value.trim();
            if (userId) loadUserFiles();
        });
