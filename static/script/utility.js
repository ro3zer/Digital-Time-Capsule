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

function resetDatePickerDisplay() {
    const selectedDateText = document.getElementById('selectedDateText');
    const unlockDate = document.getElementById('unlockDate');
    
    // Reset text and styling
    selectedDateText.textContent = 'Select Unlock Date and Time';
    selectedDateText.classList.remove('text-white');
    selectedDateText.classList.add('text-gray-400');
    
    // Clear hidden input
    unlockDate.value = '';
    
    // Reset dropdowns to current time
    populateDropdowns(); // date.js에 있는 함수 재사용
}

function resetFileInput() {
    const fileNameDisplay = document.getElementById('fileNameDisplay');
    fileNameDisplay.textContent = 'Choose a file';
    fileNameDisplay.classList.remove('text-white');
    fileNameDisplay.classList.add('text-gray-400');
}

function resetForm() {
    const form = document.getElementById('uploadForm');
    form.reset();
    resetFileInput();
    resetDatePickerDisplay();
}

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
    // 서버에서 받은 문자열을 Date 객체로 변환
    // YYYY-MM-DD HH:mm:ss 형식을 처리
    const [datePart, timePart] = dateString.split(' ');
    const [year, month, day] = datePart.split('-');
    const [hour, minute] = timePart.split(':');
    
    // Date 객체 생성 (월은 0-based이므로 -1)
    const date = new Date(year, month - 1, day, hour, minute);
    
    // 로컬 시간으로 포맷팅
    return date.toLocaleString('en-GB', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
    }).replace(/\//g, '-');
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