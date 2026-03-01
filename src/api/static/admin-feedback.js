/**
 * Feedback Analytics Manager
 */
class FeedbackAnalytics {
    constructor() {
        this.selectedDays = 7;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Time range buttons
        document.querySelectorAll('.feedback-time-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.feedback-time-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.selectedDays = e.target.dataset.days === 'all' ? null : parseInt(e.target.dataset.days);
                this.loadAnalytics();
            });
        });

        // Load analytics when feedback tab is shown
        const feedbackTab = document.querySelector('[data-tab="feedback"]');
        if (feedbackTab) {
            feedbackTab.addEventListener('click', () => {
                setTimeout(() => this.loadAnalytics(), 100);
            });
        }
    }

    async loadAnalytics() {
        try {
            const params = new URLSearchParams();
            if (this.selectedDays) {
                params.append('days', this.selectedDays);
            }

            const response = await fetch(`/api/admin/feedback/analytics?${params}`, {
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error('Failed to load feedback analytics');
            }

            const data = await response.json();
            this.displayAnalytics(data);
        } catch (error) {
            console.error('Error loading feedback analytics:', error);
            adminPanel.showToast('Failed to load feedback analytics', 'error');
        }
    }

    displayAnalytics(data) {
        // Update overview stats
        document.getElementById('feedback-total').textContent = data.overview.total_feedback.toLocaleString();
        document.getElementById('feedback-positive').textContent = data.overview.positive_count.toLocaleString();
        document.getElementById('feedback-negative').textContent = data.overview.negative_count.toLocaleString();
        document.getElementById('feedback-rate').textContent = data.overview.positive_rate + '%';

        // Display negative responses
        this.displayNegativeResponses(data.negative_responses);
    }

    displayNegativeResponses(responses) {
        const container = document.getElementById('negative-responses-list');

        if (responses.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">No negative feedback in this time period 🎉</p>';
            return;
        }

        container.innerHTML = responses.map(item => `
            <div class="negative-response-item" style="border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; background: var(--surface);">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 0.5rem;">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="font-size: 1.25rem;">👎</span>
                        <span style="font-weight: 600; color: var(--text-primary);">${this.escapeHtml(item.user_email)}</span>
                        <span style="padding: 0.125rem 0.5rem; background: #F5E0DC; color: #8A3630; border-radius: 0.25rem; font-size: 0.75rem;">${item.channel}</span>
                    </div>
                    <span style="color: var(--text-secondary); font-size: 0.875rem;">${this.formatDate(item.submitted_at)}</span>
                </div>
                <div style="background: var(--background); padding: 0.75rem; border-radius: 0.375rem; margin-bottom: 0.5rem; font-size: 0.875rem; color: var(--text-secondary);">
                    ${this.escapeHtml(item.response_content)}
                </div>
                ${item.comment ? `
                    <div style="padding: 0.5rem; border-left: 3px solid #A3423A; background: #F5E0DC; border-radius: 0.25rem; font-size: 0.875rem;">
                        <strong>User Comment:</strong> ${this.escapeHtml(item.comment)}
                    </div>
                ` : ''}
            </div>
        `).join('');
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    refresh() {
        this.loadAnalytics();
        adminPanel.showToast('Feedback analytics refreshed', 'success');
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize all admin panel components when page loads
const adminPanel = new AdminPanel();
const usageAnalytics = new UsageAnalytics();
const feedbackAnalytics = new FeedbackAnalytics();

// Expose to global scope for inline onclick handlers
window.adminPanel = adminPanel;
window.usageAnalytics = usageAnalytics;
window.feedbackAnalytics = feedbackAnalytics;
