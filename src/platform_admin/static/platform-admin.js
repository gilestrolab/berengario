/**
 * Platform Admin Dashboard — vanilla JS UI logic.
 *
 * Handles tenant listing, detail view, CRUD operations, health,
 * and user management.
 */

(function () {
    'use strict';

    // ------------------------------------------------------------------
    // State
    // ------------------------------------------------------------------
    let tenants = [];
    let selectedSlug = null;

    // ------------------------------------------------------------------
    // Init
    // ------------------------------------------------------------------
    async function init() {
        // Check auth
        const status = await api('/api/auth/status');
        if (!status.authenticated) {
            window.location.href = '/static/login.html';
            return;
        }
        document.getElementById('admin-email').textContent = status.email;

        // Wire events
        document.getElementById('logout-btn').addEventListener('click', logout);
        document.getElementById('cancel-add-user').addEventListener('click', () => hideModal('add-user-modal'));
        document.getElementById('add-user-form').addEventListener('submit', handleAddUser);

        // Tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => switchTab(tab.dataset.tab));
        });



        // Load data
        await loadTenants();
    }

    // ------------------------------------------------------------------
    // API helper
    // ------------------------------------------------------------------
    async function api(url, options = {}) {
        try {
            const res = await fetch(url, {
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', ...options.headers },
                ...options,
            });
            if (res.status === 401) {
                window.location.href = '/static/login.html';
                return null;
            }
            return await res.json();
        } catch (err) {
            showToast('Connection error', 'error');
            return null;
        }
    }

    // ------------------------------------------------------------------
    // Tenant list
    // ------------------------------------------------------------------
    async function loadTenants() {
        tenants = await api('/api/tenants/') || [];
        renderTenantStats();
        renderTenantTable();
    }

    function renderTenantStats() {
        const active = tenants.filter(t => t.status === 'active').length;
        const suspended = tenants.filter(t => t.status === 'suspended').length;
        const total = tenants.length;
        const users = tenants.reduce((sum, t) => sum + t.user_count, 0);

        document.getElementById('tenant-stats').innerHTML = `
            <div class="stat-card"><div class="stat-value">${total}</div><div class="stat-label">Total Tenants</div></div>
            <div class="stat-card"><div class="stat-value">${active}</div><div class="stat-label">Active</div></div>
            <div class="stat-card"><div class="stat-value">${suspended}</div><div class="stat-label">Suspended</div></div>
            <div class="stat-card"><div class="stat-value">${users}</div><div class="stat-label">Total Users</div></div>
        `;
    }

    function renderTenantTable() {
        const tbody = document.getElementById('tenants-body');
        if (!tenants.length) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#64748b;">No tenants yet. Create one to get started.</td></tr>';
            return;
        }
        tbody.innerHTML = tenants.map(t => `
            <tr data-slug="${t.slug}">
                <td><strong>${t.slug}</strong></td>
                <td>${t.name}</td>
                <td><span class="badge badge-${t.status}">${t.status}</span></td>
                <td>${t.organization || '-'}</td>
                <td>${t.user_count}</td>
                <td>${formatDate(t.created_at)}</td>
            </tr>
        `).join('');

        tbody.querySelectorAll('tr').forEach(row => {
            row.addEventListener('click', () => openDetail(row.dataset.slug));
        });
    }

    // ------------------------------------------------------------------
    // Tenant detail
    // ------------------------------------------------------------------
    async function openDetail(slug) {
        selectedSlug = slug;
        // Fetch detail and stats in parallel
        const [data, stats] = await Promise.all([
            api(`/api/tenants/${slug}`),
            api(`/api/tenants/${slug}/stats`),
        ]);
        if (!data) return;

        const panel = document.getElementById('detail-panel');
        const dbIcon = data.db_healthy
            ? '<span class="health-indicator health-ok"></span>Healthy'
            : '<span class="health-indicator health-bad"></span>Unhealthy';

        const s = stats || {};
        const feedbackRate = s.total_feedback > 0
            ? Math.round((s.positive_feedback / s.total_feedback) * 100) + '%'
            : '-';
        const emailErrorRate = s.emails_processed > 0
            ? Math.round((s.emails_errors / s.emails_processed) * 100) + '%'
            : '-';
        const docTypes = s.documents_by_type || {};
        const docTypeStr = Object.keys(docTypes).length
            ? Object.entries(docTypes).map(([t, c]) => `${t}: ${c}`).join(', ')
            : '-';

        panel.innerHTML = `
            <div class="detail-header">
                <h2>${data.name} <span class="badge badge-${data.status}">${data.status}</span></h2>
                <button class="btn-sm" onclick="document.getElementById('detail-panel').classList.remove('visible')">Close</button>
            </div>

            <h2 style="margin-bottom:0.75rem;">Usage</h2>
            <div class="stats-row">
                <div class="stat-card"><div class="stat-value">${s.total_queries || 0}</div><div class="stat-label">Queries</div></div>
                <div class="stat-card"><div class="stat-value">${s.total_conversations || 0}</div><div class="stat-label">Conversations</div></div>
                <div class="stat-card"><div class="stat-value">${s.unique_users || 0}</div><div class="stat-label">Unique Users</div></div>
                <div class="stat-card"><div class="stat-value">${s.total_documents || 0}</div><div class="stat-label">Documents</div></div>
                <div class="stat-card"><div class="stat-value">${s.total_chunks || 0}</div><div class="stat-label">KB Chunks</div></div>
                <div class="stat-card"><div class="stat-value">${humanSize(s.total_document_bytes)}</div><div class="stat-label">Document Size</div></div>
            </div>
            <div class="detail-grid" style="margin-bottom:1rem;">
                <div class="detail-item"><label>Emails Processed</label><span>${s.emails_processed || 0}${s.emails_errors ? ` (${s.emails_errors} errors, ${emailErrorRate})` : ''}</span></div>
                <div class="detail-item"><label>Feedback</label><span>${s.total_feedback || 0} total, ${feedbackRate} positive</span></div>
                <div class="detail-item"><label>Doc Types</label><span>${docTypeStr}</span></div>
                <div class="detail-item"><label>Activity</label><span>${s.first_activity ? formatDate(s.first_activity) + ' - ' + formatDate(s.last_activity) : 'No activity yet'}</span></div>
            </div>

            <h2>Configuration</h2>
            <div class="detail-grid">
                <div class="detail-item"><label>Slug</label><span>${data.slug}</span></div>
                <div class="detail-item"><label>Email</label><span>${data.email_address}</span></div>
                <div class="detail-item"><label>Organization</label><span>${data.organization || '-'}</span></div>
                <div class="detail-item"><label>Database</label><span>${dbIcon}</span></div>
                <div class="detail-item"><label>DB Name</label><span>${data.db_name}</span></div>
                <div class="detail-item"><label>Storage</label><span>${data.storage_path}</span></div>
                <div class="detail-item"><label>Invite Code</label><span>${data.invite_code || '-'}</span></div>
                <div class="detail-item"><label>LLM Model</label><span>${data.llm_model || 'default'}</span></div>
                <div class="detail-item"><label>Created</label><span>${formatDate(data.created_at)}</span></div>
            </div>

            <div class="detail-actions">
                ${data.status === 'active'
                    ? `<button class="btn btn-warning" onclick="PlatformAdmin.suspendTenant('${data.slug}')">Suspend</button>`
                    : data.status === 'suspended'
                        ? `<button class="btn btn-success" onclick="PlatformAdmin.resumeTenant('${data.slug}')">Resume</button>`
                        : ''}
                <button class="btn btn-primary" onclick="PlatformAdmin.rotateKey('${data.slug}')">Rotate Key</button>
                <button class="btn btn-danger" onclick="PlatformAdmin.deleteTenant('${data.slug}')">Delete</button>
            </div>

            <h2 style="margin-top:1.5rem;">Users (${data.users.length})</h2>
            <button class="btn btn-primary" style="margin:0.5rem 0;" onclick="PlatformAdmin.showAddUser('${data.slug}', '${data.name}')">+ Add User</button>
            <table>
                <thead><tr><th>Email</th><th>Role</th><th>Joined</th><th></th></tr></thead>
                <tbody>
                    ${data.users.map(u => `
                        <tr>
                            <td>${u.email}</td>
                            <td><span class="badge badge-active">${u.role}</span></td>
                            <td>${formatDate(u.created_at)}</td>
                            <td><button class="btn-sm" onclick="PlatformAdmin.removeUser('${data.slug}', '${u.email}')">Remove</button></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        panel.classList.add('visible');
    }

    // ------------------------------------------------------------------
    // Tenant actions
    // ------------------------------------------------------------------


    async function suspendTenant(slug) {
        if (!confirm(`Suspend tenant "${slug}"? Users will lose access.`)) return;
        const data = await api(`/api/tenants/${slug}/suspend`, { method: 'POST' });
        if (data && data.success) {
            showToast(`Tenant '${slug}' suspended`, 'success');
            await loadTenants();
            await openDetail(slug);
        }
    }

    async function resumeTenant(slug) {
        const data = await api(`/api/tenants/${slug}/resume`, { method: 'POST' });
        if (data && data.success) {
            showToast(`Tenant '${slug}' resumed`, 'success');
            await loadTenants();
            await openDetail(slug);
        }
    }

    async function deleteTenant(slug) {
        const input = prompt(`Type "${slug}" to permanently delete this tenant:`);
        if (input !== slug) return;
        const data = await api(`/api/tenants/${slug}?confirm=${slug}`, { method: 'DELETE' });
        if (data && data.success) {
            showToast(`Tenant '${slug}' deleted`, 'success');
            document.getElementById('detail-panel').classList.remove('visible');
            selectedSlug = null;
            await loadTenants();
        } else if (data && data.detail) {
            showToast(data.detail, 'error');
        }
    }

    async function rotateKey(slug) {
        if (!confirm(`Rotate encryption key for "${slug}"?`)) return;
        const data = await api(`/api/tenants/${slug}/rotate-key`, { method: 'POST' });
        if (data && data.success) {
            showToast(data.message, 'success');
        } else if (data && data.detail) {
            showToast(data.detail, 'error');
        }
    }

    // ------------------------------------------------------------------
    // User management
    // ------------------------------------------------------------------
    function showAddUser(slug, name) {
        selectedSlug = slug;
        document.getElementById('au-tenant-name').textContent = name;
        showModal('add-user-modal');
    }

    async function handleAddUser(e) {
        e.preventDefault();
        const body = {
            email: document.getElementById('au-email').value.trim(),
            role: document.getElementById('au-role').value,
        };
        const data = await api(`/api/tenants/${selectedSlug}/users`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
        if (data && data.email) {
            showToast(`User ${data.email} added`, 'success');
            hideModal('add-user-modal');
            document.getElementById('add-user-form').reset();
            await openDetail(selectedSlug);
            await loadTenants();
        } else if (data && data.detail) {
            showToast(data.detail, 'error');
        }
    }

    async function removeUser(slug, email) {
        if (!confirm(`Remove ${email} from ${slug}?`)) return;
        const data = await api(`/api/tenants/${slug}/users/${encodeURIComponent(email)}`, { method: 'DELETE' });
        if (data && data.success) {
            showToast(`User ${email} removed`, 'success');
            await openDetail(slug);
            await loadTenants();
        } else if (data && data.detail) {
            showToast(data.detail, 'error');
        }
    }

    // ------------------------------------------------------------------
    // Health tab
    // ------------------------------------------------------------------
    async function loadHealth() {
        const data = await api('/api/platform/health');
        if (!data) return;

        const dbIcon = data.platform_db
            ? '<span class="health-indicator health-ok"></span>Connected'
            : '<span class="health-indicator health-bad"></span>Disconnected';

        document.getElementById('health-content').innerHTML = `
            <div class="stats-row">
                <div class="stat-card">
                    <div class="stat-value" style="font-size:1rem;">${dbIcon}</div>
                    <div class="stat-label">Platform Database</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.cache_stats.cached_tenants || 0}</div>
                    <div class="stat-label">Cached Connections</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.cache_stats.max_cached || 0}</div>
                    <div class="stat-label">Max Cached</div>
                </div>
            </div>
            <div class="card">
                <h2>Tenant Summary</h2>
                <div class="detail-grid">
                    <div class="detail-item"><label>Active</label><span>${data.tenant_counts.active || 0}</span></div>
                    <div class="detail-item"><label>Suspended</label><span>${data.tenant_counts.suspended || 0}</span></div>
                    <div class="detail-item"><label>Provisioning</label><span>${data.tenant_counts.provisioning || 0}</span></div>
                </div>
            </div>
            <div class="card">
                <h2>Configuration</h2>
                <div class="detail-grid">
                    <div class="detail-item"><label>Storage Backend</label><span>${data.storage_backend}</span></div>
                    <div class="detail-item"><label>Encryption</label><span>${data.encryption_enabled ? 'Enabled' : 'Disabled'}</span></div>
                    <div class="detail-item"><label>Pool per Tenant</label><span>${data.cache_stats.pool_size_per_tenant || '-'}</span></div>
                    <div class="detail-item"><label>Status</label>
                        <span class="badge ${data.status === 'healthy' ? 'badge-active' : 'badge-suspended'}">${data.status}</span>
                    </div>
                </div>
            </div>
        `;
    }

    // ------------------------------------------------------------------
    // Tabs
    // ------------------------------------------------------------------
    function switchTab(tab) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelector(`.tab[data-tab="${tab}"]`).classList.add('active');
        document.getElementById(`tab-${tab}`).classList.add('active');

        if (tab === 'health') loadHealth();
    }

    // ------------------------------------------------------------------
    // Auth
    // ------------------------------------------------------------------
    async function logout() {
        await api('/api/auth/logout', { method: 'POST' });
        window.location.href = '/static/login.html';
    }

    // ------------------------------------------------------------------
    // Utils
    // ------------------------------------------------------------------
    function formatDate(iso) {
        if (!iso) return '-';
        const d = new Date(iso);
        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function humanSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
    }

    function showModal(id) { document.getElementById(id).classList.add('visible'); }
    function hideModal(id) { document.getElementById(id).classList.remove('visible'); }

    function showToast(msg, type) {
        const toast = document.getElementById('toast');
        toast.textContent = msg;
        toast.className = `toast ${type} visible`;
        setTimeout(() => toast.classList.remove('visible'), 3000);
    }

    // ------------------------------------------------------------------
    // Expose to inline event handlers
    // ------------------------------------------------------------------
    window.PlatformAdmin = {
        suspendTenant,
        resumeTenant,
        deleteTenant,
        rotateKey,
        showAddUser,
        removeUser,
    };

    // Boot
    document.addEventListener('DOMContentLoaded', init);
})();
