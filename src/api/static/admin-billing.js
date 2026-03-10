/**
 * Billing tab — plan info, usage stats, Paddle checkout, subscription management.
 *
 * Extends AdminPanel with billing-related methods.
 * Loaded after admin.js in admin.html.
 */

(function () {
    'use strict';

    // State
    let billingConfig = null;
    let planInfo = null;
    let paddleReady = false;

    /**
     * Load billing data when tab is first shown.
     */
    AdminPanel.prototype.loadBilling = async function () {
        await Promise.all([
            this.loadPlanInfo(),
            this.loadBillingConfig(),
        ]);
    };

    /**
     * Fetch current plan, usage stats, and limits.
     */
    AdminPanel.prototype.loadPlanInfo = async function () {
        const container = document.getElementById('billing-plan-info');
        if (!container) return;

        try {
            const resp = await fetch('/api/billing/plan-info', { credentials: 'include' });
            if (!resp.ok) throw new Error('Failed to load plan info');
            planInfo = await resp.json();
            this.renderPlanInfo(planInfo);
        } catch (e) {
            console.error('Error loading plan info:', e);
            container.innerHTML = '<p style="color: var(--danger);">Failed to load billing information.</p>';
        }
    };

    /**
     * Fetch Paddle checkout configuration (admin only).
     */
    AdminPanel.prototype.loadBillingConfig = async function () {
        try {
            const resp = await fetch('/api/billing/checkout-config', { credentials: 'include' });
            if (resp.ok) {
                billingConfig = await resp.json();
                this.initPaddle();
                this.renderPlanCards();
            }
        } catch (e) {
            console.error('Failed to load billing config:', e);
        }
    };

    /**
     * Initialize Paddle.js for checkout overlays.
     */
    AdminPanel.prototype.initPaddle = function () {
        if (!billingConfig || !billingConfig.client_token || typeof Paddle === 'undefined') return;
        try {
            if (billingConfig.environment === 'sandbox') {
                Paddle.Environment.set('sandbox');
            }
            Paddle.Initialize({
                token: billingConfig.client_token,
                eventCallback: (ev) => {
                    if (ev.name === 'checkout.completed') {
                        this.showToast('Subscription activated! Reloading...', 'success');
                        setTimeout(() => window.location.reload(), 2000);
                    }
                }
            });
            paddleReady = true;
            this.fetchPaddlePrices();
        } catch (e) {
            console.error('Paddle init failed:', e);
        }
    };

    /**
     * Fetch localised prices from Paddle PricePreview.
     */
    AdminPanel.prototype.fetchPaddlePrices = async function () {
        if (!billingConfig) return;
        const priceIds = [
            billingConfig.price_id_lite,
            billingConfig.price_id_team,
            billingConfig.price_id_department,
        ].filter(Boolean);
        if (priceIds.length === 0) return;

        try {
            const result = await Paddle.PricePreview({
                items: priceIds.map(id => ({ priceId: id, quantity: 1 })),
            });
            for (const item of result.data.details.lineItems) {
                const formatted = item.formattedTotals.subtotal;
                const el = document.querySelector(`[data-price-id="${item.price.id}"]`);
                if (el) el.textContent = formatted + '/year';
            }
        } catch (e) {
            console.error('Paddle PricePreview failed:', e);
        }
    };

    /**
     * Render current plan info with usage stats.
     */
    AdminPanel.prototype.renderPlanInfo = function (data) {
        const container = document.getElementById('billing-plan-info');
        if (!container) return;

        const isTrialing = data.is_trialing;
        const trialEnd = data.trial_ends_at ? new Date(data.trial_ends_at) : null;
        const now = new Date();
        const daysLeft = trialEnd ? Math.max(0, Math.ceil((trialEnd - now) / (1000 * 60 * 60 * 24))) : 0;

        // Status badge
        let statusBadge = '';
        if (isTrialing) {
            statusBadge = `<span class="billing-badge billing-badge-trial">Trial — ${daysLeft} days left</span>`;
        } else if (data.subscription_status === 'active') {
            statusBadge = '<span class="billing-badge billing-badge-active">Active</span>';
        } else if (data.subscription_status === 'past_due') {
            statusBadge = '<span class="billing-badge billing-badge-warning">Past Due</span>';
        } else if (data.subscription_status === 'cancelled') {
            statusBadge = '<span class="billing-badge billing-badge-cancelled">Cancelled</span>';
        }

        // Scheduled change notice
        let scheduledNotice = '';
        if (data.scheduled_change && data.scheduled_change.action === 'cancel') {
            scheduledNotice = `
                <div class="billing-notice billing-notice-warning">
                    Your subscription will be cancelled at the end of the current billing period.
                </div>`;
        }

        // Query usage bar
        const queryPct = data.query_limit > 0 ? Math.min(100, (data.queries_this_month / data.query_limit) * 100) : 0;
        const queryBarClass = queryPct >= 90 ? 'billing-bar-danger' : queryPct >= 70 ? 'billing-bar-warning' : '';

        // Storage usage bar
        const storagePct = data.storage_limit_mb > 0 ? Math.min(100, (data.storage_used_mb / data.storage_limit_mb) * 100) : 0;
        const storageBarClass = storagePct >= 90 ? 'billing-bar-danger' : storagePct >= 70 ? 'billing-bar-warning' : '';

        const storageUsedDisplay = data.storage_used_mb >= 1024
            ? (data.storage_used_mb / 1024).toFixed(1) + ' GB'
            : data.storage_used_mb.toFixed(0) + ' MB';
        const storageLimitDisplay = data.storage_limit_mb >= 1024
            ? (data.storage_limit_mb / 1024).toFixed(0) + ' GB'
            : data.storage_limit_mb + ' MB';

        container.innerHTML = `
            <div class="billing-current-plan">
                <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
                    <h4 style="margin: 0;">Current Plan: ${data.plan_display}</h4>
                    ${statusBadge}
                </div>
                ${scheduledNotice}

                <div class="billing-usage-grid">
                    <div class="billing-usage-item">
                        <div class="billing-usage-label">
                            <span>Queries this month</span>
                            <span>${data.queries_this_month.toLocaleString()} / ${data.query_limit.toLocaleString()}</span>
                        </div>
                        <div class="billing-bar">
                            <div class="billing-bar-fill ${queryBarClass}" style="width: ${queryPct}%"></div>
                        </div>
                    </div>

                    <div class="billing-usage-item">
                        <div class="billing-usage-label">
                            <span>Document storage</span>
                            <span>${storageUsedDisplay} / ${storageLimitDisplay}</span>
                        </div>
                        <div class="billing-bar">
                            <div class="billing-bar-fill ${storageBarClass}" style="width: ${storagePct}%"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    };

    /**
     * Render plan comparison cards.
     */
    AdminPanel.prototype.renderPlanCards = function () {
        const container = document.getElementById('billing-plan-cards');
        if (!container || !planInfo) return;

        const plans = planInfo.plans || [];
        const currentPlan = planInfo.plan;
        const status = planInfo.subscription_status;

        let cardsHtml = '';
        for (const plan of plans) {
            const isCurrent = plan.tier === currentPlan && status !== 'trialing';
            const isTrialPlan = status === 'trialing' && plan.tier === 'department';
            const priceId = billingConfig
                ? billingConfig[`price_id_${plan.tier}`]
                : '';

            let badge = '';
            if (isCurrent) {
                badge = '<span class="billing-badge billing-badge-active">Current Plan</span>';
            } else if (isTrialPlan) {
                badge = '<span class="billing-badge billing-badge-trial">Trial</span>';
            }
            if (plan.tier === 'team') {
                badge += '<span class="billing-badge billing-badge-popular">Most Popular</span>';
            }

            const fallbackPrice = plan.fallback_price_gbp
                ? `£${plan.fallback_price_gbp}/year`
                : '';

            let actionButton = '';
            if (isCurrent) {
                actionButton = '<button class="billing-btn billing-btn-current" disabled>Current Plan</button>';
            } else if (isTrialPlan) {
                actionButton = '<button class="billing-btn billing-btn-current" disabled>Trial Active</button>';
            } else {
                const label = _isUpgrade(plan.tier, currentPlan) ? 'Upgrade' : 'Switch';
                actionButton = `<button class="billing-btn billing-btn-upgrade" onclick="adminPanel.openCheckout('${plan.tier}')">${label} to ${plan.display_name}</button>`;
            }

            cardsHtml += `
                <div class="billing-plan-card ${isCurrent || isTrialPlan ? 'billing-plan-card-active' : ''}">
                    <div class="billing-plan-header">
                        <h4>${plan.display_name}</h4>
                        <div>${badge}</div>
                    </div>
                    <div class="billing-plan-price" data-price-id="${priceId}">${fallbackPrice}</div>
                    <ul class="billing-plan-features">
                        <li>${plan.queries_per_month.toLocaleString()} queries/month</li>
                        <li>${plan.storage_display} document storage</li>
                        <li>Unlimited users</li>
                        <li>Email & web interface</li>
                    </ul>
                    ${actionButton}
                </div>
            `;
        }

        // Management buttons
        let managementHtml = '';
        if (billingConfig && billingConfig.paddle_subscription_id) {
            managementHtml = `
                <div class="billing-management" style="margin-top: 1.5rem;">
                    <button class="billing-btn billing-btn-manage" onclick="adminPanel.openBillingPortal()">
                        Manage Billing
                    </button>
                    <button class="billing-btn billing-btn-danger" onclick="adminPanel.downgradeToFree()">
                        Cancel Subscription
                    </button>
                </div>
            `;
        } else if (status === 'trialing' || status === 'cancelled') {
            managementHtml = '';
        }

        container.innerHTML = `
            <div class="billing-plans-grid">${cardsHtml}</div>
            ${managementHtml}
        `;
    };

    /**
     * Open Paddle checkout overlay.
     */
    AdminPanel.prototype.openCheckout = function (planTier) {
        if (!paddleReady || !billingConfig) {
            this.showToast('Payment system not ready. Please refresh and try again.', 'error');
            return;
        }

        const priceId = billingConfig[`price_id_${planTier}`];
        if (!priceId) {
            this.showToast('Price not configured for this plan.', 'error');
            return;
        }

        const checkoutSettings = {
            items: [{ priceId: priceId, quantity: 1 }],
            settings: {
                displayMode: 'overlay',
                theme: 'light',
            },
            customData: {
                tenant_id: billingConfig.tenant_id,
            },
        };

        if (billingConfig.email) {
            checkoutSettings.customer = { email: billingConfig.email };
        }
        if (billingConfig.paddle_customer_id) {
            checkoutSettings.customer = checkoutSettings.customer || {};
            checkoutSettings.customer.id = billingConfig.paddle_customer_id;
        }

        try {
            Paddle.Checkout.open(checkoutSettings);
        } catch (e) {
            console.error('Checkout open failed:', e);
            this.showToast('Failed to open checkout. Please try again.', 'error');
        }
    };

    /**
     * Open Paddle billing portal (update payment / cancel).
     */
    AdminPanel.prototype.openBillingPortal = async function () {
        try {
            const resp = await fetch('/api/billing/portal', { credentials: 'include' });
            if (resp.ok) {
                const urls = await resp.json();
                const url = urls.update_payment_method || urls.cancel;
                if (url) window.open(url, '_blank');
            } else {
                const err = await resp.json();
                this.showToast(err.detail || 'Could not open billing portal', 'error');
            }
        } catch (e) {
            console.error('Portal error:', e);
            this.showToast('Failed to open billing portal.', 'error');
        }
    };

    /**
     * Downgrade to free plan (cancel subscription).
     */
    AdminPanel.prototype.downgradeToFree = async function () {
        if (!confirm('Are you sure you want to cancel your subscription? Your plan will downgrade to Free and you will lose access to queries.')) {
            return;
        }

        try {
            const resp = await fetch('/api/billing/downgrade-to-free', {
                method: 'POST',
                credentials: 'include',
            });
            const data = await resp.json();
            if (resp.ok) {
                this.showToast(data.detail, 'success');
                setTimeout(() => window.location.reload(), 1500);
            } else {
                this.showToast(data.detail || 'Failed to downgrade.', 'error');
            }
        } catch (e) {
            console.error('Downgrade error:', e);
            this.showToast('Failed to cancel subscription.', 'error');
        }
    };

    /**
     * Determine if switching to targetTier is an upgrade from currentTier.
     */
    function _isUpgrade(targetTier, currentTier) {
        const order = { free: 0, lite: 1, team: 2, department: 3 };
        return (order[targetTier] || 0) > (order[currentTier] || 0);
    }

    // Hook into tab switching — load billing data on first visit
    const origSwitchTab = AdminPanel.prototype.switchTab;
    AdminPanel.prototype.switchTab = function (tabName) {
        origSwitchTab.call(this, tabName);
        if (tabName === 'billing' && !planInfo) {
            this.loadBilling();
        }
    };

})();
