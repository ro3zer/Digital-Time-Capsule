document.addEventListener('DOMContentLoaded', function() {
    const datePickerDisplay = document.getElementById('datePickerDisplay');
    const customDatePicker = document.getElementById('customDatePicker');
    const selectedDateText = document.getElementById('selectedDateText');
    const cancelButton = document.getElementById('cancelDatePicker');
    const confirmButton = document.getElementById('confirmDatePicker');
    const hiddenInput = document.getElementById('unlockDate');

    // Toggle date picker
    datePickerDisplay.addEventListener('click', function() {
        customDatePicker.classList.toggle('hidden');
    });

    // Cancel button
    cancelButton.addEventListener('click', function() {
        customDatePicker.classList.add('hidden');
    });

    // Confirm button
    confirmButton.addEventListener('click', function() {
        const month = document.getElementById('monthSelect').value;
        const day = document.getElementById('daySelect').value;
        const year = document.getElementById('yearSelect').value;
        const hour = document.getElementById('hourSelect').value;
        const minute = document.getElementById('minuteSelect').value;

        if (month && day && year && hour !== '' && minute !== '') {
            // 선택한 날짜와 시간으로 문자열 생성 (YYYY-MM-DDTHH:mm 형식)
            const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
            
            // 화면에 표시할 형식
            const displayDate = new Date(dateStr);
            const formattedDisplayDate = displayDate.toLocaleString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true
            });

            selectedDateText.textContent = formattedDisplayDate;
            selectedDateText.classList.remove('text-gray-400');
            selectedDateText.classList.add('text-white');

            // 선택한 날짜 그대로 저장 (타임존 변환 없이)
            hiddenInput.value = dateStr;

            customDatePicker.classList.add('hidden');
        } else {
            alert('Please select all date and time components');
        }
    });
});

// Populate dropdowns
function populateDropdowns() {
    const monthSelect = document.getElementById('monthSelect');
    const daySelect = document.getElementById('daySelect');
    const yearSelect = document.getElementById('yearSelect');
    const hourSelect = document.getElementById('hourSelect');
    const minuteSelect = document.getElementById('minuteSelect');

    // Get current date and time
    const now = new Date();
    const currentMonth = now.getMonth() + 1; // JavaScript months are 0-based
    const currentDay = now.getDate();
    const currentYear = now.getFullYear();
    const currentHour = now.getHours();
    const currentMinute = now.getMinutes(); // No more rounding to 5 minutes

    // Clear existing options
    monthSelect.innerHTML = '';
    daySelect.innerHTML = '';
    yearSelect.innerHTML = '';
    hourSelect.innerHTML = '';
    minuteSelect.innerHTML = '';

    // Populate months
    const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    months.forEach((month, index) => {
        const option = document.createElement('option');
        option.value = index + 1;
        option.textContent = month;
        monthSelect.appendChild(option);
    });
    monthSelect.value = currentMonth;

    // Populate days
    for (let i = 1; i <= 31; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i;
        daySelect.appendChild(option);
    }
    daySelect.value = currentDay;

    // Populate years
    for (let i = currentYear; i <= currentYear + 10; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i;
        yearSelect.appendChild(option);
    }
    yearSelect.value = currentYear;

    // Populate hours
    for (let i = 0; i < 24; i++) {
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i.toString().padStart(2, '0');
        hourSelect.appendChild(option);
    }
    hourSelect.value = currentHour;

    // Populate minutes - now with 1-minute intervals
    for (let i = 0; i < 60; i++) {  // Changed from i += 5 to i++
        const option = document.createElement('option');
        option.value = i;
        option.textContent = i.toString().padStart(2, '0');
        minuteSelect.appendChild(option);
    }
    minuteSelect.value = currentMinute;  // Use exact current minute
}

populateDropdowns();

function resetDatePicker() {
    const selectedDateText = document.getElementById('selectedDateText');
    selectedDateText.textContent = 'Select Unlock Date and Time';
    selectedDateText.classList.remove('text-white');
    selectedDateText.classList.add('text-gray-400');
    
    // Reset the hidden input
    document.getElementById('unlockDate').value = '';
    
    // Reset all select elements to current date/time
    const now = new Date();
    document.getElementById('monthSelect').value = now.getMonth() + 1;
    document.getElementById('daySelect').value = now.getDate();
    document.getElementById('yearSelect').value = now.getFullYear();
    document.getElementById('hourSelect').value = now.getHours();
    document.getElementById('minuteSelect').value = Math.floor(now.getMinutes() / 5) * 5;
}