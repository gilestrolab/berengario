/**
 * Admin Panel JavaScript
 * Handles team management and document operations
 */

class AdminPanel {
    constructor() {
        this.documents = [];
        this.crawledUrls = [];
        this.backups = [];
        this.sortState = {}; // Track sort state per section
        this.teamMembers = [];
        this.teamPage = 1;
        this.teamPageSize = 20;
        this.teamSearchDebounceTimer = null;
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

            // Multi-tenant mode: show Team tab
            if (config.multi_tenant) {
                this.multiTenant = true;
                const teamTabBtn = document.getElementById('team-tab-btn');
                if (teamTabBtn) teamTabBtn.style.display = '';
                this.switchTab('team');
                this.loadTeamData();
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
            const canDownload = ['manual', 'file', 'attachment'].includes(doc.source_type);
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

            // Enhancement indicator - show green star icon if enhanced
            const enhancementIndicator = doc.enhanced ? `
                <i class="fas fa-star enhancement-indicator" title="Enhanced with AI (${doc.enhancement_count} enhancements: narrative + Q&A)"></i>
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
                            ${enhancementIndicator}
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
            const canDownload = ['manual', 'file', 'attachment'].includes(doc.source_type);
            const canView = doc.source_type === 'email';
            const displayName = this.getDisplayName(doc);

            const description = this.descriptions && this.descriptions[doc.filename];
            const hasDescription = description && description.description;
            const descriptionText = hasDescription ? this.escapeHtml(description.description) : '';

            const infoButton = hasDescription ? `
                <button class="btn-info" title="Show/hide description">ℹ️</button>
            ` : '';

            // Enhancement indicator - show green star icon if enhanced
            const enhancementIndicator = doc.enhanced ? `
                <i class="fas fa-star enhancement-indicator" title="Enhanced with AI (${doc.enhancement_count} enhancements: narrative + Q&A)"></i>
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
                            ${enhancementIndicator}
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

    async downloadDocument(fileHash, filename) {
        try {
            const downloadUrl = `/api/admin/documents/${fileHash}/download`;

            // Fetch with credentials to include session cookies
            const response = await fetch(downloadUrl, {
                method: 'GET',
                credentials: 'same-origin',
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Download failed: ${response.status}`);
            }

            // Get the blob from response
            const blob = await response.blob();

            // Create a download link and trigger it
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.style.display = 'none';

            // Add to DOM, click, and remove
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            // Clean up the object URL
            window.URL.revokeObjectURL(url);

            this.showToast(`Downloaded ${filename}`, 'success');
        } catch (error) {
            console.error('Download error:', error);
            this.showToast(`Download failed: ${error.message}`, 'error');
        }
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
            <div class="empty-state" style="color: var(--danger, #A3423A);">
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
                        <button class="btn-restore-backup" onclick="adminPanel.restoreBackup('${this.escapeHtml(backup.filename)}')">
                            Restore
                        </button>
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

    async restoreBackup(filename) {
        if (!confirm(`Restore from backup "${filename}"?\n\nThis will REPLACE your current data with the backup contents.\nA safety backup will be created automatically before restoring.\n\nThis operation runs in the background. You will receive an email when complete.`)) {
            return;
        }

        try {
            const response = await fetch(`/api/admin/backups/${filename}/restore`, {
                method: 'POST',
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to start restore');
            }

            this.showToast(data.message, 'success');
        } catch (error) {
            console.error('Error restoring backup:', error);
            this.showToast(error.message, 'error');
        }
    }

    async handleRestoreFileSelected(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Reset the file input so the same file can be selected again
        event.target.value = '';

        if (!file.name.endsWith('.zip')) {
            this.showToast('Please select a ZIP file', 'error');
            return;
        }

        if (!confirm(`Restore from uploaded file "${file.name}"?\n\nThis will REPLACE your current data with the backup contents.\nA safety backup will be created automatically before restoring.\n\nThis operation runs in the background. You will receive an email when complete.`)) {
            return;
        }

        const button = document.querySelector('.btn-upload-restore');
        try {
            if (button) {
                button.disabled = true;
                button.textContent = 'Uploading & restoring...';
            }

            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch('/api/admin/backup/restore', {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to start restore');
            }

            this.showToast(data.message, 'success');
        } catch (error) {
            console.error('Error uploading restore:', error);
            this.showToast(error.message, 'error');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = 'Upload & Restore Backup';
            }
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

            <div class="model-card">
                <h4>Reranking</h4>
                <div class="model-detail">
                    <span class="model-detail-label">Status:</span>
                    <span class="model-detail-value">${data.reranking.active
                        ? '<span style="color: #4CAF50;">Active</span>'
                        : data.reranking.enabled
                            ? '<span style="color: #FF9800;">Enabled (no API key)</span>'
                            : '<span style="color: #999;">Disabled</span>'
                    }</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Provider:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.reranking.provider)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Model:</span>
                    <span class="model-detail-value">${this.escapeHtml(data.reranking.model)}</span>
                </div>
                <div class="model-detail">
                    <span class="model-detail-label">Top N:</span>
                    <span class="model-detail-value">${data.reranking.top_n}</span>
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
                statusSpan.style.color = 'var(--success, #5B8C7A)';
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
                statusSpan.style.color = 'var(--danger, #A3423A)';
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
            statusSpan.style.color = 'var(--primary, #7A5C3E)';
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
                statusSpan.style.color = 'var(--success, #5B8C7A)';
            }

            // Load and display the questions
            await this.loadExampleQuestions();

        } catch (error) {
            console.error('Error generating example questions:', error);
            this.showToast(error.message, 'error');
            if (statusSpan) {
                statusSpan.innerHTML = '<i class="fas fa-xmark"></i> Generation failed';
                statusSpan.style.color = 'var(--danger, #A3423A)';
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

    // === Team Management Methods (Multi-Tenant) ===

    async loadTeamData() {
        await Promise.all([
            this.loadTeamMembers(),
            this.loadInviteInfo(),
            this.loadTeamSettings(),
        ]);
        this.setupTeamEventListeners();
    }

    setupTeamEventListeners() {
        const emailInput = document.getElementById('team-member-email');
        if (emailInput) {
            emailInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.addTeamMember();
                }
            });
        }

        const addBtn = document.getElementById('add-team-member-btn');
        if (addBtn) addBtn.addEventListener('click', () => this.addTeamMember());

        // Search and filter listeners
        const searchInput = document.getElementById('team-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this.teamSearchDebounceTimer);
                this.teamSearchDebounceTimer = setTimeout(() => {
                    this.teamPage = 1;
                    this.renderTeamMembers();
                }, 200);
            });
        }

        const roleFilter = document.getElementById('team-role-filter');
        if (roleFilter) {
            roleFilter.addEventListener('change', () => {
                this.teamPage = 1;
                this.renderTeamMembers();
            });
        }

        const copyBtn = document.getElementById('copy-invite-btn');
        if (copyBtn) copyBtn.addEventListener('click', () => this.copyInviteCode());

        const regenBtn = document.getElementById('regenerate-invite-btn');
        if (regenBtn) regenBtn.addEventListener('click', () => this.regenerateInviteCode());

        const qrBtn = document.getElementById('show-qr-btn');
        if (qrBtn) qrBtn.addEventListener('click', () => this.toggleQRCode());

        const approvalToggle = document.getElementById('join-approval-toggle');
        if (approvalToggle) {
            approvalToggle.addEventListener('change', (e) => {
                this.toggleJoinApproval(e.target.checked);
            });
        }

        const saveSettingsBtn = document.getElementById('save-team-settings-btn');
        if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', () => this.saveTeamSettings());

        const slugInput = document.getElementById('team-slug-input');
        if (slugInput) {
            slugInput.addEventListener('input', () => {
                const preview = document.getElementById('slug-email-preview');
                if (preview) preview.textContent = slugInput.value || 'slug';
            });
        }
    }

    async loadTeamMembers() {
        try {
            const [membersResp, requestsResp] = await Promise.all([
                fetch('/api/admin/team', { credentials: 'include' }),
                fetch('/api/admin/tenant/join-requests', { credentials: 'include' }),
            ]);
            const members = await membersResp.json();
            const requests = await requestsResp.json();

            // Normalize members
            const normalized = members.map(m => ({
                ...m,
                type: 'member',
            }));

            // Normalize pending join requests
            const pending = (Array.isArray(requests) ? requests : []).map(r => ({
                id: r.id,
                email: r.email,
                role: 'pending',
                type: 'pending',
                created_at: r.created_at,
            }));

            // Pending first, then members sorted by email
            this.teamMembers = [
                ...pending.sort((a, b) => a.email.localeCompare(b.email)),
                ...normalized.sort((a, b) => a.email.localeCompare(b.email)),
            ];
            this.teamPage = 1;
            this.renderTeamMembers();
        } catch (e) {
            console.error('Failed to load team members:', e);
        }
    }

    getFilteredTeamMembers() {
        const searchInput = document.getElementById('team-search-input');
        const roleFilter = document.getElementById('team-role-filter');
        const searchText = (searchInput?.value || '').toLowerCase();
        const roleValue = roleFilter?.value || 'all';

        return this.teamMembers.filter(m => {
            if (searchText && !m.email.toLowerCase().includes(searchText)) return false;
            if (roleValue !== 'all' && m.role !== roleValue) return false;
            return true;
        });
    }

    renderTeamMembers() {
        const container = document.getElementById('team-members-list');
        const filtered = this.getFilteredTeamMembers();
        const totalPages = Math.max(1, Math.ceil(filtered.length / this.teamPageSize));

        // Clamp current page
        if (this.teamPage > totalPages) this.teamPage = totalPages;
        if (this.teamPage < 1) this.teamPage = 1;

        const start = (this.teamPage - 1) * this.teamPageSize;
        const pageMembers = filtered.slice(start, start + this.teamPageSize);

        // Update count label
        const countLabel = document.getElementById('team-member-count');
        if (countLabel) {
            const filterActive = filtered.length !== this.teamMembers.length;
            countLabel.textContent = filterActive
                ? `${filtered.length} of ${this.teamMembers.length}`
                : `${this.teamMembers.length}`;
        }

        if (!this.teamMembers.length) {
            container.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.875rem; padding: 1rem;">No team members</div>';
            this.renderTeamPagination(0, 0);
            return;
        }

        if (!filtered.length) {
            container.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.875rem; padding: 1rem;">No members match filters</div>';
            this.renderTeamPagination(0, 0);
            return;
        }

        container.innerHTML = pageMembers.map(m => {
            if (m.type === 'pending') {
                const dateStr = m.created_at ? new Date(m.created_at).toLocaleDateString() : '';
                return `
                    <div class="team-member-row">
                        <div class="team-member-info">
                            <span class="team-member-email">${this.escapeHtml(m.email)}</span>
                            <span class="role-badge role-pending">pending</span>
                            <span class="team-member-date">${dateStr}</span>
                        </div>
                        <div class="team-member-actions">
                            <button class="btn-approve-request" onclick="adminPanel.approveJoinRequest(${m.id})" title="Approve">
                                <i class="fas fa-check"></i>
                            </button>
                            <button class="btn-reject-request" onclick="adminPanel.rejectJoinRequest(${m.id})" title="Reject">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>`;
            }
            return `
                <div class="team-member-row">
                    <div class="team-member-info">
                        <span class="team-member-email">${this.escapeHtml(m.email)}</span>
                        <span class="role-badge role-${m.role}">${m.role}</span>
                    </div>
                    <div class="team-member-actions">
                        <select class="team-select role-select" data-user-id="${m.id}">
                            <option value="querier" ${m.role === 'querier' ? 'selected' : ''}>Querier</option>
                            <option value="teacher" ${m.role === 'teacher' ? 'selected' : ''}>Teacher</option>
                            <option value="admin" ${m.role === 'admin' ? 'selected' : ''}>Admin</option>
                        </select>
                        <button class="btn-remove-member" onclick="adminPanel.removeTeamMember(${m.id})" title="Remove member">
                            <i class="fas fa-trash-alt"></i>
                        </button>
                    </div>
                </div>`;
        }).join('');

        // Add change listeners for role selects
        container.querySelectorAll('.role-select').forEach(sel => {
            sel.addEventListener('change', (e) => {
                this.changeTeamMemberRole(e.target.dataset.userId, e.target.value);
            });
        });

        this.renderTeamPagination(totalPages, filtered.length);
    }

    renderTeamPagination(totalPages, totalFiltered) {
        const paginationContainer = document.getElementById('team-pagination');
        if (!paginationContainer) return;

        if (totalPages <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }

        let buttons = '';
        buttons += `<button class="team-page-btn" data-page="prev" ${this.teamPage <= 1 ? 'disabled' : ''}>&lsaquo;</button>`;

        // Show max 5 page buttons with ellipsis
        const maxButtons = 5;
        let startPage = Math.max(1, this.teamPage - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        if (startPage > 1) {
            buttons += `<button class="team-page-btn" data-page="1">1</button>`;
            if (startPage > 2) buttons += `<span class="team-page-ellipsis">&hellip;</span>`;
        }

        for (let i = startPage; i <= endPage; i++) {
            buttons += `<button class="team-page-btn ${i === this.teamPage ? 'active' : ''}" data-page="${i}">${i}</button>`;
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) buttons += `<span class="team-page-ellipsis">&hellip;</span>`;
            buttons += `<button class="team-page-btn" data-page="${totalPages}">${totalPages}</button>`;
        }

        buttons += `<button class="team-page-btn" data-page="next" ${this.teamPage >= totalPages ? 'disabled' : ''}>&rsaquo;</button>`;

        paginationContainer.innerHTML = buttons;

        // Wire up page button clicks
        paginationContainer.querySelectorAll('.team-page-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const page = btn.dataset.page;
                if (page === 'prev') this.teamPage--;
                else if (page === 'next') this.teamPage++;
                else this.teamPage = parseInt(page);
                this.renderTeamMembers();
            });
        });
    }

    async addTeamMember() {
        const emailInput = document.getElementById('team-member-email');
        const roleSelect = document.getElementById('team-member-role');
        const email = emailInput.value.trim();
        const role = roleSelect.value;

        if (!email) {
            this.showToast('Please enter an email', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/admin/team', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, role }),
                credentials: 'include',
            });
            const data = await resp.json();

            if (resp.ok) {
                emailInput.value = '';
                this.showToast(`Added ${email} as ${role}`, 'success');
                await this.loadTeamMembers();
            } else {
                this.showToast(data.detail || data.message || 'Failed to add member', 'error');
            }
        } catch (e) {
            this.showToast('Failed to add member', 'error');
        }
    }

    async removeTeamMember(userId) {
        if (!confirm('Remove this team member?')) return;

        try {
            const resp = await fetch(`/api/admin/team/${userId}`, {
                method: 'DELETE',
                credentials: 'include',
            });

            if (resp.ok) {
                this.showToast('Member removed', 'success');
                await this.loadTeamMembers();
            } else {
                const data = await resp.json();
                this.showToast(data.detail || 'Failed to remove', 'error');
            }
        } catch (e) {
            this.showToast('Failed to remove member', 'error');
        }
    }

    async changeTeamMemberRole(userId, newRole) {
        try {
            const resp = await fetch(`/api/admin/team/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: newRole }),
                credentials: 'include',
            });

            if (resp.ok) {
                this.showToast(`Role updated to ${newRole}`, 'success');
            } else {
                const data = await resp.json();
                this.showToast(data.detail || 'Failed to update role', 'error');
                await this.loadTeamMembers(); // Revert UI
            }
        } catch (e) {
            this.showToast('Failed to update role', 'error');
            await this.loadTeamMembers();
        }
    }

