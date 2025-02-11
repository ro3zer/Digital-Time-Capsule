document.addEventListener('DOMContentLoaded', function() {
    const datePickerDisplay = document.getElementById('datePickerDisplay');
    const customDatePicker = document.getElementById('customDatePicker');
    const selectedDateText = document.getElementById('selectedDateText');
    const cancelButton = document.getElementById('cancelDatePicker');
    const confirmButton = document.getElementById('confirmDatePicker');
    const hiddenInput = document.getElementById('unlockDate');

    // Populate dropdowns
    function populateDropdowns() {
        const monthSelect = document.getElementById('monthSelect');
        const daySelect = document.getElementById('daySelect');
        const yearSelect = document.getElementById('yearSelect');
        const hourSelect = document.getElementById('hourSelect');
        const minuteSelect = document.getElementById('minuteSelect');

        // Populate months
        const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
        months.forEach((month, index) => {
            const option = document.createElement('option');
            option.value = index + 1;
            option.textContent = month;
            monthSelect.appendChild(option);
        });

        // Populate days
        for (let i = 1; i <= 31; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i;
            daySelect.appendChild(option);
        }

        // Populate years
        const currentYear = new Date().getFullYear();
        for (let i = currentYear; i <= currentYear + 10; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i;
            yearSelect.appendChild(option);
        }

        // Populate hours
        for (let i = 0; i < 24; i++) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i.toString().padStart(2, '0');
            hourSelect.appendChild(option);
        }

        // Populate minutes
        for (let i = 0; i < 60; i += 5) {
            const option = document.createElement('option');
            option.value = i;
            option.textContent = i.toString().padStart(2, '0');
            minuteSelect.appendChild(option);
        }
    }

    populateDropdowns();

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
            const selectedDate = new Date(year, month - 1, day, hour, minute);
            const formattedDate = selectedDate.toLocaleString('en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true
            });

            selectedDateText.textContent = formattedDate;
            selectedDateText.classList.remove('text-gray-400');
            selectedDateText.classList.add('text-white');

            // Set the hidden input value for form submission
            hiddenInput.value = selectedDate.toISOString().slice(0, 16);

            customDatePicker.classList.add('hidden');
        } else {
            alert('Please select all date and time components');
        }
    });

    // Close picker if clicked outside
    document.addEventListener('click', function(event) {
        if (!datePickerDisplay.contains(event.target) && !customDatePicker.contains(event.target)) {
            customDatePicker.classList.add('hidden');
        }
    });
});