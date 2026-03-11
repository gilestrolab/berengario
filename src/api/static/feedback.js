/**
 * Feedback page JavaScript
 */

class FeedbackPage {
    constructor() {
        this.feedbackForm = document.getElementById('feedback-form');
        this.successMessage = document.getElementById('success-message');
        this.submitBtn = document.getElementById('submit-btn');
        this.commentSection = document.getElementById('comment-section');
        this.commentInput = document.getElementById('comment');
        this.errorMessage = document.getElementById('error-message');

        this.selectedRating = null;
        this.token = null;
        this.messageId = null;

        this.init();
    }

    init() {
        // Parse URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        this.token = urlParams.get('token');
        const rating = urlParams.get('rating');

        if (!this.token) {
            this.showError('Invalid feedback link. Please use the link from your email.');
            return;
        }

        // Decode token to get message_id
        this.decodeToken();

        // Set up event listeners
        this.setupEventListeners();

        // If rating is pre-selected (from email link), select it
        if (rating) {
            const option = document.querySelector(`.feedback-option[data-rating="${rating}"]`);
            if (option) {
                this.selectRating(rating);
                // For positive feedback, auto-submit
                if (rating === 'positive') {
                    setTimeout(() => this.submitFeedback(), 500);
                }
            }
        }

        // Load config for instance name
        this.loadConfig();
    }

    decodeToken() {
        try {
            // Decode base64 token to get optional tenant slug and message_id
            // Token format: base64("slug:message_id") or base64("message_id")
            const decoded = atob(this.token.replace(/_/g, '/').replace(/-/g, '+'));
            if (decoded.includes(':')) {
                const lastColon = decoded.lastIndexOf(':');
                this.messageId = parseInt(decoded.substring(lastColon + 1));
            } else {
                this.messageId = parseInt(decoded);
            }
        } catch (error) {
            console.error('Failed to decode token:', error);
            this.showError('Invalid feedback link. Please use the link from your email.');
        }
    }

    setupEventListeners() {
        // Feedback option selection
        document.querySelectorAll('.feedback-option').forEach(option => {
            option.addEventListener('click', () => {
                const rating = option.dataset.rating;
                this.selectRating(rating);
            });
        });

        // Submit button
        this.submitBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.submitFeedback();
        });
    }

    selectRating(rating) {
        this.selectedRating = rating;

        // Update UI
        document.querySelectorAll('.feedback-option').forEach(option => {
            option.classList.remove('selected');
        });
        const selectedOption = document.querySelector(`.feedback-option[data-rating="${rating}"]`);
        if (selectedOption) {
            selectedOption.classList.add('selected');
        }

        // Show comment section for negative feedback
        if (rating === 'negative') {
            this.commentSection.classList.add('visible');
            this.submitBtn.style.display = 'block';
        } else {
            this.commentSection.classList.remove('visible');
            this.commentInput.value = '';
        }
    }

    async submitFeedback() {
        if (!this.selectedRating || !this.messageId) {
            this.showError('Please select a rating.');
            return;
        }

        // Show loading state
        this.submitBtn.disabled = true;
        const buttonText = this.submitBtn.querySelector('.button-text');
        const buttonSpinner = this.submitBtn.querySelector('.button-spinner');
        buttonText.style.display = 'none';
        buttonSpinner.style.display = 'inline-block';

        try {
            const response = await fetch('/api/feedback/email', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    token: this.token,
                    message_id: this.messageId,
                    is_positive: this.selectedRating === 'positive',
                    comment: this.commentInput.value || null,
                }),
            });

            const data = await response.json();

            if (data.success) {
                // Show success message
                this.feedbackForm.style.display = 'none';
                this.successMessage.style.display = 'block';
            } else {
                this.showError(data.message || 'Failed to submit feedback. Please try again.');
                this.submitBtn.disabled = false;
                buttonText.style.display = 'inline';
                buttonSpinner.style.display = 'none';
            }
        } catch (error) {
            console.error('Error submitting feedback:', error);
            this.showError('Error submitting feedback. Please try again.');
            this.submitBtn.disabled = false;
            buttonText.style.display = 'inline';
            buttonSpinner.style.display = 'none';
        }
    }

    showError(message) {
        this.errorMessage.textContent = message;
        this.errorMessage.style.display = 'block';
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            // Update instance name if available
            const instanceNameEl = document.getElementById('instance-name');
            if (instanceNameEl && config.instance_name) {
                instanceNameEl.textContent = `Powered by ${config.instance_name}`;
            }
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => new FeedbackPage());
} else {
    new FeedbackPage();
}
