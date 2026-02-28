/**
 * Landing page logic for multi-tenant mode.
 *
 * Checks if user is already authenticated and redirects accordingly.
 * Loads instance configuration for display.
 * Handles ?code=XYZ query param from QR invite links.
 */

class LandingPage {
    constructor() {
        this.init();
    }

    async init() {
        await this.checkAuth();
        await this.loadConfig();
        this.checkInviteCode();
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/status', {
                credentials: 'include',
            });
            const data = await response.json();

            if (data.authenticated && !data.onboarding_verified) {
                // Already logged in with a tenant — go to main app
                window.location.href = '/';
                return;
            }
        } catch (e) {
            // Not authenticated, stay on landing
        }
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            document.getElementById('instance-name').textContent = config.instance_name || 'Berengario';
            document.getElementById('instance-description').textContent = config.instance_description || '';
            document.title = `Welcome - ${config.instance_name || 'Berengario'}`;
        } catch (e) {
            // Use defaults
        }
    }

    checkInviteCode() {
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        if (code) {
            window.location.href = `/static/onboarding.html?mode=join&code=${encodeURIComponent(code)}`;
        }
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => new LandingPage());
