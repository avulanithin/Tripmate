function bookNow() {
    const username = document.getElementById('username').value;  // Get username from a hidden field or login
    const packageName = document.getElementById('detail-name').innerText;

    if (!packageName || !username) {
        alert('Please select a package and ensure you are logged in.');
        return;
    }

    fetch('/book-package', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            username: username,       // send username from frontend
            package_name: packageName // send package name
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.message) {
            alert(data.message);
        } else {
            alert(data.error || "Booking failed.");
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("Booking failed due to an error.");
    });
}
