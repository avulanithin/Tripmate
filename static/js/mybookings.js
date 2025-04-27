function fetchMyBookings() {
    const username = document.getElementById('username').value;  // username field

    fetch('/my-bookings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: username })
    })
    .then(response => response.json())
    .then(data => {
        if (data.packages) {
            const bookingsList = document.getElementById('bookings-list');
            bookingsList.innerHTML = '';

            data.packages.forEach(pkg => {
                const listItem = document.createElement('li');
                listItem.innerHTML = `<strong>${pkg.name}</strong> - ₹${pkg.price} for ${pkg.duration} days<br>${pkg.description}`;
                bookingsList.appendChild(listItem);
            });
        } else {
            alert(data.error || "No bookings found.");
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Failed to fetch bookings.");
    });
}
