/**
 * Moderation tab — review teach submissions queued from users without
 * teach permission. Polls a pending-count endpoint to drive the tab badge.
 */
(function () {
    const POLL_INTERVAL_MS = 30000;

    const state = {
        filter: 'pending',
        items: [],
        selectedId: null,
        pollTimer: null,
    };

    function el(tag, attrs, ...children) {
        const node = document.createElement(tag);
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) {
                if (k === 'className') node.className = v;
                else if (k === 'onclick') node.onclick = v;
                else if (k === 'dataset') Object.assign(node.dataset, v);
                else node.setAttribute(k, v);
            }
        }
        for (const child of children.flat()) {
            if (child == null) continue;
            node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
        }
        return node;
    }

    function showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        if (!toast) return;
        toast.textContent = message;
        toast.className = `toast show ${type}`;
        setTimeout(() => { toast.className = 'toast'; }, 3000);
    }

    async function refreshPendingCount() {
        try {
            const resp = await fetch('/api/admin/moderation/queue/pending-count');
            if (!resp.ok) return;
            const data = await resp.json();
            const badge = document.getElementById('moderation-badge');
            if (!badge) return;
            if (data.count > 0) {
                badge.textContent = data.count > 99 ? '99+' : String(data.count);
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
        } catch (e) {
            // Network errors shouldn't disrupt the panel.
        }
    }

    async function loadList() {
        const list = document.getElementById('moderation-list');
        if (!list) return;
        list.innerHTML = '<div class="moderation-row empty">Loading…</div>';
        try {
            const resp = await fetch(`/api/admin/moderation/queue?status=${encodeURIComponent(state.filter)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            state.items = data.submissions || [];
            renderList();
        } catch (e) {
            list.innerHTML = `<div class="moderation-row empty">Failed to load: ${e.message}</div>`;
        }
    }

    function renderList() {
        const list = document.getElementById('moderation-list');
        if (!list) return;
        list.innerHTML = '';
        if (state.items.length === 0) {
            list.appendChild(el('div', { className: 'moderation-row empty' }, 'No submissions in this view.'));
            return;
        }
        for (const item of state.items) {
            const created = item.created_at ? new Date(item.created_at).toLocaleString() : '—';
            const attachmentCount = (item.attachment_keys || []).length;
            const subject = item.subject || '(no subject)';
            const row = el(
                'div',
                { className: 'moderation-row', onclick: () => loadDetail(item.id) },
                el('div', null, item.submitter_email),
                el('div', null,
                    el('div', null, subject),
                    el('div', { className: 'meta' }, `${attachmentCount} attachment(s) • ${created}`)
                ),
                el('div', { className: `status-${item.status}` }, item.status),
                el('div', { className: 'meta' }, '›')
            );
            list.appendChild(row);
        }
    }

    async function loadDetail(submissionId) {
        state.selectedId = submissionId;
        const container = document.getElementById('moderation-detail-container');
        if (!container) return;
        container.innerHTML = '<div class="moderation-detail">Loading…</div>';
        try {
            const resp = await fetch(`/api/admin/moderation/${encodeURIComponent(submissionId)}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const item = await resp.json();
            renderDetail(item);
        } catch (e) {
            container.innerHTML = `<div class="moderation-detail">Failed to load: ${e.message}</div>`;
        }
    }

    function renderDetail(item) {
        const container = document.getElementById('moderation-detail-container');
        if (!container) return;
        container.innerHTML = '';

        const isPending = item.status === 'pending';
        const created = item.created_at ? new Date(item.created_at).toLocaleString() : '—';
        const reviewed = item.reviewed_at ? new Date(item.reviewed_at).toLocaleString() : null;
        const attachments = item.attachment_keys || [];

        const detail = el('div', { className: 'moderation-detail' },
            el('h4', null, item.subject || '(no subject)'),
            el('div', { className: 'meta' },
                `From ${item.submitter_email} • Submitted ${created}` +
                (reviewed ? ` • Reviewed ${reviewed} by ${item.reviewed_by || ''}` : '')
            ),
            el('div', { className: 'field-label' }, 'Body'),
            el('pre', { className: 'body-preview' }, item.body_text || '(empty)'),
        );

        if (attachments.length > 0) {
            detail.appendChild(el('div', { className: 'field-label' }, 'Attachments'));
            const list = el('ul');
            for (const att of attachments) {
                const link = el('a', {
                    href: `/api/admin/moderation/${encodeURIComponent(item.id)}/attachments/${encodeURIComponent(att.filename)}`,
                    target: '_blank',
                    rel: 'noopener',
                }, att.filename);
                const li = el('li', null, link, ` (${att.size || 0} bytes)`);
                list.appendChild(li);
            }
            detail.appendChild(list);
        }

        if (isPending) {
            const notesInput = el('textarea', { rows: '2', placeholder: 'Optional notes (sent to submitter)' });
            const promoteCheckbox = el('input', { type: 'checkbox', id: 'mod-promote', checked: 'checked' });
            const actions = el('div', { className: 'moderation-actions' },
                notesInput,
                el('label', null, promoteCheckbox, ' Promote sender to teacher'),
                el('button', {
                    className: 'approve-btn',
                    onclick: () => approve(item.id, notesInput.value, promoteCheckbox.checked),
                }, 'Approve'),
                el('button', {
                    className: 'reject-btn',
                    onclick: () => reject(item.id, notesInput.value),
                }, 'Reject'),
            );
            detail.appendChild(actions);
        } else {
            if (item.decision_notes) {
                detail.appendChild(el('div', { className: 'field-label' }, 'Decision notes'));
                detail.appendChild(el('pre', { className: 'body-preview' }, item.decision_notes));
            }
            if (item.promoted_to_teacher) {
                detail.appendChild(el('div', { className: 'meta' }, 'Submitter was promoted to teacher.'));
            }
        }

        container.appendChild(detail);
    }

    async function approve(submissionId, notes, promote) {
        const ok = confirm('Approve this submission and add it to the knowledge base?');
        if (!ok) return;
        try {
            const resp = await fetch(`/api/admin/moderation/${encodeURIComponent(submissionId)}/approve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ promote_to_teacher: promote, notes: notes || null }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            showToast(`Approved (${data.chunks_added} chunks added${data.promoted_to_teacher ? ', promoted to teacher' : ''})`);
            await Promise.all([loadList(), refreshPendingCount()]);
            document.getElementById('moderation-detail-container').innerHTML = '';
        } catch (e) {
            showToast(`Approve failed: ${e.message}`, 'error');
        }
    }

    async function reject(submissionId, notes) {
        const ok = confirm('Reject this submission?');
        if (!ok) return;
        try {
            const resp = await fetch(`/api/admin/moderation/${encodeURIComponent(submissionId)}/reject`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notes: notes || null }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            showToast('Rejected');
            await Promise.all([loadList(), refreshPendingCount()]);
            document.getElementById('moderation-detail-container').innerHTML = '';
        } catch (e) {
            showToast(`Reject failed: ${e.message}`, 'error');
        }
    }

    function bindFilters() {
        document.querySelectorAll('[data-mod-filter]').forEach((btn) => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('[data-mod-filter]').forEach((b) => b.classList.toggle('active', b === btn));
                state.filter = btn.dataset.modFilter;
                loadList();
            });
        });
    }

    function startPolling() {
        refreshPendingCount();
        if (state.pollTimer) clearInterval(state.pollTimer);
        state.pollTimer = setInterval(refreshPendingCount, POLL_INTERVAL_MS);
    }

    function init() {
        bindFilters();
        startPolling();

        const moderationTab = document.querySelector('[data-tab="moderation"]');
        if (moderationTab) {
            moderationTab.addEventListener('click', loadList);
        }

        // Load list immediately if the tab is already active on page load
        const moderationContent = document.getElementById('moderation-tab');
        if (moderationContent && moderationContent.classList.contains('active')) {
            loadList();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