    async loadInviteInfo() {
        try {
            const resp = await fetch('/api/admin/tenant/invite', { credentials: 'include' });
            const data = await resp.json();

            document.getElementById('invite-code-display').textContent = data.invite_code || '---';
            document.getElementById('join-approval-toggle').checked = data.join_approval_required || false;
        } catch (e) {
            console.error('Failed to load invite info:', e);
        }
    }

    async copyInviteCode() {
        const code = document.getElementById('invite-code-display').textContent;
        if (code && code !== '---') {
            try {
                await navigator.clipboard.writeText(code);
                this.showToast('Invite code copied!', 'success');
            } catch (e) {
                // Fallback for non-HTTPS
                const textarea = document.createElement('textarea');
                textarea.value = code;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
                this.showToast('Invite code copied!', 'success');
            }
        }
    }

    async regenerateInviteCode() {
        if (!confirm('Generate a new invite code? The old code will stop working.')) return;

        try {
            const resp = await fetch('/api/admin/tenant/invite/regenerate', {
                method: 'POST',
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.invite_code) {
                document.getElementById('invite-code-display').textContent = data.invite_code;
                this.showToast('Invite code regenerated', 'success');
            }
        } catch (e) {
            this.showToast('Failed to regenerate code', 'error');
        }
    }

    toggleQRCode() {
        const container = document.getElementById('qr-container');
        if (!container.classList.contains('visible')) {
            const img = document.getElementById('qr-image');
            img.style.display = 'none';
            container.classList.add('visible');
            container.innerHTML = '<i class="fas fa-spinner fa-spin" style="font-size:1.5rem;color:var(--text-secondary,#8C8279)"></i>';
            const qrImg = document.createElement('img');
            qrImg.id = 'qr-image';
            qrImg.alt = 'Invite QR Code';
            qrImg.className = 'qr-image';
            qrImg.onload = () => {
                container.innerHTML = '';
                container.appendChild(qrImg);
            };
            qrImg.onerror = () => {
                container.innerHTML = '<span style="color:var(--text-secondary)">Failed to load QR code</span>';
            };
            qrImg.src = '/api/admin/tenant/invite/qr?' + Date.now();
        } else {
            container.classList.remove('visible');
        }
    }

    async toggleJoinApproval(required) {
        try {
            await fetch('/api/admin/tenant/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ join_approval_required: required }),
                credentials: 'include',
            });
            this.showToast(required ? 'Approval now required' : 'Open joining enabled', 'success');
        } catch (e) {
            this.showToast('Failed to update setting', 'error');
        }
    }

