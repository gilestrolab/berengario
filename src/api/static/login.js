// Login Page Logic

class LoginPage {
    constructor() {
        this.form = document.getElementById('login-form');
        this.emailInput = document.getElementById('email');
        this.submitBtn = document.getElementById('submit-btn');
        this.errorMessage = document.getElementById('error-message');
        this.infoMessage = document.getElementById('info-message');

        this.init();
    }

    async init() {
        // Check if already authenticated
        await this.checkAuth();

        // Load KB stats
        await this.loadStats();

        // Setup event listeners
        this.setupEventListeners();
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/status', {
                credentials: 'include',
            });
            const data = await response.json();

            if (data.authenticated) {
                // Already authenticated, redirect to chat
                window.location.href = '/';
            }
        } catch (error) {
            console.error('Error checking auth:', error);
        }
    }

    async loadStats() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();

            document.getElementById('kb-documents').textContent = data.unique_documents;
            document.getElementById('kb-chunks').textContent = data.total_chunks;
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    setupEventListeners() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        // Auto-format email input
        this.emailInput.addEventListener('input', () => {
            this.hideMessages();
        });
    }

    async handleSubmit(e) {
        e.preventDefault();

        const email = this.emailInput.value.trim();

        if (!email) {
            this.showError('Please enter your email address');
            return;
        }

        if (!this.isValidEmail(email)) {
            this.showError('Please enter a valid email address');
            return;
        }

        this.setLoading(true);
        this.hideMessages();

        try {
            const response = await fetch('/api/auth/request-otp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email }),
            });

            const data = await response.json();

            if (data.success) {
                // Store email for verification page
                sessionStorage.setItem('verify_email', email);

                // Show success message briefly
                this.showInfo(data.message);

                // Redirect to verification page
                setTimeout(() => {
                    window.location.href = '/static/verify.html';
                }, 1500);
            } else {
                this.showError(data.message || 'Failed to send login code');
            }
        } catch (error) {
            console.error('Error requesting OTP:', error);
            this.showError('Network error. Please check your connection and try again.');
        } finally {
            this.setLoading(false);
        }
    }

    isValidEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    setLoading(loading) {
        if (loading) {
            this.submitBtn.disabled = true;
            this.submitBtn.classList.add('loading');
            this.emailInput.disabled = true;
        } else {
            this.submitBtn.disabled = false;
            this.submitBtn.classList.remove('loading');
            this.emailInput.disabled = false;
        }
    }

    showError(message) {
        this.errorMessage.textContent = message;
        this.errorMessage.style.display = 'block';
        this.infoMessage.style.display = 'none';
    }

    showInfo(message) {
        this.infoMessage.textContent = message;
        this.infoMessage.style.display = 'block';
        this.errorMessage.style.display = 'none';
    }

    hideMessages() {
        this.errorMessage.style.display = 'none';
        this.infoMessage.style.display = 'none';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new LoginPage();
});
