/**
 * Admin Panel JavaScript
 * Handles whitelist management and document operations
 */

class AdminPanel {
    constructor() {
        this.whitelists = {
            queriers: [],
            teachers: [],
            admins: []
        };
        this.documents = [];
        this.init();
    }

    async init() {
        // Check authentication and admin status
        await this.checkAuth();

        // Load instance config
        await this.loadConfig();

        // Setup event listeners
        this.setupEventListeners();

        // Load initial data
        await this.loadAllWhitelists();
        await this.loadDocuments();
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/status');
            const data = await response.json();

            if (!data.authenticated) {
                // Redirect to login
                window.location.href = '/static/login.html';
                return;
            }

            if (!data.is_admin) {
                // Not an admin, redirect to main chat
                this.showToast('Access denied. Admin privileges required.', 'error');
                setTimeout(() => {
                    window.location.href = '/';
                }, 2000);
                return;
            }
        } catch (error) {
            console.error('Auth check failed:', error);
            window.location.href = '/static/login.html';
        }
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();

            // Update page title
            document.title = `Admin Panel - ${config.instance_name}`;
            document.getElementById('admin-title').textContent = `${config.instance_name} - Admin Panel`;
        } catch (error) {
            console.error('Error loading config:', error);
        }
    }

    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
        });

        // Enter key for whitelist inputs
        ['queriers', 'teachers', 'admins'].forEach(type => {
            const input = document.getElementById(`${type}-input`);
            if (input) {
                input.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        this.addWhitelistEntry(type);
                    }
                });
            }
        });
    }

    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}-tab`);
        });
    }

    async loadAllWhitelists() {
        await Promise.all([
            this.loadWhitelist('queriers'),
            this.loadWhitelist('teachers'),
            this.loadWhitelist('admins')
        ]);
    }

    async loadWhitelist(type) {
        try {
            const response = await fetch(`/api/admin/whitelists/${type}`);

            if (!response.ok) {
                throw new Error(`Failed to load ${type} whitelist`);
            }

            const data = await response.json();
            this.whitelists[type] = data.entries;
            this.renderWhitelist(type);
        } catch (error) {
            console.error(`Error loading ${type} whitelist:`, error);
            this.renderWhitelistError(type, error.message);
        }
    }

    renderWhitelist(type) {
        const container = document.getElementById(`${type}-list`);
        if (!container) return;

        if (this.whitelists[type].length === 0) {
            container.innerHTML = '<div class="empty-state">No entries yet</div>';
            return;
        }

        container.innerHTML = this.whitelists[type].map(entry => `
            <div class="whitelist-item">
                <span>${this.escapeHtml(entry)}</span>
                <button onclick="adminPanel.removeWhitelistEntry('${type}', '${this.escapeHtml(entry)}')">Remove</button>
            </div>
        `).join('');
    }

    renderWhitelistError(type, message) {
        const container = document.getElementById(`${type}-list`);
        if (!container) return;

        container.innerHTML = `<div class="error-message">Error: ${this.escapeHtml(message)}</div>`;
    }

    async addWhitelistEntry(type) {
        const input = document.getElementById(`${type}-input`);
        if (!input) return;

        const entry = input.value.trim();
        if (!entry) {
            this.showToast('Please enter an email or domain', 'error');
            return;
        }

        try {
            const response = await fetch(`/api/admin/whitelists/${type}/add`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ entry }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to add entry');
            }

            this.showToast(data.message, 'success');
            input.value = '';
            await this.loadWhitelist(type);
        } catch (error) {
            console.error('Error adding whitelist entry:', error);
            this.showToast(error.message, 'error');
        }
    }

    async removeWhitelistEntry(type, entry) {
        if (!confirm(`Remove "${entry}" from ${type} whitelist?`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/whitelists/${type}/remove`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ entry }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to remove entry');
            }

            this.showToast(data.message, 'success');
            await this.loadWhitelist(type);
        } catch (error) {
            console.error('Error removing whitelist entry:', error);
            this.showToast(error.message, 'error');
        }
    }

    async loadDocuments() {
        try {
            const response = await fetch('/api/admin/documents');

            if (!response.ok) {
                throw new Error('Failed to load documents');
            }

            const data = await response.json();
            this.documents = data.documents;
            this.renderDocuments();
        } catch (error) {
            console.error('Error loading documents:', error);
            this.renderDocumentsError(error.message);
        }
    }

    renderDocuments() {
        const container = document.getElementById('documents-list');
        if (!container) return;

        if (this.documents.length === 0) {
            container.innerHTML = '<div class="empty-state">No documents in knowledge base</div>';
            return;
        }

        container.innerHTML = this.documents.map(doc => {
            // Determine which buttons to show based on source type
            const canDownload = ['manual', 'file'].includes(doc.source_type);
            const canView = doc.source_type === 'email';

            const downloadButton = canDownload ? `
                <button class="btn-download" onclick="adminPanel.downloadDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')">
                    Download
                </button>
            ` : '';

            const viewButton = canView ? `
                <button class="btn-view" onclick="adminPanel.viewDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')">
                    View
                </button>
            ` : '';

            return `
                <div class="document-item">
                    <div class="document-info">
                        <div class="filename">${this.escapeHtml(doc.filename)}</div>
                        <div class="metadata">
                            Type: ${this.escapeHtml(doc.file_type || 'unknown')} |
                            Source: ${this.escapeHtml(doc.source_type || 'unknown')} |
                            Hash: ${this.escapeHtml(doc.file_hash.substring(0, 16))}...
                        </div>
                    </div>
                    <div class="document-actions">
                        ${viewButton}
                        ${downloadButton}
                        <button class="btn-delete" onclick="adminPanel.deleteDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')">
                            Delete
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    renderDocumentsError(message) {
        const container = document.getElementById('documents-list');
        if (!container) return;

        container.innerHTML = `<div class="error-message">Error: ${this.escapeHtml(message)}</div>`;
    }

    async viewDocument(fileHash, filename) {
        try {
            const response = await fetch(`/api/admin/documents/${fileHash}/view`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to load document content');
            }

            // Update modal content
            document.getElementById('modal-title').textContent = `View: ${filename}`;
            document.getElementById('modal-content').textContent = data.content;

            // Show modal
            document.getElementById('view-modal').classList.add('active');

            // Close modal on background click
            document.getElementById('view-modal').onclick = (e) => {
                if (e.target.id === 'view-modal') {
                    this.closeViewModal();
                }
            };

        } catch (error) {
            console.error('Error viewing document:', error);
            this.showToast(error.message, 'error');
        }
    }

    closeViewModal() {
        document.getElementById('view-modal').classList.remove('active');
    }

    downloadDocument(fileHash, filename) {
        // Create a download link and trigger it
        const downloadUrl = `/api/admin/documents/${fileHash}/download`;

        // Create temporary link element
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        link.style.display = 'none';

        // Add to DOM, click, and remove
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        this.showToast(`Downloading ${filename}...`, 'success');
    }

    async deleteDocument(fileHash, filename) {
        if (!confirm(`Delete document "${filename}"?\n\nThis will:\n- Archive the file\n- Remove all chunks from the knowledge base\n\nThis action cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/documents/${fileHash}?archive=true`, {
                method: 'DELETE',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete document');
            }

            this.showToast(data.message, 'success');
            await this.loadDocuments();
        } catch (error) {
            console.error('Error deleting document:', error);
            this.showToast(error.message, 'error');
        }
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        if (!toast) return;

        toast.textContent = message;
        toast.className = `toast ${type}`;
        toast.style.display = 'block';

        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize admin panel when page loads
const adminPanel = new AdminPanel();