    async approveJoinRequest(requestId) {
        try {
            const resp = await fetch(`/api/admin/tenant/join-requests/${requestId}/approve`, {
                method: 'POST',
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                this.showToast(data.message, 'success');
                await this.loadTeamMembers();
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (e) {
            this.showToast('Failed to approve request', 'error');
        }
    }

    async rejectJoinRequest(requestId) {
        if (!confirm('Reject this join request?')) return;

        try {
            const resp = await fetch(`/api/admin/tenant/join-requests/${requestId}/reject`, {
                method: 'POST',
                credentials: 'include',
            });
            const data = await resp.json();

            if (data.success) {
                this.showToast(data.message, 'success');
                await this.loadTeamMembers();
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (e) {
            this.showToast('Failed to reject request', 'error');
        }
    }

    async loadTeamSettings() {
        try {
            const resp = await fetch('/api/admin/tenant/details', { credentials: 'include' });
            if (!resp.ok) return;
            const data = await resp.json();

            const nameInput = document.getElementById('team-name-input');
            const orgInput = document.getElementById('team-org-input');
            const descInput = document.getElementById('team-desc-input');
            const slugInput = document.getElementById('team-slug-input');
            const preview = document.getElementById('slug-email-preview');

            if (nameInput) nameInput.value = data.name || '';
            if (orgInput) orgInput.value = data.organization || '';
            if (descInput) descInput.value = data.description || '';
            if (slugInput) slugInput.value = data.slug || '';
            if (preview) preview.textContent = data.slug || 'slug';
        } catch (e) {
            console.error('Failed to load team settings:', e);
        }
    }

    async saveTeamSettings() {
        const orgInput = document.getElementById('team-org-input');
        const descInput = document.getElementById('team-desc-input');
        const slugInput = document.getElementById('team-slug-input');

        const body = {};
        if (orgInput) body.organization = orgInput.value.trim();
        if (descInput) body.description = descInput.value.trim();
        if (slugInput) body.slug = slugInput.value.trim();

        try {
            const resp = await fetch('/api/admin/tenant/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                credentials: 'include',
            });
            const data = await resp.json();

            if (resp.ok && data.success) {
                this.showToast('Settings saved', 'success');
                // Update slug preview from server response
                if (data.details) {
                    const preview = document.getElementById('slug-email-preview');
                    if (preview) preview.textContent = data.details.slug || 'slug';
                    if (slugInput) slugInput.value = data.details.slug || '';
                }
            } else {
                this.showToast(data.detail || data.message || 'Failed to save settings', 'error');
            }
        } catch (e) {
            this.showToast('Failed to save settings', 'error');
        }
    }

}
