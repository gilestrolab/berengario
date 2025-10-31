// RAGInbox Web Interface - Frontend Logic

class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.queryInput = document.getElementById('query-input');
        this.sendBtn = document.getElementById('send-btn');
        this.clearBtn = document.getElementById('clear-btn');
        this.logoutBtn = document.getElementById('logout-btn');
        this.userEmailSpan = document.getElementById('user-email');
        this.loadingOverlay = document.getElementById('loading-overlay');
        this.toast = document.getElementById('toast');

        this.isLoading = false;
        this.sessionId = null;
        this.userEmail = null;

        this.init();
    }

    async init() {
        // Check authentication first
        const authenticated = await this.checkAuth();
        if (!authenticated) {
            // Redirect to login
            window.location.href = '/static/login.html';
            return;
        }

        // Load KB stats
        await this.loadStats();

        // Load conversation history
        await this.loadHistory();

        // Setup event listeners
        this.setupEventListeners();

        // Focus input
        this.queryInput.focus();
    }

    async checkAuth() {
        try {
            const response = await fetch('/api/auth/status', {
                credentials: 'include',
            });
            const data = await response.json();

            if (!data.authenticated) {
                return false;
            }

            // Store and display user email
            this.userEmail = data.email;
            if (this.userEmailSpan && this.userEmail) {
                this.userEmailSpan.textContent = this.userEmail;
                this.userEmailSpan.title = `Logged in as ${this.userEmail}`;
            }
            return true;
        } catch (error) {
            console.error('Error checking auth:', error);
            return false;
        }
    }

    setupEventListeners() {
        // Send button click
        this.sendBtn.addEventListener('click', () => this.sendQuery());

        // Enter key to send (Shift+Enter for new line)
        this.queryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendQuery();
            }
        });

        // Auto-resize textarea
        this.queryInput.addEventListener('input', () => {
            this.queryInput.style.height = 'auto';
            this.queryInput.style.height = this.queryInput.scrollHeight + 'px';
        });

        // Clear chat button
        this.clearBtn.addEventListener('click', () => this.clearSession());

        // Logout button
        this.logoutBtn.addEventListener('click', () => this.logout());
    }

    async loadStats() {
        try {
            const response = await fetch('/api/stats');
            const data = await response.json();

            document.getElementById('kb-documents').textContent = data.unique_documents;
            document.getElementById('kb-chunks').textContent = data.total_chunks;
        } catch (error) {
            console.error('Error loading stats:', error);
        }
    }

    async loadHistory() {
        try {
            const response = await fetch('/api/history');
            const data = await response.json();

            this.sessionId = data.session_id;

            // Remove welcome message if there are messages
            if (data.messages && data.messages.length > 0) {
                const welcomeMsg = this.messagesContainer.querySelector('.welcome-message');
                if (welcomeMsg) {
                    welcomeMsg.remove();
                }

                // Display all messages
                data.messages.forEach(msg => {
                    this.displayMessage(
                        msg.role,
                        msg.content,
                        msg.sources,
                        msg.attachments,
                        msg.timestamp
                    );
                });
            }
        } catch (error) {
            console.error('Error loading history:', error);
            this.showToast('Failed to load conversation history', 'error');
        }
    }

    async sendQuery() {
        const query = this.queryInput.value.trim();

        if (!query || this.isLoading) {
            return;
        }

        // Clear input and reset height
        this.queryInput.value = '';
        this.queryInput.style.height = 'auto';

        // Remove welcome message if present
        const welcomeMsg = this.messagesContainer.querySelector('.welcome-message');
        if (welcomeMsg) {
            welcomeMsg.remove();
        }

        // Display user message
        this.displayMessage('user', query);

        // Show loading state
        this.setLoading(true);

        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ query }),
                credentials: 'include', // Include cookies for session
            });

            const data = await response.json();

            if (data.success) {
                // Display assistant response
                this.displayMessage(
                    'assistant',
                    data.response,
                    data.sources,
                    data.attachments,
                    data.timestamp
                );
                this.sessionId = data.session_id;
            } else {
                // Display error
                this.displayMessage(
                    'assistant',
                    `Error: ${data.error || 'Unknown error occurred'}`,
                    null,
                    null,
                    data.timestamp
                );
                this.showToast('Failed to process query', 'error');
            }
        } catch (error) {
            console.error('Error sending query:', error);
            this.displayMessage(
                'assistant',
                'Sorry, I encountered an error processing your query. Please try again.',
                null,
                null,
                new Date().toISOString()
            );
            this.showToast('Network error', 'error');
        } finally {
            this.setLoading(false);
            this.queryInput.focus();
        }
    }

    displayMessage(role, content, sources = null, attachments = null, timestamp = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}-message`;

        // Avatar
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = role === 'user' ? 'U' : 'AI';

        // Content wrapper
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Message bubble
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = content;

        // Timestamp
        if (timestamp) {
            const timestampDiv = document.createElement('div');
            timestampDiv.className = 'message-timestamp';
            timestampDiv.textContent = this.formatTimestamp(timestamp);
            contentDiv.appendChild(timestampDiv);
        }

        contentDiv.appendChild(bubble);

        // Sources
        if (sources && sources.length > 0) {
            const sourcesDiv = this.createSourcesSection(sources);
            contentDiv.appendChild(sourcesDiv);
        }

        // Attachments
        if (attachments && attachments.length > 0) {
            const attachmentsDiv = this.createAttachmentsSection(attachments);
            contentDiv.appendChild(attachmentsDiv);
        }

        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    createSourcesSection(sources) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'message-sources';

        const header = document.createElement('div');
        header.className = 'sources-header';
        header.textContent = `Sources (${sources.length})`;
        header.addEventListener('click', () => {
            header.classList.toggle('expanded');
            list.classList.toggle('expanded');
        });

        const list = document.createElement('div');
        list.className = 'sources-list';

        sources.forEach(source => {
            const item = document.createElement('div');
            item.className = 'source-item';

            const filename = document.createElement('span');
            filename.className = 'source-filename';

            // Check if it's an email source
            if (source.sender && source.subject) {
                filename.textContent = `Email from ${source.sender}: "${source.subject}"`;
            } else {
                filename.textContent = source.filename || 'Unknown document';
            }

            const relevance = document.createElement('span');
            relevance.className = 'source-relevance';
            relevance.textContent = `(relevance: ${(source.score || 0).toFixed(2)})`;

            item.appendChild(filename);
            item.appendChild(relevance);
            list.appendChild(item);
        });

        sourcesDiv.appendChild(header);
        sourcesDiv.appendChild(list);

        return sourcesDiv;
    }

    createAttachmentsSection(attachments) {
        const attachmentsDiv = document.createElement('div');
        attachmentsDiv.className = 'message-attachments';

        attachments.forEach(attachment => {
            const link = document.createElement('a');
            link.className = 'attachment-chip';
            link.href = attachment.url;
            link.download = attachment.filename;
            link.target = '_blank';

            const icon = document.createElement('span');
            icon.className = 'attachment-icon';

            // Choose icon based on file type
            if (attachment.filename.endsWith('.ics')) {
                icon.textContent = '📅';
            } else if (attachment.filename.endsWith('.csv')) {
                icon.textContent = '📊';
            } else if (attachment.filename.endsWith('.json')) {
                icon.textContent = '📄';
            } else {
                icon.textContent = '📎';
            }

            const filename = document.createElement('span');
            filename.textContent = attachment.filename;

            link.appendChild(icon);
            link.appendChild(filename);
            attachmentsDiv.appendChild(link);
        });

        return attachmentsDiv;
    }

    async clearSession() {
        if (!confirm('Clear conversation history? This cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch('/api/session', {
                method: 'DELETE',
                credentials: 'include',
            });

            const data = await response.json();

            if (data.success) {
                // Clear messages
                this.messagesContainer.innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">💬</div>
                        <h2>Welcome to RAGInbox</h2>
                        <p>Ask me anything about the knowledge base documents.</p>
                        <p class="welcome-hint">Your conversation history will be saved during this session.</p>
                    </div>
                `;
                this.sessionId = null;
                this.showToast('Conversation cleared', 'success');
            } else {
                this.showToast('Failed to clear conversation', 'error');
            }
        } catch (error) {
            console.error('Error clearing session:', error);
            this.showToast('Network error', 'error');
        }
    }

    async logout() {
        if (!confirm('Are you sure you want to logout?')) {
            return;
        }

        try {
            const response = await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include',
            });

            const data = await response.json();

            if (data.success) {
                // Redirect to login page
                window.location.href = '/static/login.html';
            } else {
                this.showToast('Failed to logout', 'error');
            }
        } catch (error) {
            console.error('Error logging out:', error);
            this.showToast('Network error', 'error');
        }
    }

    setLoading(loading) {
        this.isLoading = loading;
        this.sendBtn.disabled = loading;
        this.queryInput.disabled = loading;

        if (loading) {
            this.loadingOverlay.classList.add('active');
        } else {
            this.loadingOverlay.classList.remove('active');
        }
    }

    showToast(message, type = 'info') {
        this.toast.textContent = message;
        this.toast.className = `toast ${type} show`;

        setTimeout(() => {
            this.toast.classList.remove('show');
        }, 3000);
    }

    scrollToBottom() {
        const container = document.getElementById('messages-container');
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 100);
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();

        // If today, just show time
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        // Otherwise show date and time
        return date.toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});
