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
        this.backups = [];
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

        const itemsHtml = documents.map(doc => {
            // Determine which buttons to show based on source type
            const canDownload = ['manual', 'file'].includes(doc.source_type);
            const canView = doc.source_type === 'email';

            // Get display name (improved for emails)
            const displayName = this.getDisplayName(doc);

            // Get description if available
            const description = this.descriptions && this.descriptions[doc.filename];
            const hasDescription = description && description.description;

            const downloadButton = canDownload ? `
                <button class="btn-download" onclick="adminPanel.downloadDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(doc.filename)}')">
                    Download
                </button>
            ` : '';

            const viewButton = canView ? `
                <button class="btn-view" onclick="adminPanel.viewDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')">
                    View
                </button>
            ` : '';

            const descriptionHtml = hasDescription ? `
                <div class="document-description">
                    <button class="description-toggle" onclick="adminPanel.toggleDescription(this)">
                        <span class="toggle-icon">▶</span>
                        <span class="toggle-text">Show Description</span>
                    </button>
                    <div class="description-content" style="display: none;">
                        ${this.escapeHtml(description.description)}
                    </div>
                </div>
            ` : '';

            return `
                <div class="document-item">
                    <div class="document-info">
                        <div class="filename" title="${this.escapeHtml(displayName)}">${this.escapeHtml(displayName)}</div>
                        <div class="metadata">
                            Type: ${this.escapeHtml(doc.file_type || 'unknown')} |
                            Hash: ${this.escapeHtml(doc.file_hash.substring(0, 12))}...
                            ${description ? `| Chunks: ${description.chunk_count}` : ''}
                        </div>
                        ${descriptionHtml}
                    </div>
                    <div class="document-actions">
                        ${viewButton}
                        ${downloadButton}
                        <button class="btn-delete" onclick="adminPanel.deleteDocument('${this.escapeHtml(doc.file_hash)}', '${this.escapeHtml(displayName)}')">
                            Delete
                        </button>
                    </div>
                </div>
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
                    ${itemsHtml}
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
                            fileItem.textContent = `✓ ${file.name} - Successfully processed (${data.chunks_added || 0} chunks)`;
                        } else {
                            fileItem.className = 'upload-file-item upload-file-error';
                            fileItem.textContent = `✗ ${file.name} - ${data.detail || 'Upload failed'}`;
                        }
                    }
                } catch (error) {
                    const fileItem = document.getElementById(`upload-file-${i}`);
                    if (fileItem) {
                        fileItem.className = 'upload-file-item upload-file-error';
                        fileItem.textContent = `✗ ${file.name} - ${error.message}`;
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
                statusSpan.textContent = '✓ Saved successfully';
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
                statusSpan.textContent = '✗ Save failed';
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

    toggleDescription(button) {
        const descriptionContent = button.parentElement.querySelector('.description-content');
        const toggleIcon = button.querySelector('.toggle-icon');
        const toggleText = button.querySelector('.toggle-text');

        if (descriptionContent.style.display === 'none') {
            // Show description
            descriptionContent.style.display = 'block';
            toggleIcon.textContent = '▼';
            toggleText.textContent = 'Hide Description';
        } else {
            // Hide description
            descriptionContent.style.display = 'none';
            toggleIcon.textContent = '▶';
            toggleText.textContent = 'Show Description';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize admin panel when page loads
const adminPanel = new AdminPanel();
