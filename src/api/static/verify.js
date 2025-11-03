// Verification Page Logic

class VerifyPage {
    constructor() {
        this.form = document.getElementById('verify-form');
        this.otpInput = document.getElementById('otp-code');
        this.submitBtn = document.getElementById('submit-btn');
        this.errorMessage = document.getElementById('error-message');
        this.successMessage = document.getElementById('success-message');
        this.userEmailSpan = document.getElementById('user-email');

        this.email = null;

        this.init();
    }

    async init() {
        // Load instance configuration
        await this.loadConfig();

        // Get email from session storage
        this.email = sessionStorage.getItem('verify_email');

        if (!this.email) {
            // No email found, redirect to login
            window.location.href = '/static/login.html';
            return;
        }

        // Display email
        this.userEmailSpan.textContent = this.email;

        // Check if already authenticated
        await this.checkAuth();

        // Setup event listeners
        this.setupEventListeners();
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            // Update page title and headers
            document.title = `Verify - ${config.instance_name}`;
            document.getElementById('instance-name').textContent = config.instance_name;
            document.getElementById('instance-description').textContent = config.instance_description;
        } catch (error) {
            console.error('Error loading config:', error);
        }
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

    setupEventListeners() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));

        // Auto-format OTP input (numbers only)
        this.otpInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/[^0-9]/g, '');
            this.hideMessages();
        });

        // Auto-submit when 6 digits entered
        this.otpInput.addEventListener('input', () => {
            if (this.otpInput.value.length === 6) {
                this.form.dispatchEvent(new Event('submit'));
            }
        });
    }

    async handleSubmit(e) {
        e.preventDefault();

        const otpCode = this.otpInput.value.trim();

        if (!otpCode) {
            this.showError('Please enter the 6-digit code');
            return;
        }

        if (otpCode.length !== 6) {
            this.showError('Code must be 6 digits');
            return;
        }

        this.setLoading(true);
        this.hideMessages();

        try {
            const response = await fetch('/api/auth/verify-otp', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    email: this.email,
                    otp_code: otpCode,
                }),
            });

            // Check response status first
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                this.showError(errorData.message || `Server error: ${response.status}`);
                this.otpInput.value = '';
                this.otpInput.focus();
                return;
            }

            const data = await response.json();

            if (data.success) {
                // Success! Clear stored email
                sessionStorage.removeItem('verify_email');

                // Show success message
                this.showSuccess(data.message);

                // Important: Wait for success message to render before redirect
                // This prevents NS_BINDING_ABORTED in Firefox
                await new Promise(resolve => setTimeout(resolve, 1500));

                // Redirect to chat
                window.location.href = '/';
            } else {
                this.showError(data.message || 'Invalid code');
                this.otpInput.value = '';
                this.otpInput.focus();
            }
        } catch (error) {
            console.error('Error verifying OTP:', error);
            // Check if it's a network abort (which might be normal during redirect)
            if (error.name === 'AbortError') {
                console.log('Request aborted - this is expected during redirect');
                return;
            }
            this.showError('Network error. Please check your connection and try again.');
        } finally {
            this.setLoading(false);
        }
    }

    setLoading(loading) {
        if (loading) {
            this.submitBtn.style.display = 'flex';
            this.submitBtn.disabled = true;
            this.submitBtn.classList.add('loading');
            this.otpInput.disabled = true;
        } else {
            this.submitBtn.style.display = 'none';
            this.submitBtn.disabled = false;
            this.submitBtn.classList.remove('loading');
            this.otpInput.disabled = false;
        }
    }

    showError(message) {
        this.errorMessage.textContent = message;
        this.errorMessage.style.display = 'block';
        this.successMessage.style.display = 'none';
    }

    showSuccess(message) {
        this.successMessage.textContent = message;
        this.successMessage.style.display = 'block';
        this.errorMessage.style.display = 'none';
    }

    hideMessages() {
        this.errorMessage.style.display = 'none';
        this.successMessage.style.display = 'none';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new VerifyPage();
});
