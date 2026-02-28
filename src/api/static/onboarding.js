/**
 * Onboarding wizard for multi-tenant mode.
 *
 * Handles both Create Account and Join Team flows.
 * Uses URL params: ?mode=create|join and ?code=XYZ
 */

class OnboardingPage {
    constructor() {
        this.mode = null; // 'create' or 'join'
        this.email = null;
        this.inviteCode = null;
        this.teamName = null;
        this.requiresApproval = false;
        this.slug = null;
        this.slugTimeout = null;
        this.steps = [];
        this.currentStep = 0;

        this.init();
    }

    async init() {
        await this.loadConfig();
        this.parseParams();
        this.setupSteps();
        this.setupEventListeners();
        await this.checkExistingSession();
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();
            document.getElementById('instance-name').textContent = config.instance_name || 'Berengario';
            document.title = `Get Started - ${config.instance_name || 'Berengario'}`;
        } catch (e) {
            // Use defaults
        }
    }

    parseParams() {
        const params = new URLSearchParams(window.location.search);
        this.mode = params.get('mode') || 'create';
        this.inviteCode = params.get('code') || null;
    }

    setupSteps() {
        if (this.mode === 'create') {
            this.steps = ['step-email', 'step-otp', 'step-details', 'step-success'];
        } else {
            // Join flow: code first, then email/otp, then join
            if (this.inviteCode) {
                // Pre-filled code: validate, then email, otp, join
                this.steps = ['step-code', 'step-email', 'step-otp', 'step-join', 'step-success'];
            } else {
                this.steps = ['step-code', 'step-email', 'step-otp', 'step-join', 'step-success'];
            }
        }
        this.renderProgress();
        this.showStep(0);

        // Pre-fill invite code if provided
        if (this.inviteCode && this.mode === 'join') {
            document.getElementById('invite-code').value = this.inviteCode;
        }
    }

    renderProgress() {
        const container = document.getElementById('wizard-progress');
        container.innerHTML = '';
        // Don't count success step in progress
        const visibleSteps = this.steps.length - 1;
        for (let i = 0; i < visibleSteps; i++) {
            const dot = document.createElement('div');
            dot.className = 'wizard-dot';
            if (i < this.currentStep) dot.classList.add('completed');
            if (i === this.currentStep) dot.classList.add('active');
            container.appendChild(dot);
        }
    }

    showStep(index) {
        this.currentStep = index;
        document.querySelectorAll('.wizard-step').forEach(el => el.classList.remove('active'));
        const stepEl = document.getElementById(this.steps[index]);
        if (stepEl) stepEl.classList.add('active');
        this.renderProgress();

        // Auto-focus first input
        const input = stepEl?.querySelector('input');
        if (input) setTimeout(() => input.focus(), 100);
    }

    nextStep() {
        if (this.currentStep < this.steps.length - 1) {
            this.showStep(this.currentStep + 1);
        }
    }

    async checkExistingSession() {
        try {
            const resp = await fetch('/api/auth/status', { credentials: 'include' });
            const data = await resp.json();

            if (data.authenticated && data.onboarding_verified) {
                // Already verified — skip email/OTP steps
                this.email = data.email;
                if (this.mode === 'create') {
                    this.showStep(this.steps.indexOf('step-details'));
                } else if (this.inviteCode) {
                    // Auto-validate the pre-filled code
                    await this.validateCode(this.inviteCode);
                    if (this.teamName) {
                        this.showStep(this.steps.indexOf('step-join'));
                    }
                }
            } else if (data.authenticated && !data.onboarding_verified && data.tenant_id) {
                // Fully authenticated with tenant — go to main
                window.location.href = '/';
            }
        } catch (e) {
            // Not authenticated, start from beginning
        }
    }

    setupEventListeners() {
        // Email form
        document.getElementById('email-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.requestOTP();
        });

        // OTP form
        document.getElementById('otp-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.verifyOTP();
        });

        // Code form
        document.getElementById('code-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            const code = document.getElementById('invite-code').value.trim();
            const valid = await this.validateCode(code);
            if (valid) {
                this.inviteCode = code;
                this.nextStep();
            }
        });

        // Details form (create flow)
        document.getElementById('details-form')?.addEventListener('submit', async (e) => {
            e.preventDefault();
            await this.createTenant();
        });

        // Join button
        document.getElementById('join-btn')?.addEventListener('click', async () => {
            await this.joinTenant();
        });

        // Team name → slug auto-generation
        document.getElementById('team-name-input')?.addEventListener('input', (e) => {
            this.autoGenerateSlug(e.target.value);
        });
    }

    setLoading(btnId, loading) {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        if (loading) {
            btn.classList.add('loading');
            btn.disabled = true;
        } else {
            btn.classList.remove('loading');
            btn.disabled = false;
        }
    }

    showError(id, message) {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = message;
            el.style.display = 'block';
        }
    }

    hideError(id) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    }

    async requestOTP() {
        const email = document.getElementById('email').value.trim();
        if (!email) return;

        this.hideError('email-error');
        this.setLoading('email-btn', true);

        try {
            const resp = await fetch('/api/auth/request-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email }),
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                this.email = email;
                document.getElementById('otp-email-display').textContent = email;
                this.nextStep();
            } else {
                this.showError('email-error', data.message);
            }
        } catch (e) {
            this.showError('email-error', 'Network error. Please try again.');
        } finally {
            this.setLoading('email-btn', false);
        }
    }

    async verifyOTP() {
        const code = document.getElementById('otp-code').value.trim();
        if (!code) return;

        this.hideError('otp-error');
        this.setLoading('otp-btn', true);

        try {
            const resp = await fetch('/api/auth/verify-otp', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: this.email, otp_code: code }),
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                if (this.mode === 'create') {
                    this.nextStep(); // → step-details
                } else {
                    this.nextStep(); // → step-join
                    // Populate join info
                    document.getElementById('join-team-name').textContent = this.teamName;
                    document.getElementById('join-team-approval').textContent =
                        this.requiresApproval ? 'Admin approval required' : 'Open — you can join immediately';
                }
            } else {
                this.showError('otp-error', data.message);
            }
        } catch (e) {
            this.showError('otp-error', 'Network error. Please try again.');
        } finally {
            this.setLoading('otp-btn', false);
        }
    }

    async validateCode(code) {
        if (!code) return false;

        this.hideError('code-error');
        this.setLoading('code-btn', true);

        try {
            const resp = await fetch('/api/onboarding/validate-code', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code }),
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.valid) {
                this.teamName = data.tenant_name;
                this.requiresApproval = data.requires_approval;

                // Show team info
                document.getElementById('team-info').style.display = 'block';
                document.getElementById('team-name').textContent = data.tenant_name;
                document.getElementById('team-approval').textContent =
                    data.requires_approval ? 'Admin approval required to join' : 'Open to join';

                return true;
            } else {
                this.showError('code-error', 'Invalid invite code. Please check and try again.');
                return false;
            }
        } catch (e) {
            this.showError('code-error', 'Network error. Please try again.');
            return false;
        } finally {
            this.setLoading('code-btn', false);
        }
    }

    autoGenerateSlug(name) {
        if (!name || name.length < 2) {
            document.getElementById('slug-preview').style.display = 'none';
            document.getElementById('slug-status').textContent = '';
            return;
        }

        // Generate slug locally (simple version)
        const slug = name
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-|-$/g, '')
            .slice(0, 63);

        if (slug.length < 2) return;

        this.slug = slug;
        document.getElementById('slug-preview').style.display = 'block';
        document.getElementById('slug-display').textContent = slug;

        // Debounce slug check
        clearTimeout(this.slugTimeout);
        this.slugTimeout = setTimeout(() => this.checkSlug(slug), 400);
    }

    async checkSlug(slug) {
        try {
            const resp = await fetch(`/api/onboarding/slug-check?slug=${encodeURIComponent(slug)}`, {
                credentials: 'include',
            });
            const data = await resp.json();

            const statusEl = document.getElementById('slug-status');
            if (data.available) {
                statusEl.className = 'slug-status available';
                statusEl.textContent = 'Available';
            } else {
                statusEl.className = 'slug-status taken';
                statusEl.textContent = data.suggestion
                    ? `Taken. Suggestion: ${data.suggestion}`
                    : 'Taken';
                if (data.suggestion) {
                    this.slug = data.suggestion;
                    document.getElementById('slug-display').textContent = data.suggestion;
                }
            }
        } catch (e) {
            // Ignore slug check errors
        }
    }

    async createTenant() {
        const name = document.getElementById('team-name-input').value.trim();
        if (!name) return;

        this.hideError('details-error');
        this.setLoading('create-btn', true);

        const body = {
            name,
            slug: this.slug || undefined,
            organization: document.getElementById('org-input').value.trim() || undefined,
            description: document.getElementById('desc-input').value.trim() || undefined,
        };

        try {
            const resp = await fetch('/api/onboarding/create-tenant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                document.getElementById('success-title').textContent = 'Team Created!';
                document.getElementById('success-message').textContent =
                    `${data.tenant_name} is ready. Redirecting...`;
                this.showStep(this.steps.indexOf('step-success'));
                setTimeout(() => { window.location.href = '/'; }, 1500);
            } else {
                this.showError('details-error', data.message);
            }
        } catch (e) {
            this.showError('details-error', 'Network error. Please try again.');
        } finally {
            this.setLoading('create-btn', false);
        }
    }

    async joinTenant() {
        if (!this.inviteCode) return;

        this.hideError('join-error');
        this.setLoading('join-btn', true);

        try {
            const resp = await fetch('/api/onboarding/join-tenant', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: this.inviteCode }),
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                if (data.joined) {
                    document.getElementById('success-title').textContent = 'Welcome!';
                    document.getElementById('success-message').textContent =
                        'You\'ve joined the team. Redirecting...';
                    this.showStep(this.steps.indexOf('step-success'));
                    setTimeout(() => { window.location.href = '/'; }, 1500);
                } else if (data.pending_approval) {
                    this.showStep(this.steps.indexOf('step-pending') !== -1
                        ? this.steps.indexOf('step-pending')
                        : this.steps.length - 1);
                    // Show pending step (insert if not in steps)
                    document.getElementById('step-pending').classList.add('active');
                    document.querySelectorAll('.wizard-step:not(#step-pending)').forEach(
                        el => el.classList.remove('active'));
                }
            } else {
                this.showError('join-error', data.message);
            }
        } catch (e) {
            this.showError('join-error', 'Network error. Please try again.');
        } finally {
            this.setLoading('join-btn', false);
        }
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => new OnboardingPage());
