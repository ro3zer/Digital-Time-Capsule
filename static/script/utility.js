// 유틸리티 함수
const showToast = (message, isError = false) => {
    Toastify({
        text: message,
        duration: 3000,
        gravity: "top",
        position: "right",
        backgroundColor: isError ? "#DC2626" : "#059669",
        className: "rounded-lg",
        style: {
            background: isError ? 
                "linear-gradient(to right, #DC2626, #B91C1C)" :
                "linear-gradient(to right, #059669, #047857)"
        }
    }).showToast();
};

const showError = (message) => {
    const errorAlert = document.getElementById('errorAlert');
    const errorMessage = document.getElementById('errorMessage');
    errorMessage.textContent = message;
    errorAlert.classList.remove('hidden');
    setTimeout(() => errorAlert.classList.add('hidden'), 5000);
};

function startSimulatedProgress() {
    const progress = document.getElementById('progress');
    const progressText = document.getElementById('progressText');
    let width = 0;
    isUploading = true;

    if (progressInterval) {
        clearInterval(progressInterval);
    }

    progressInterval = setInterval(() => {
        if (!isUploading) {
            clearInterval(progressInterval);
            return;
        }

        if (width < 90) {
            const increment = (90 - width) / 200;
            width += Math.max(0.1, increment);
            progress.style.width = width + '%';
            progressText.textContent = Math.round(width) + '%';
        }
    }, 100);
}

function stopSimulatedProgress() {
    isUploading = false;
    if (progressInterval) {
        clearInterval(progressInterval);
    }
}

function completeProgress() {
    stopSimulatedProgress();
    const progress = document.getElementById('progress');
    const progressText = document.getElementById('progressText');
    
    progress.style.width = '100%';
    progressText.textContent = 'Done!';

    setTimeout(() => {
        progressContainer.style.display = 'none';
        // Reset progress for next upload
        progress.style.width = '0%';
        progressText.textContent = '0%';

    }, 3000);
}

const formatDate = (dateString) => {
    // UTC 시간을 Date 객체로 변환
    const date = new Date(dateString + 'Z');  // 'Z'를 추가하여 UTC임을 명시
    
    // 사용자의 로컬 시간대로 변환하여 표시
    return date.toLocaleString('ko-KR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone // 사용자의 로컬 시간대 사용
    });
};

function updateFileName(input) {
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    if (input.files && input.files.length > 0) {
        fileNameDisplay.textContent = input.files[0].name;
        fileNameDisplay.classList.remove('text-gray-400');
        fileNameDisplay.classList.add('text-white');
    } else {
        fileNameDisplay.textContent = 'Choose a file';
        fileNameDisplay.classList.remove('text-white');
        fileNameDisplay.classList.add('text-gray-400');
    }
}