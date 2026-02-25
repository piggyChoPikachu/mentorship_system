// ===== Registration Script =====
const registrationForm = document.getElementById('registrationForm');
const messageDiv = document.getElementById('message');

if (registrationForm) {
    registrationForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const role = document.getElementById('role').value;

        const userData = { username, email, password, role };

        fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userData)
        })
        .then(response => response.json().then(data => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
            if (ok) {
                messageDiv.innerHTML = '<div class="success">Registration successful! Redirecting to login page...</div>';
                setTimeout(() => { window.location.href = 'login'; }, 2000);
            } else {
                messageDiv.innerHTML = '<div class="error">Registration failed: ' + (data.error || 'Unknown error') + '</div>';
            }
        })
        .catch(error => {
            messageDiv.innerHTML = '<div class="error">Registration failed: ' + error.message + '</div>';
        });
    });
}

// ===== Login Script =====
const loginBtn = document.getElementById("login-btn");
const errorDiv = document.getElementById("error");

if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
        const identifier = document.getElementById("username").value.trim(); // can be username or email
        const password = document.getElementById("password").value;

        if (!identifier || !password) {
            errorDiv.textContent = "Please enter both username/email and password.";
            return;
        }

        try {
            const response = await fetch("/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ identifier, password })
            });

            const data = await response.json();

            if (response.ok) {
                // alert("Login successful! User ID: " + data.user_id);
                window.location.href = "/profile"; // redirect to home/dashboard
            } else {
                errorDiv.textContent = data.error || "Login failed.";
            }
        } catch (err) {
            console.error(err);
            errorDiv.textContent = "Server error. Try again later.";
        }
    });
}




// ===== profile person table edit Script =====

