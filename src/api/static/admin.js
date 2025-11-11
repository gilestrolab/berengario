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
        this.crawledUrls = [];
        this.backups = [];
        this.sortState = {}; // Track sort state per section
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
        await this.loadBackups();
        await this.loadSettings();
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

            // Update header with organization if available
            let headerText = `${config.instance_name} - Admin Panel`;
            if (config.organization) {
                headerText = `${config.instance_name} - Admin Panel`;
                // Add organization as subtitle
                const adminTitle = document.getElementById('admin-title');
                adminTitle.innerHTML = `
                    ${config.instance_name} - Admin Panel
                    <div style="font-size: 0.6em; font-weight: normal; color: var(--text-secondary, #666); margin-top: 0.25rem;">
                        ${config.organization}
                    </div>
                `;
            } else {
                document.getElementById('admin-title').textContent = headerText;
            }
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

        // File upload selection handler
        const fileInput = document.getElementById('document-upload');
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                this.handleFileSelection(e);
            });
        }
    }

    handleFileSelection(event) {
        const files = event.target.files;
        const selectedFilesSpan = document.getElementById('selected-files');
        const uploadButton = document.querySelector('.btn-upload-process');

        if (files.length > 0) {
            const fileNames = Array.from(files).map(f => f.name).join(', ');
            if (selectedFilesSpan) {
                selectedFilesSpan.textContent = `${files.length} file(s) selected: ${fileNames.substring(0, 100)}${fileNames.length > 100 ? '...' : ''}`;
            }
            if (uploadButton) {
                uploadButton.style.display = 'inline-block';
            }
        } else {
            if (selectedFilesSpan) {
                selectedFilesSpan.textContent = '';
            }
            if (uploadButton) {
                uploadButton.style.display = 'none';
            }
        }
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

        // Load data for specific tabs on first switch
        if (tabName === 'webcrawl' && this.crawledUrls.length === 0) {
            this.loadCrawledUrls();
        }
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
            // Load both documents and descriptions in parallel
            const [docsResponse, descsResponse] = await Promise.all([
                fetch('/api/admin/documents'),
                fetch('/api/admin/documents/descriptions')
            ]);

            if (!docsResponse.ok) {
                throw new Error('Failed to load documents');
            }

            const docsData = await docsResponse.json();
            this.documents = docsData.documents;

            // Load descriptions (don't fail if it errors)
            this.descriptions = {};
            if (descsResponse.ok) {
                try {
                    const descsData = await descsResponse.json();
                    // Create a map of file_path -> description
                    descsData.descriptions.forEach(desc => {
                        // Also map by filename for easier matching
                        this.descriptions[desc.filename] = desc;
                    });
                } catch (e) {
                    console.warn('Failed to parse descriptions:', e);
                }
            }

            this.renderDocuments();
        } catch (error) {
            console.error('Error loading documents:', error);
            this.renderDocumentsError(error.message);
        }
    }

    getDisplayName(doc) {
        // Generate a better display name for emails
        if (doc.source_type === 'email' && doc.sender && doc.subject) {
            const senderName = doc.sender.split('@')[0];
            const date = doc.date ? new Date(doc.date).toLocaleDateString() : 'unknown date';
            const subject = doc.subject.substring(0, 50);
            return `Email from ${senderName} on ${date} - ${subject}`;
        }
        return doc.filename;
    }

    renderDocuments() {
        const container = document.getElementById('documents-list');
        if (!container) return;

        if (this.documents.length === 0) {
            container.innerHTML = '<div class="empty-state">No documents in knowledge base</div>';
            return;
        }

        // Separate documents from emails
        const fileDocuments = this.documents.filter(doc => doc.source_type !== 'email');
        const emailDocuments = this.documents.filter(doc => doc.source_type === 'email');

        let html = '';

        // Render file documents section
        if (fileDocuments.length > 0) {
            html += this.renderDocumentSection(
                'files',
                'Documents',
                fileDocuments,
                false  // Start expanded
            );
        }

        // Render email documents section
        if (emailDocuments.length > 0) {
            html += this.renderDocumentSection(
                'emails',
                'Emails',
                emailDocuments,
                false  // Start expanded
            );
        }

        container.innerHTML = html;

        // Setup toggle listeners
        this.setupSectionToggles();
    }

    renderDocumentSection(id, title, documents, collapsed) {
        const collapsedClass = collapsed ? 'collapsed' : '';
        const contentClass = collapsed ? 'collapsed' : '';

        // Sort documents by age (newest first) by default
        const sortedDocs = [...documents].sort((a, b) => {
            const ageA = a.age_days ?? Infinity;
            const ageB = b.age_days ?? Infinity;
            return ageA - ageB;
        });

        const rowsHtml = sortedDocs.map(doc => {
            // Determine which buttons to show based on source type
            const canDownload = ['manual', 'file'].includes(doc.source_type);
            const canView = doc.source_type === 'email';

            // Get display name (improved for emails)
            const displayName = this.getDisplayName(doc);

            // Get description if available
            const description = this.descriptions && this.descriptions[doc.filename];
            const hasDescription = description && description.description;
            const descriptionText = hasDescription ? this.escapeHtml(description.description) : '';

            // Info button - only show if description exists
            const infoButton = hasDescription ? `
                <button class="btn-info" title="Show/hide description">ℹ️</button>
            ` : '';

            const downloadButton = canDownload ? `
                <button class="btn-download" onclick="adminPanel.downloadDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')" title="Download">
                    ⬇
                </button>
            ` : '';

            const viewButton = canView ? `
                <button class="btn-view" onclick="adminPanel.viewDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')" title="View">
                    <i class="fas fa-eye"></i>
                </button>
            ` : '';

            // Format age for display
            const ageHtml = this.formatDocumentAge(doc.age_days, doc.date_added);

            return `
                <tr class="doc-row" data-age="${doc.age_days ?? ''}">
                    <td class="doc-filename">
                        <div class="filename-container">
                            <span class="filename" title="${this.escapeHtml(displayName)}">${this.escapeHtml(displayName)}</span>
                            ${infoButton}
                        </div>
                        ${hasDescription ? `<div class="document-description">${descriptionText}</div>` : ''}
                    </td>
                    <td class="doc-age-cell">${ageHtml}</td>
                    <td class="doc-actions">
                        ${viewButton}
                        ${downloadButton}
                        <button class="btn-delete" onclick="adminPanel.deleteDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        return `
            <div class="document-section">
                <div class="section-header ${collapsedClass}" data-section="${id}">
                    <span class="toggle-icon">▼</span>
                    <span class="title">${title}</span>
                    <span class="count">${documents.length}</span>
                </div>
                <div class="section-content ${contentClass}" data-section="${id}">
                    <table class="documents-table">
                        <thead>
                            <tr>
                                <th class="sortable" data-sort-key="filename" onclick="adminPanel.sortDocuments('${id}', 'filename')">
                                    Document <span class="sort-indicator"></span>
                                </th>
                                <th class="sortable" data-sort-key="age" onclick="adminPanel.sortDocuments('${id}', 'age')">
                                    Age <span class="sort-indicator"></span>
                                </th>
                                <th class="actions-header">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }

    setupSectionToggles() {
        document.querySelectorAll('.section-header').forEach(header => {
            header.addEventListener('click', () => {
                const sectionId = header.getAttribute('data-section');
                const content = document.querySelector(`.section-content[data-section="${sectionId}"]`);

                if (content) {
                    header.classList.toggle('collapsed');
                    content.classList.toggle('collapsed');
                }
            });
        });

        // Setup event delegation for info button clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('btn-info')) {
                e.preventDefault();
                e.stopPropagation();
                this.toggleDescriptionForDoc(e.target);
            }
        });
    }

    /**
     * Sort documents in a section by specified key
     * @param {string} sectionId - Section identifier ('files' or 'emails')
     * @param {string} sortKey - Sort key ('filename' or 'age')
     */
    sortDocuments(sectionId, sortKey) {
        // Initialize sort state for this section if not exists
        if (!this.sortState[sectionId]) {
            this.sortState[sectionId] = { key: 'age', ascending: true };
        }

        const state = this.sortState[sectionId];

        // Toggle direction if same key, otherwise reset to ascending
        if (state.key === sortKey) {
            state.ascending = !state.ascending;
        } else {
            state.key = sortKey;
            state.ascending = true;
        }

        // Get documents for this section
        const isFilesSection = sectionId === 'files';
        const sectionDocs = this.documents.filter(doc =>
            isFilesSection ? doc.source_type !== 'email' : doc.source_type === 'email'
        );

        // Sort documents
        sectionDocs.sort((a, b) => {
            let valA, valB;

            if (sortKey === 'age') {
                valA = a.age_days ?? Infinity;
                valB = b.age_days ?? Infinity;
            } else if (sortKey === 'filename') {
                valA = this.getDisplayName(a).toLowerCase();
                valB = this.getDisplayName(b).toLowerCase();
            }

            if (valA < valB) return state.ascending ? -1 : 1;
            if (valA > valB) return state.ascending ? 1 : -1;
            return 0;
        });

        // Re-render just this section
        const sectionContainer = document.querySelector(`.section-content[data-section="${sectionId}"]`);
        if (!sectionContainer) return;

        const table = sectionContainer.querySelector('.documents-table tbody');
        if (!table) return;

        // Re-render rows
        const rowsHtml = sectionDocs.map(doc => {
            const canDownload = ['manual', 'file'].includes(doc.source_type);
            const canView = doc.source_type === 'email';
            const displayName = this.getDisplayName(doc);

            const description = this.descriptions && this.descriptions[doc.filename];
            const hasDescription = description && description.description;
            const descriptionText = hasDescription ? this.escapeHtml(description.description) : '';

            const infoButton = hasDescription ? `
                <button class="btn-info" title="Show/hide description">ℹ️</button>
            ` : '';

            const downloadButton = canDownload ? `
                <button class="btn-download" onclick="adminPanel.downloadDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')" title="Download">
                    ⬇
                </button>
            ` : '';

            const viewButton = canView ? `
                <button class="btn-view" onclick="adminPanel.viewDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')" title="View">
                    <i class="fas fa-eye"></i>
                </button>
            ` : '';

            const ageHtml = this.formatDocumentAge(doc.age_days, doc.date_added);

            return `
                <tr class="doc-row" data-age="${doc.age_days ?? ''}">
                    <td class="doc-filename">
                        <div class="filename-container">
                            <span class="filename" title="${this.escapeHtml(displayName)}">${this.escapeHtml(displayName)}</span>
                            ${infoButton}
                        </div>
                        ${hasDescription ? `<div class="document-description">${descriptionText}</div>` : ''}
                    </td>
                    <td class="doc-age-cell">${ageHtml}</td>
                    <td class="doc-actions">
                        ${viewButton}
                        ${downloadButton}
                        <button class="btn-delete" onclick="adminPanel.deleteDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        table.innerHTML = rowsHtml;

        // Update sort indicators
        sectionContainer.querySelectorAll('.sortable').forEach(th => {
            const indicator = th.querySelector('.sort-indicator');
            if (th.dataset.sortKey === sortKey) {
                indicator.textContent = state.ascending ? '▲' : '▼';
                th.classList.add('sorted');
            } else {
                indicator.textContent = '';
                th.classList.remove('sorted');
            }
        });
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
            const modal = document.getElementById('view-modal');
            modal.classList.add('active');

            // Close modal on background click
            modal.onclick = (e) => {
                if (e.target.id === 'view-modal') {
                    this.closeViewModal();
                }
            };

            // Close modal on ESC key
            const escHandler = (e) => {
                if (e.key === 'Escape') {
                    this.closeViewModal();
                    document.removeEventListener('keydown', escHandler);
                }
            };
            document.addEventListener('keydown', escHandler);

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

    // Web Crawling Methods
    async crawlUrl() {
        const urlInput = document.getElementById('crawl-url-input');
        const depthSelect = document.getElementById('crawl-depth-select');
        const crawlBtn = document.getElementById('crawl-btn');
        const statusDiv = document.getElementById('crawl-status');

        const url = urlInput.value.trim();
        const depth = parseInt(depthSelect.value);

        if (!url) {
            this.showToast('Please enter a URL', 'error');
            return;
        }

        // Basic URL validation
        try {
            new URL(url);
        } catch (e) {
            this.showToast('Please enter a valid URL (including http:// or https://)', 'error');
            return;
        }

        // Disable button and show processing
        crawlBtn.disabled = true;
        crawlBtn.textContent = 'Crawling...';
        statusDiv.innerHTML = '<div class="upload-file-processing"><i class="fas fa-spinner fa-spin"></i> Crawling URL, please wait...</div>';

        try {
            const response = await fetch('/api/admin/crawl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    url: url,
                    crawl_depth: depth,
                }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to crawl URL');
            }

            // Success
            statusDiv.innerHTML = `
                <div class="upload-file-success">
                    <i class="fas fa-check"></i> Successfully crawled ${data.details.pages_crawled} page(s)<br>
                    Added ${data.details.chunks_added} chunks to knowledge base
                </div>
            `;

            this.showToast(data.message, 'success');

            // Clear input and reload list
            urlInput.value = '';
            await this.loadCrawledUrls();

        } catch (error) {
            console.error('Error crawling URL:', error);
            statusDiv.innerHTML = `<div class="upload-file-error"><i class="fas fa-xmark"></i> Error: ${this.escapeHtml(error.message)}</div>`;
            this.showToast(error.message, 'error');
        } finally {
            // Re-enable button
            crawlBtn.disabled = false;
            crawlBtn.textContent = 'Crawl URL';
        }
    }

    async loadCrawledUrls() {
        try {
            const response = await fetch('/api/admin/crawled-urls');

            if (!response.ok) {
                throw new Error('Failed to load crawled URLs');
            }

            const data = await response.json();
            this.crawledUrls = data.urls;

            this.renderCrawledUrls();
        } catch (error) {
            console.error('Error loading crawled URLs:', error);
            this.renderCrawledUrlsError(error.message);
        }
    }

    renderCrawledUrls() {
        const container = document.getElementById('crawled-urls-list');
        if (!container) return;

        if (!this.crawledUrls || this.crawledUrls.length === 0) {
            container.innerHTML = '<div class="empty-state">No crawled URLs in knowledge base</div>';
            return;
        }

        const itemsHtml = this.crawledUrls.map(url => {
            const displayUrl = url.source_url.length > 80
                ? url.source_url.substring(0, 77) + '...'
                : url.source_url;

            const crawledDate = url.last_crawled_formatted || 'Unknown';

            return `
                <div class="document-item">
                    <div class="document-info">
                        <div class="filename-row">
                            <div class="filename" title="${this.escapeHtml(url.source_url)}">
                                <i class="fas fa-globe"></i> ${this.escapeHtml(displayUrl)}
                            </div>
                        </div>
                        <div style="font-size: 0.75rem; color: var(--text-secondary, #999); margin-top: 0.25rem;">
                            Crawled: ${this.escapeHtml(crawledDate)} | Depth: ${url.crawl_depth || 1}
                        </div>
                    </div>
                    <div class="document-actions">
                        <button class="btn-view" onclick="window.open('${this.escapeHtml(url.source_url)}', '_blank')" title="Open URL">
                            <i class="fas fa-link"></i>
                        </button>
                        <button class="btn-delete" onclick="adminPanel.deleteCrawledUrl('${this.escapeHtml(url.url_hash)}', '${this.escapeHtml(url.source_url)}')" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        const html = `
            <div class="section">
                <div class="section-header">
                    <h4>
                        Crawled URLs
                        <span class="count">${this.crawledUrls.length}</span>
                    </h4>
                </div>
                <div class="section-content">
                    ${itemsHtml}
                </div>
            </div>
        `;

        container.innerHTML = html;
    }

    renderCrawledUrlsError(message) {
        const container = document.getElementById('crawled-urls-list');
        if (!container) return;

        container.innerHTML = `
            <div class="empty-state" style="color: var(--danger, #dc3545);">
                Error loading crawled URLs: ${this.escapeHtml(message)}
            </div>
        `;
    }

    async deleteCrawledUrl(urlHash, sourceUrl) {
        if (!confirm(`Delete crawled URL?\n\n${sourceUrl}`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/crawled-urls/${urlHash}`, {
                method: 'DELETE',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete URL');
            }

            this.showToast(data.message, 'success');
            await this.loadCrawledUrls();
        } catch (error) {
            console.error('Error deleting crawled URL:', error);
            this.showToast(error.message, 'error');
        }
    }

    async deleteAllCrawledUrls() {
        const count = this.crawledUrls ? this.crawledUrls.length : 0;

        if (count === 0) {
            this.showToast('No crawled URLs to delete', 'info');
            return;
        }

        if (!confirm(`WARNING: This will delete ALL ${count} crawled URL(s) from the knowledge base.\n\nThis action cannot be undone.\n\nAre you sure you want to continue?`)) {
            return;
        }

        try {
            const response = await fetch('/api/admin/crawled-urls/all', {
                method: 'DELETE',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete all URLs');
            }

            this.showToast(data.message, 'success');
            await this.loadCrawledUrls();
        } catch (error) {
            console.error('Error deleting all crawled URLs:', error);
            this.showToast(error.message, 'error');
        }
    }

    async loadBackups() {
        try {
            const response = await fetch('/api/admin/backups');

            if (!response.ok) {
                throw new Error('Failed to load backups');
            }

            const data = await response.json();
            this.backups = data.backups;
            this.renderBackups();
        } catch (error) {
            console.error('Error loading backups:', error);
            this.renderBackupsError(error.message);
        }
    }

    renderBackups() {
        const container = document.getElementById('backups-list');
        if (!container) return;

        if (this.backups.length === 0) {
            container.innerHTML = '<div class="empty-state">No backups available</div>';
            return;
        }

        container.innerHTML = this.backups.map(backup => {
            const createdDate = new Date(backup.created).toLocaleString();

            return `
                <div class="backup-item">
                    <div class="backup-info">
                        <div class="backup-name">${this.escapeHtml(backup.filename)}</div>
                        <div class="backup-metadata">
                            Size: ${backup.size_mb} MB | Created: ${createdDate}
                        </div>
                    </div>
                    <div class="backup-actions">
                        <button class="btn-download-backup" onclick="adminPanel.downloadBackup('${this.escapeHtml(backup.filename)}')">
                            Download
                        </button>
                        <button class="btn-delete-backup" onclick="adminPanel.deleteBackup('${this.escapeHtml(backup.filename)}')">
                            Delete
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    }

    renderBackupsError(message) {
        const container = document.getElementById('backups-list');
        if (!container) return;

        container.innerHTML = `<div class="error-message">Error: ${this.escapeHtml(message)}</div>`;
    }

    async createBackup() {
        if (!confirm('Create a data backup?\n\nThis will create a ZIP file of the entire data directory. You will receive an email with a download link when the backup is complete.\n\nNote: This may take a few minutes for large knowledge bases.')) {
            return;
        }

        try {
            // Disable the button to prevent multiple clicks
            const button = document.querySelector('.btn-create-backup');
            if (button) {
                button.disabled = true;
                button.textContent = 'Creating backup...';
            }

            const response = await fetch('/api/admin/backup/create', {
                method: 'POST',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to create backup');
            }

            this.showToast(data.message, 'success');

            // Re-enable button after a delay
            setTimeout(() => {
                if (button) {
                    button.disabled = false;
                    button.textContent = 'Create New Backup';
                }
                // Reload backups list after some time to show the new backup
                setTimeout(() => this.loadBackups(), 5000);
            }, 2000);

        } catch (error) {
            console.error('Error creating backup:', error);
            this.showToast(error.message, 'error');

            // Re-enable button on error
            const button = document.querySelector('.btn-create-backup');
            if (button) {
                button.disabled = false;
                button.textContent = 'Create New Backup';
            }
        }
    }

    downloadBackup(filename) {
        // Create a download link and trigger it
        const downloadUrl = `/api/admin/backups/${filename}`;

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

    async deleteBackup(filename) {
        if (!confirm(`Delete backup "${filename}"?\n\nThis action cannot be undone.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/backups/${filename}`, {
                method: 'DELETE',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to delete backup');
            }

            this.showToast(data.message, 'success');
            await this.loadBackups();
        } catch (error) {
            console.error('Error deleting backup:', error);
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

    async loadSettings() {
        // Load both model info and prompt settings
        await Promise.all([
            this.loadModelInfo(),
            this.loadPromptSettings()
        ]);
    }

    async loadModelInfo() {
        try {
            const response = await fetch('/api/admin/settings/models');

            if (!response.ok) {
                throw new Error('Failed to load model settings');
            }

            const data = await response.json();
            this.renderModelInfo(data);
        } catch (error) {
            console.error('Error loading model settings:', error);
            this.renderModelInfoError(error.message);
        }
    }

    renderModelInfo(data) {
        const container = document.getElementById('model-info');
        if (!container) return;

        container.innerHTML = `
            <div class="model-card">
                <h4>Embedding Model</h4>
                <div class="model-detail">
                    <span class="model-detail-label">Model:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.embedding.model)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Provider:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.embedding.provider)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">API Base:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.embedding.api_base)}</span>
                </div>
            </div>

            <div class="model-card">
                <h4>LLM Model</h4>
                <div class="model-detail">
                    <span class="model-detail-label">Model:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.llm.model)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Provider:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.llm.provider)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">API Base:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.llm.api_base)}</span>
                </div>
            </div>

            <div class="model-card">
                <h4>RAG Configuration</h4>
                <div class="model-detail">
                    <span class="model-detail-label">Chunk Size:</span>
                    <span class="model-detail-value">${data.rag.chunk_size}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Chunk Overlap:</span>
                    <span class="model-detail-value">${data.rag.chunk_overlap}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Top K Retrieval:</span>
                    <span class="model-detail-value">${data.rag.top_k_retrieval}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Similarity Threshold:</span>
                    <span class="model-detail-value">${data.rag.similarity_threshold}</span>
                </div>
            </div>
        `;
    }

    renderModelInfoError(message) {
        const container = document.getElementById('model-info');
        if (!container) return;

        container.innerHTML = `<div class="error-message">Error: ${this.escapeHtml(message)}</div>`;
    }

    async loadPromptSettings() {
        try {
            const response = await fetch('/api/admin/settings/prompt');

            if (!response.ok) {
                throw new Error('Failed to load prompt settings');
            }

            const data = await response.json();
            this.renderPromptSettings(data);
        } catch (error) {
            console.error('Error loading prompt settings:', error);
            this.showToast('Failed to load prompt settings', 'error');
        }
    }

    renderPromptSettings(data) {
        const fullPromptTextarea = document.getElementById('full-prompt');
        const customPromptTextarea = document.getElementById('custom-prompt');

        if (fullPromptTextarea) {
            fullPromptTextarea.value = data.full_prompt || '';
        }

        if (customPromptTextarea) {
            customPromptTextarea.value = data.custom_prompt || '';
        }
    }

    async uploadDocuments() {
        const fileInput = document.getElementById('document-upload');
        const uploadButton = document.querySelector('.btn-upload-process');
        const chooseButton = document.querySelector('.btn-upload');
        const progressDiv = document.getElementById('upload-progress');
        const statusDiv = document.getElementById('upload-status');

        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showToast('Please select files to upload', 'error');
            return;
        }

        const files = Array.from(fileInput.files);

        try {
            // Disable buttons
            if (uploadButton) uploadButton.disabled = true;
            if (chooseButton) chooseButton.disabled = true;

            // Show progress
            if (progressDiv) progressDiv.style.display = 'block';
            if (statusDiv) statusDiv.innerHTML = '';

            // Upload files one by one
            for (let i = 0; i < files.length; i++) {
                const file = files[i];

                // Update status
                if (statusDiv) {
                    const fileItem = document.createElement('div');
                    fileItem.className = 'upload-file-item upload-file-processing';
                    fileItem.id = `upload-file-${i}`;
                    fileItem.textContent = `Uploading ${file.name}... (${i + 1}/${files.length})`;
                    statusDiv.appendChild(fileItem);
                }

                try {
                    // Create form data
                    const formData = new FormData();
                    formData.append('file', file);

                    // Upload file
                    const response = await fetch('/api/admin/documents/upload', {
                        method: 'POST',
                        body: formData,
                    });

                    const data = await response.json();

                    // Update status
                    const fileItem = document.getElementById(`upload-file-${i}`);
                    if (fileItem) {
                        if (response.ok) {
                            fileItem.className = 'upload-file-item upload-file-success';
                            fileItem.innerHTML = `<i class="fas fa-check"></i> ${file.name} - Successfully processed (${data.chunks_added || 0} chunks)`;
                        } else {
                            fileItem.className = 'upload-file-item upload-file-error';
                            fileItem.innerHTML = `<i class="fas fa-xmark"></i> ${file.name} - ${data.detail || 'Upload failed'}`;
                        }
                    }
                } catch (error) {
                    const fileItem = document.getElementById(`upload-file-${i}`);
                    if (fileItem) {
                        fileItem.className = 'upload-file-item upload-file-error';
                        fileItem.innerHTML = `<i class="fas fa-xmark"></i> ${file.name} - ${error.message}`;
                    }
                }
            }

            // Show completion message
            this.showToast(`Uploaded ${files.length} file(s)`, 'success');

            // Reload documents list
            await this.loadDocuments();

            // Clear file input and reset UI
            fileInput.value = '';
            document.getElementById('selected-files').textContent = '';
            if (uploadButton) uploadButton.style.display = 'none';

        } catch (error) {
            console.error('Error uploading documents:', error);
            this.showToast(error.message, 'error');
        } finally {
            // Re-enable buttons
            if (uploadButton) uploadButton.disabled = false;
            if (chooseButton) chooseButton.disabled = false;
        }
    }

    async savePrompt() {
        const customPromptTextarea = document.getElementById('custom-prompt');
        const saveButton = document.querySelector('.btn-save-prompt');
        const statusSpan = document.getElementById('prompt-save-status');

        if (!customPromptTextarea) return;

        const customPrompt = customPromptTextarea.value;

        try {
            // Disable button during save
            if (saveButton) {
                saveButton.disabled = true;
                saveButton.textContent = 'Saving...';
            }
            if (statusSpan) {
                statusSpan.textContent = '';
            }

            const response = await fetch('/api/admin/settings/prompt', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ custom_prompt: customPrompt }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to save custom prompt');
            }

            this.showToast(data.message, 'success');
            if (statusSpan) {
                statusSpan.innerHTML = '<i class="fas fa-check"></i> Saved successfully';
                statusSpan.style.color = 'var(--success, #28a745)';
                setTimeout(() => {
                    statusSpan.textContent = '';
                }, 3000);
            }

            // Reload the full prompt to show the updated version
            await this.loadPromptSettings();

        } catch (error) {
            console.error('Error saving custom prompt:', error);
            this.showToast(error.message, 'error');
            if (statusSpan) {
                statusSpan.innerHTML = '<i class="fas fa-xmark"></i> Save failed';
                statusSpan.style.color = 'var(--danger, #dc3545)';
            }
        } finally {
            // Re-enable button
            if (saveButton) {
                saveButton.disabled = false;
                saveButton.textContent = 'Save Custom Prompt';
            }
        }
    }

    async generateExampleQuestions() {
        const generateButton = document.getElementById('generate-questions-btn');
        const statusSpan = document.getElementById('questions-generate-status');
        const previewDiv = document.getElementById('example-questions-preview');
        const questionsList = document.getElementById('questions-list');

        if (!generateButton) return;

        // Disable button and show processing
        generateButton.disabled = true;
        generateButton.textContent = 'Generating...';
        if (statusSpan) {
            statusSpan.textContent = '⏳ Analyzing knowledge base...';
            statusSpan.style.color = 'var(--primary, #007bff)';
        }

        try {
            const response = await fetch('/api/admin/example-questions/generate', {
                method: 'POST',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to generate example questions');
            }

            // Success
            this.showToast(data.message, 'success');
            if (statusSpan) {
                statusSpan.innerHTML = `<i class="fas fa-check"></i> Generated ${data.details.count} questions`;
                statusSpan.style.color = 'var(--success, #28a745)';
            }

            // Load and display the questions
            await this.loadExampleQuestions();

        } catch (error) {
            console.error('Error generating example questions:', error);
            this.showToast(error.message, 'error');
            if (statusSpan) {
                statusSpan.innerHTML = '<i class="fas fa-xmark"></i> Generation failed';
                statusSpan.style.color = 'var(--danger, #dc3545)';
            }
        } finally {
            // Re-enable button
            if (generateButton) {
                generateButton.disabled = false;
                generateButton.textContent = 'Generate Example Questions';
            }
        }
    }

    async loadExampleQuestions() {
        const previewDiv = document.getElementById('example-questions-preview');
        const questionsList = document.getElementById('questions-list');

        if (!previewDiv || !questionsList) return;

        try {
            const response = await fetch('/api/example-questions');
            const data = await response.json();

            if (data.questions && data.questions.length > 0) {
                // Show preview
                previewDiv.style.display = 'block';

                // Build list
                questionsList.innerHTML = data.questions.map(q =>
                    `<li>${this.escapeHtml(q)}</li>`
                ).join('');
            } else {
                previewDiv.style.display = 'none';
            }
        } catch (error) {
            console.error('Error loading example questions:', error);
            previewDiv.style.display = 'none';
        }
    }

    toggleDescriptionForDoc(button) {
        // Find the doc-filename container (table cell)
        const docFilename = button.closest('.doc-filename');
        if (!docFilename) return;

        // Find the description div
        const descriptionDiv = docFilename.querySelector('.document-description');
        if (!descriptionDiv) return;

        // Toggle visibility
        if (descriptionDiv.classList.contains('visible')) {
            // Hide description
            descriptionDiv.classList.remove('visible');
            button.classList.remove('active');
            button.title = 'Show description';
        } else {
            // Show description
            descriptionDiv.classList.add('visible');
            button.classList.add('active');
            button.title = 'Hide description';
        }
    }

    /**
     * Format document age with warning for old documents
     * @param {number|null} ageDays - Age in days
     * @param {string|null} dateAdded - ISO date string for tooltip
     * @returns {string} Formatted HTML for age display
     */
    formatDocumentAge(ageDays, dateAdded) {
        if (ageDays === null || ageDays === undefined) {
            return '<span class="doc-age">Unknown</span>';
        }

        let ageText = '';
        let warningIcon = '';
        let ageClass = 'doc-age';

        // Calculate human-readable age
        if (ageDays < 7) {
            ageText = ageDays === 1 ? '1 day old' : `${ageDays} days old`;
        } else if (ageDays < 31) {
            const weeks = Math.floor(ageDays / 7);
            ageText = weeks === 1 ? '1 week old' : `${weeks} weeks old`;
        } else if (ageDays < 365) {
            const months = Math.floor(ageDays / 30);
            ageText = months === 1 ? '1 month old' : `${months} months old`;
        } else {
            // Warning for documents older than 12 months
            const years = Math.floor(ageDays / 365);
            const months = Math.floor((ageDays % 365) / 30);

            if (years === 1) {
                ageText = months > 0 ? `1 year ${months} months old` : '1 year old';
            } else {
                ageText = months > 0 ? `${years} years ${months} months old` : `${years} years old`;
            }

            warningIcon = '⚠️ ';
            ageClass += ' doc-age-warning';
        }

        // Format date for tooltip
        let tooltipDate = '';
        if (dateAdded) {
            try {
                const date = new Date(dateAdded);
                tooltipDate = date.toLocaleString('en-GB', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            } catch (e) {
                tooltipDate = dateAdded;
            }
        }

        return `<span class="${ageClass}" title="Added: ${this.escapeHtml(tooltipDate)}">${warningIcon}${ageText}</span>`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

/**
 * Usage Analytics Manager
 * Handles usage monitoring and statistics
 */
class UsageAnalytics {
    constructor() {
        this.currentTimeRange = 7; // Default: last 7 days
        this.chart = null;
        this.init();
    }

    init() {
        // Setup time range button listeners
        document.querySelectorAll('.time-range-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.time-range-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');

                const days = e.target.dataset.days;
                this.currentTimeRange = days === 'all' ? null : parseInt(days);
                this.loadAnalytics();
            });
        });

        // Load initial analytics when usage tab is shown
        const usageTab = document.querySelector('[data-tab="usage"]');
        if (usageTab) {
            usageTab.addEventListener('click', () => {
                // Small delay to ensure tab content is visible
                setTimeout(() => this.loadAnalytics(), 100);
            });
        }
    }

    async loadAnalytics() {
        try {
            const params = this.currentTimeRange ? `?days=${this.currentTimeRange}` : '';
            const response = await fetch(`/api/admin/usage/analytics${params}`);

            if (!response.ok) {
                throw new Error('Failed to load analytics');
            }

            const data = await response.json();
            this.renderOverviewStats(data.overview, data.channel_breakdown);
            this.renderTrendsChart(data.daily_stats);
            this.renderUserTable(data.user_activity);

        } catch (error) {
            console.error('Error loading analytics:', error);
            adminPanel.showToast('Error loading usage analytics', 'error');
        }
    }

    renderOverviewStats(overview, channelBreakdown) {
        document.getElementById('stat-total-queries').textContent = overview.total_queries.toLocaleString();
        document.getElementById('stat-unique-users').textContent = overview.unique_users.toLocaleString();
        document.getElementById('stat-avg-queries').textContent = overview.avg_queries_per_user.toFixed(1);

        // Calculate channel split
        const email = channelBreakdown.email || 0;
        const webchat = channelBreakdown.webchat || 0;
        const total = email + webchat;

        if (total > 0) {
            const emailPct = Math.round((email / total) * 100);
            const webchatPct = Math.round((webchat / total) * 100);
            document.getElementById('stat-channel-split').textContent = `${emailPct}% / ${webchatPct}%`;
        } else {
            document.getElementById('stat-channel-split').textContent = 'N/A';
        }
    }

    renderTrendsChart(dailyStats) {
        const ctx = document.getElementById('query-trends-chart');
        if (!ctx) return;

        // Destroy existing chart if it exists
        if (this.chart) {
            this.chart.destroy();
        }

        // Prepare data
        const labels = dailyStats.map(stat => stat.date);
        const data = dailyStats.map(stat => stat.count);

        // Create chart
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Queries',
                    data: data,
                    borderColor: 'rgb(0, 123, 255)',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    tension: 0.3,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    }

    renderUserTable(userActivity) {
        const tbody = document.getElementById('users-table-body');
        if (!tbody) return;

        if (userActivity.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-secondary, #666);">No user activity in this period</td></tr>';
            return;
        }

        tbody.innerHTML = userActivity.map(user => `
            <tr>
                <td>${this.escapeHtml(user.sender)}</td>
                <td><span class="badge badge-${user.channel.toLowerCase()}">${user.channel}</span></td>
                <td>${user.query_count}</td>
                <td>
                    <button class="btn-view-queries" onclick="usageAnalytics.viewUserQueries('${this.escapeHtml(user.sender)}')">
                        View Queries
                    </button>
                </td>
            </tr>
        `).join('');
    }

    async viewUserQueries(sender) {
        try {
            const params = this.currentTimeRange ? `?days=${this.currentTimeRange}` : '';
            const response = await fetch(`/api/admin/usage/user/${encodeURIComponent(sender)}${params}`);

            if (!response.ok) {
                throw new Error('Failed to load user queries');
            }

            const data = await response.json();
            this.showQueriesModal(sender, data.queries);

        } catch (error) {
            console.error('Error loading user queries:', error);
            adminPanel.showToast('Error loading user queries', 'error');
        }
    }

    showQueriesModal(sender, queries) {
        const modalHtml = `
            <div class="modal-overlay" onclick="this.remove()">
                <div class="modal-content" onclick="event.stopPropagation()" style="max-width: 800px;">
                    <div class="modal-header">
                        <h3>Queries from ${this.escapeHtml(sender)}</h3>
                        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
                    </div>
                    <div class="modal-body" style="max-height: 600px; overflow-y: auto;">
                        ${queries.length === 0 ? '<p>No queries found</p>' : queries.map((q, i) => `
                            <div class="query-item" style="margin-bottom: 1rem; padding: 1rem; background: var(--bg-secondary, #f8f9fa); border-radius: 6px;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                                    <strong>#${i + 1}</strong>
                                    <span style="color: var(--text-secondary, #666); font-size: 0.875rem;">
                                        ${new Date(q.timestamp).toLocaleString()}
                                    </span>
                                </div>
                                ${q.subject ? `<div style="color: var(--text-secondary, #666); font-size: 0.875rem; margin-bottom: 0.5rem;"><em>Subject: ${this.escapeHtml(q.subject)}</em></div>` : ''}
                                <div class="query-content" style="white-space: pre-wrap; word-wrap: break-word;">
                                    ${this.truncateAndMakeExpandable(q.content, 200, `query-${i}`)}
                                </div>
                                <span class="badge badge-${q.channel.toLowerCase()}" style="margin-top: 0.5rem; display: inline-block;">${q.channel}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    truncateAndMakeExpandable(text, maxLength, id) {
        if (text.length <= maxLength) {
            return this.escapeHtml(text);
        }

        const truncated = text.substring(0, maxLength);
        return `
            <span id="${id}-short">${this.escapeHtml(truncated)}...
                <a href="#" onclick="document.getElementById('${id}-short').style.display='none'; document.getElementById('${id}-full').style.display='block'; return false;" style="color: var(--primary, #007bff);">
                    [Show More]
                </a>
            </span>
            <span id="${id}-full" style="display: none;">${this.escapeHtml(text)}
                <a href="#" onclick="document.getElementById('${id}-full').style.display='none'; document.getElementById('${id}-short').style.display='block'; return false;" style="color: var(--primary, #007bff);">
                    [Show Less]
                </a>
            </span>
        `;
    }

    async analyzeTopics() {
        const btn = document.querySelector('.btn-analyze-topics');
        const originalHtml = btn.innerHTML;

        try {
            // Disable button and show loading
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';

            const params = this.currentTimeRange ? `?days=${this.currentTimeRange}` : '';
            const response = await fetch(`/api/admin/usage/topics${params}`, {
                method: 'POST'
            });

            if (!response.ok) {
                throw new Error('Failed to analyze topics');
            }

            const data = await response.json();
            this.renderTopics(data.topics);
            adminPanel.showToast(`Identified ${data.topics.length} topics from ${data.total_queries} queries`, 'success');

        } catch (error) {
            console.error('Error analyzing topics:', error);
            adminPanel.showToast('Error analyzing topics', 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }

    renderTopics(topics) {
        const container = document.getElementById('topics-container');
        if (!container) return;

        if (topics.length === 0) {
            container.innerHTML = '<p class="topics-placeholder">No topics identified. Try a longer time period or check if there are queries in the database.</p>';
            return;
        }

        container.innerHTML = topics.map((topic, i) => `
            <div class="topic-card">
                <div class="topic-header">
                    <div class="topic-name">${this.escapeHtml(topic.topic_name)}</div>
                    <div class="topic-stats">${topic.query_count} queries (${topic.percentage}%)</div>
                </div>
                <div class="topic-description">${this.escapeHtml(topic.description)}</div>
                <div class="topic-samples">
                    <div class="topic-samples-title">Sample Queries</div>
                    ${topic.sample_queries.slice(0, 3).map((query, j) => {
                        const truncated = query.length > 100;
                        const displayText = truncated ? query.substring(0, 100) : query;
                        return `
                            <div class="sample-query ${truncated ? 'truncated' : ''}"
                                 id="topic-${i}-query-${j}"
                                 onclick="usageAnalytics.toggleQueryExpand('topic-${i}-query-${j}', ${JSON.stringify(query).replace(/"/g, '&quot;')})">
                                ${this.escapeHtml(displayText)}
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `).join('');
    }

    toggleQueryExpand(elementId, fullText) {
        const element = document.getElementById(elementId);
        if (!element) return;

        if (element.classList.contains('expanded')) {
            // Collapse
            element.classList.remove('expanded');
            const truncated = fullText.substring(0, 100);
            element.textContent = truncated;
        } else {
            // Expand
            element.classList.add('expanded');
            element.textContent = fullText;
        }
    }

    refresh() {
        this.loadAnalytics();
        adminPanel.showToast('Analytics refreshed', 'success');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

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
                        <span style="padding: 0.125rem 0.5rem; background: #fee2e2; color: #991b1b; border-radius: 0.25rem; font-size: 0.75rem;">${item.channel}</span>
                    </div>
                    <span style="color: var(--text-secondary); font-size: 0.875rem;">${this.formatDate(item.submitted_at)}</span>
                </div>
                <div style="background: var(--background); padding: 0.75rem; border-radius: 0.375rem; margin-bottom: 0.5rem; font-size: 0.875rem; color: var(--text-secondary);">
                    ${this.escapeHtml(item.response_content)}
                </div>
                ${item.comment ? `
                    <div style="padding: 0.5rem; border-left: 3px solid #ef4444; background: #fef2f2; border-radius: 0.25rem; font-size: 0.875rem;">
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

// Initialize admin panel when page loads
const adminPanel = new AdminPanel();
const usageAnalytics = new UsageAnalytics();
const feedbackAnalytics = new FeedbackAnalytics();

// Expose to global scope for inline onclick handlers
window.adminPanel = adminPanel;
window.usageAnalytics = usageAnalytics;
window.feedbackAnalytics = feedbackAnalytics;
