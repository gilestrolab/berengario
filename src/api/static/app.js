// RAGInbox Web Interface - Frontend Logic

class ChatApp {
    constructor() {
        this.messagesContainer = document.getElementById('messages');
        this.queryInput = document.getElementById('query-input');
        this.sendBtn = document.getElementById('send-btn');
        this.logoutBtn = document.getElementById('logout-btn');
        this.userEmailSpan = document.getElementById('user-email');
        this.toast = document.getElementById('toast');

        // Conversation management
        this.conversationsList = document.getElementById('conversations-list');
        this.conversationSearch = document.getElementById('conversation-search');
        this.newConversationBtn = document.getElementById('new-conversation-btn');
        this.sidebarToggle = document.getElementById('sidebar-toggle');
        this.sidebar = document.getElementById('sidebar');

        this.isLoading = false;
        this.sessionId = null;
        this.userEmail = null;
        this.config = null; // Store instance configuration
        this.currentConversationId = null; // Currently active conversation
        this.conversations = []; // List of conversations
        this.searchTimeout = null; // For debouncing search

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

        // Load instance configuration
        await this.loadConfig();

        // Load KB stats
        await this.loadStats();

        // Load all conversations
        await this.loadConversations();

        // Load current session history (for in-memory messages)
        await this.loadHistory();

        // Load example questions
        await this.loadExampleQuestions();

        // Setup event listeners
        this.setupEventListeners();

        // Focus input
        this.queryInput.focus();
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();

            // Update page title and headers
            document.title = this.config.instance_name;
            document.getElementById('instance-name').textContent = this.config.instance_name;
            document.getElementById('instance-description').textContent = this.config.instance_description;

            // Update organization if available
            const orgElement = document.getElementById('instance-organization');
            if (this.config.organization && orgElement) {
                orgElement.textContent = this.config.organization;
                orgElement.style.display = 'block';
            }

            // Update welcome message if present
            const welcomeTitle = document.getElementById('welcome-title');
            const welcomeDescription = document.getElementById('welcome-description');
            if (welcomeTitle) {
                welcomeTitle.textContent = `Welcome to ${this.config.instance_name}`;
            }
            if (welcomeDescription && this.config.instance_description) {
                welcomeDescription.textContent = this.config.instance_description;
            }
        } catch (error) {
            console.error('Error loading config:', error);
        }
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

            // Show admin button if user is admin
            if (data.is_admin) {
                const adminBtn = document.getElementById('admin-btn');
                if (adminBtn) {
                    adminBtn.style.display = 'block';
                }
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

        // Logout button
        this.logoutBtn.addEventListener('click', () => this.logout());

        // Admin button
        const adminBtn = document.getElementById('admin-btn');
        if (adminBtn) {
            adminBtn.addEventListener('click', () => {
                window.location.href = '/admin';
            });
        }

        // Conversation management
        if (this.newConversationBtn) {
            this.newConversationBtn.addEventListener('click', () => this.startNewConversation());
        }

        if (this.conversationSearch) {
            this.conversationSearch.addEventListener('input', (e) => this.handleSearch(e.target.value));
        }

        if (this.sidebarToggle) {
            this.sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        }

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 768 && this.sidebar.classList.contains('open')) {
                if (!this.sidebar.contains(e.target) && !this.sidebarToggle.contains(e.target)) {
                    this.toggleSidebar();
                }
            }
        });
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
            // Prepare request payload with conversation_id if continuing a conversation
            const requestBody = { query };
            if (this.currentConversationId) {
                requestBody.conversation_id = this.currentConversationId;
            }

            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody),
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
                    data.timestamp,
                    data.message_id
                );
                this.sessionId = data.session_id;

                // Reload conversations to update the list (in case a new one was created)
                await this.loadConversations();
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

    displayMessage(role, content, sources = null, attachments = null, timestamp = null, messageId = null) {
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

        // Render markdown for assistant messages, plain text for user messages
        if (role === 'assistant' && typeof marked !== 'undefined') {
            // Configure marked for safe rendering
            marked.setOptions({
                breaks: true,  // Convert \n to <br>
                gfm: true,     // GitHub Flavored Markdown
                headerIds: false,
                mangle: false,
            });
            bubble.innerHTML = marked.parse(content);
        } else {
            bubble.textContent = content;
        }

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

        // Feedback buttons for assistant messages
        if (role === 'assistant' && messageId) {
            const feedbackDiv = this.createFeedbackSection(messageId);
            contentDiv.appendChild(feedbackDiv);
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
                // Calendar icon
                icon.innerHTML = '<i class="fas fa-calendar"></i>';
            } else if (attachment.filename.endsWith('.csv')) {
                // Chart/spreadsheet icon
                icon.innerHTML = '<i class="fas fa-chart-bar"></i>';
            } else if (attachment.filename.endsWith('.json')) {
                // Document icon
                icon.innerHTML = '<i class="fas fa-file-code"></i>';
            } else {
                // Paperclip icon
                icon.innerHTML = '<i class="fas fa-paperclip"></i>';
            }

            const filename = document.createElement('span');
            filename.textContent = attachment.filename;

            link.appendChild(icon);
            link.appendChild(filename);
            attachmentsDiv.appendChild(link);
        });

        return attachmentsDiv;
    }

    createFeedbackSection(messageId) {
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = 'message-feedback';
        feedbackDiv.setAttribute('data-message-id', messageId);

        const feedbackText = document.createElement('span');
        feedbackText.className = 'feedback-text';
        feedbackText.textContent = 'Was this helpful?';

        const thumbsUpBtn = document.createElement('button');
        thumbsUpBtn.className = 'feedback-btn feedback-thumbs-up';
        thumbsUpBtn.innerHTML = '👍';
        thumbsUpBtn.title = 'Yes, this was helpful';
        thumbsUpBtn.onclick = () => this.submitFeedback(messageId, true, feedbackDiv);

        const thumbsDownBtn = document.createElement('button');
        thumbsDownBtn.className = 'feedback-btn feedback-thumbs-down';
        thumbsDownBtn.innerHTML = '👎';
        thumbsDownBtn.title = 'No, this was not helpful';
        thumbsDownBtn.onclick = () => this.submitFeedback(messageId, false, feedbackDiv);

        feedbackDiv.appendChild(feedbackText);
        feedbackDiv.appendChild(thumbsUpBtn);
        feedbackDiv.appendChild(thumbsDownBtn);

        return feedbackDiv;
    }

    async submitFeedback(messageId, isPositive, feedbackDiv) {
        try {
            // Disable buttons immediately
            const buttons = feedbackDiv.querySelectorAll('.feedback-btn');
            buttons.forEach(btn => btn.disabled = true);

            // If negative feedback, show comment field
            let comment = null;
            if (!isPositive) {
                comment = prompt('Please tell us what went wrong (optional):');
                // If user cancelled, re-enable buttons
                if (comment === null) {
                    buttons.forEach(btn => btn.disabled = false);
                    return;
                }
            }

            // Submit feedback
            const response = await fetch('/api/feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify({
                    message_id: messageId,
                    is_positive: isPositive,
                    comment: comment,
                }),
            });

            const data = await response.json();

            if (data.success) {
                // Show thank you message
                feedbackDiv.innerHTML = '<span class="feedback-thanks">Thank you for your feedback!</span>';
            } else {
                alert('Failed to submit feedback. Please try again.');
                buttons.forEach(btn => btn.disabled = false);
            }
        } catch (error) {
            console.error('Error submitting feedback:', error);
            alert('Error submitting feedback. Please try again.');
            const buttons = feedbackDiv.querySelectorAll('.feedback-btn');
            buttons.forEach(btn => btn.disabled = false);
        }
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
                // Clear messages with dynamic instance name
                const instanceName = this.config ? this.config.instance_name : 'RAGInbox';
                const instanceDescription = this.config ? this.config.instance_description : 'Ask me anything about the knowledge base documents.';

                this.messagesContainer.innerHTML = `
                    <div class="welcome-message">
                        <div class="welcome-icon">
                            <i class="fas fa-comments"></i>
                        </div>
                        <h2 id="welcome-title">Welcome to ${instanceName}</h2>
                        <p id="welcome-description">${instanceDescription}</p>
                        <p class="welcome-hint">Your conversation history will be saved during this session.</p>

                        <!-- Example Questions -->
                        <div id="example-questions-container" style="display: none; margin-top: 2rem;">
                            <p style="font-size: 0.9rem; color: var(--text-secondary, #666); margin-bottom: 0.75rem;">
                                Try asking:
                            </p>
                            <div id="example-questions" class="example-questions">
                                <!-- Questions will be inserted here by JavaScript -->
                            </div>
                        </div>
                    </div>
                `;
                this.sessionId = null;
                this.showToast('Conversation cleared', 'success');

                // Display example questions again
                this.displayExampleQuestions();
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
            // Show typing indicator as a message
            this.showTypingIndicator();
        } else {
            // Remove typing indicator
            this.hideTypingIndicator();
        }
    }

    showTypingIndicator() {
        // Remove existing typing indicator if present
        this.hideTypingIndicator();

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant-message typing-indicator-message';
        messageDiv.id = 'typing-indicator';

        // Avatar
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.textContent = 'AI';

        // Content wrapper
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        // Typing indicator bubble
        const bubble = document.createElement('div');
        bubble.className = 'message-bubble typing-indicator';
        bubble.innerHTML = `
            <div class="typing-dots">
                <span class="dot"></span>
                <span class="dot"></span>
                <span class="dot"></span>
            </div>
        `;

        contentDiv.appendChild(bubble);
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(contentDiv);

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
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

    // ====================================
    // Conversation Management Methods
    // ====================================

    async loadConversations() {
        try {
            const response = await fetch('/api/conversations', {
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error('Failed to load conversations');
            }

            const data = await response.json();
            this.conversations = data.conversations;
            this.renderConversations(this.conversations);
        } catch (error) {
            console.error('Error loading conversations:', error);
            this.conversationsList.innerHTML = `
                <div class="empty-conversations">
                    <p>Failed to load conversations</p>
                </div>
            `;
        }
    }

    renderConversations(conversations) {
        if (conversations.length === 0) {
            this.conversationsList.innerHTML = `
                <div class="empty-conversations">
                    <p>No conversations yet</p>
                    <p style="font-size: 0.8rem; margin-top: 0.5rem;">Start a new conversation to get started!</p>
                </div>
            `;
            return;
        }

        this.conversationsList.innerHTML = conversations.map(conv => {
            const channelIcon = conv.channel === 'email'
                ? '<i class="fas fa-envelope"></i>'
                : '<i class="fas fa-comment"></i>';
            const isActive = this.currentConversationId === conv.id;
            const preview = conv.preview || 'No messages yet';
            const messageCount = conv.message_count || 0;

            return `
                <div class="conversation-item ${isActive ? 'active' : ''}" data-id="${conv.id}">
                    <div class="conversation-header">
                        <div style="display: flex; align-items: center; flex: 1;">
                            <span class="conversation-channel">${channelIcon}</span>
                            <div style="flex: 1; min-width: 0;">
                                <div class="conversation-title">${conv.subject || 'Conversation'}</div>
                            </div>
                        </div>
                        <span class="conversation-date">${this.formatRelativeTime(conv.last_message_at)}</span>
                    </div>
                    <div class="conversation-preview">${preview}</div>
                    <div class="conversation-meta">
                        <span class="conversation-count">
                            <i class="fas fa-comment"></i>
                            ${messageCount} message${messageCount !== 1 ? 's' : ''}
                        </span>
                    </div>
                    <div class="conversation-actions">
                        <button class="delete-conversation-btn" data-id="${conv.id}" title="Delete conversation">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        // Add click handlers for conversation items
        this.conversationsList.querySelectorAll('.conversation-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.delete-conversation-btn')) {
                    const conversationId = parseInt(item.dataset.id);
                    this.loadConversation(conversationId);
                }
            });
        });

        // Add click handlers for delete buttons
        this.conversationsList.querySelectorAll('.delete-conversation-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const conversationId = parseInt(btn.dataset.id);
                this.deleteConversation(conversationId);
            });
        });
    }

    async loadConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}`, {
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error('Failed to load conversation');
            }

            const data = await response.json();

            // Set current conversation
            this.currentConversationId = conversationId;

            // Clear messages and display conversation history
            this.messagesContainer.innerHTML = '';

            // Add all messages
            data.messages.forEach(msg => {
                this.displayMessage(
                    msg.role,
                    msg.content,
                    msg.sources,
                    msg.attachments,
                    msg.timestamp
                );
            });

            // Update UI
            this.updateActiveConversation();

            // Close sidebar on mobile
            if (window.innerWidth <= 768) {
                this.toggleSidebar();
            }

            this.showToast('Conversation loaded', 'success');
        } catch (error) {
            console.error('Error loading conversation:', error);
            this.showToast('Failed to load conversation', 'error');
        }
    }

    async deleteConversation(conversationId) {
        if (!confirm('Are you sure you want to delete this conversation? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/conversations/${conversationId}`, {
                method: 'DELETE',
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error('Failed to delete conversation');
            }

            // If deleted conversation was active, start new one
            if (this.currentConversationId === conversationId) {
                this.startNewConversation();
            }

            // Reload conversations list
            await this.loadConversations();

            this.showToast('Conversation deleted', 'success');
        } catch (error) {
            console.error('Error deleting conversation:', error);
            this.showToast('Failed to delete conversation', 'error');
        }
    }

    async handleSearch(query) {
        // Debounce search
        clearTimeout(this.searchTimeout);

        if (!query || query.trim().length < 2) {
            // Show all conversations if search is cleared
            this.renderConversations(this.conversations);
            return;
        }

        this.searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/conversations/search?q=${encodeURIComponent(query)}`, {
                    credentials: 'include',
                });

                if (!response.ok) {
                    throw new Error('Search failed');
                }

                const data = await response.json();
                this.renderConversations(data.results);
            } catch (error) {
                console.error('Error searching conversations:', error);
                this.showToast('Search failed', 'error');
            }
        }, 300);
    }

    startNewConversation() {
        // Clear current conversation
        this.currentConversationId = null;

        // Clear messages
        const welcomeMsg = this.messagesContainer.querySelector('.welcome-message');
        if (!welcomeMsg) {
            this.messagesContainer.innerHTML = `
                <div class="welcome-message">
                    <div class="welcome-icon">
                        <i class="fas fa-comments"></i>
                    </div>
                    <h2 id="welcome-title">Welcome to ${this.config?.instance_name || 'RAGInbox'}</h2>
                    <p id="welcome-description">${this.config?.instance_description || 'Ask me anything about the knowledge base documents.'}</p>
                    <p class="welcome-hint">Start a new conversation below.</p>

                    <!-- Example Questions -->
                    <div id="example-questions-container" style="display: none; margin-top: 2rem;">
                        <p style="font-size: 0.9rem; color: var(--text-secondary, #666); margin-bottom: 0.75rem;">
                            Try asking:
                        </p>
                        <div id="example-questions" class="example-questions">
                            <!-- Questions will be inserted here by JavaScript -->
                        </div>
                    </div>
                </div>
            `;

            // Display example questions
            this.displayExampleQuestions();
        }

        // Update UI
        this.updateActiveConversation();

        // Clear search
        if (this.conversationSearch) {
            this.conversationSearch.value = '';
        }

        // Show all conversations
        this.renderConversations(this.conversations);

        // Close sidebar on mobile
        if (window.innerWidth <= 768) {
            this.toggleSidebar();
        }

        // Focus input
        this.queryInput.focus();

        this.showToast('New conversation started', 'success');
    }

    updateActiveConversation() {
        // Update visual state of conversation items
        this.conversationsList.querySelectorAll('.conversation-item').forEach(item => {
            const itemId = parseInt(item.dataset.id);
            if (itemId === this.currentConversationId) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    toggleSidebar() {
        this.sidebar.classList.toggle('open');
        document.body.classList.toggle('sidebar-open');
    }

    formatRelativeTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        const diffDays = Math.floor(diffMs / 86400000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString([], {
            month: 'short',
            day: 'numeric'
        });
    }

    async loadExampleQuestions() {
        try {
            const response = await fetch('/api/example-questions');
            const data = await response.json();

            if (data.questions && data.questions.length > 0) {
                // Store all questions
                this.allExampleQuestions = data.questions;
                // Display random 3 questions
                this.displayExampleQuestions();
            }
        } catch (error) {
            console.error('Error loading example questions:', error);
            // Silently fail - example questions are optional
        }
    }

    displayExampleQuestions() {
        const container = document.getElementById('example-questions-container');
        const questionsDiv = document.getElementById('example-questions');

        if (!container || !questionsDiv || !this.allExampleQuestions || this.allExampleQuestions.length === 0) {
            return;
        }

        // Hide if conversation has started
        if (this.currentConversationId || (this.messagesContainer && this.messagesContainer.querySelectorAll('.message').length > 0)) {
            container.style.display = 'none';
            return;
        }

        // Select 3 random questions
        const selectedQuestions = this.getRandomQuestions(this.allExampleQuestions, 3);

        // Clear and populate
        questionsDiv.innerHTML = '';
        selectedQuestions.forEach(question => {
            const chip = document.createElement('button');
            chip.className = 'example-question-chip';
            chip.textContent = question;
            chip.onclick = () => this.selectExampleQuestion(question);
            questionsDiv.appendChild(chip);
        });

        // Show container
        container.style.display = 'block';
    }

    getRandomQuestions(questions, count) {
        // Shuffle array and take first 'count' items
        const shuffled = [...questions].sort(() => Math.random() - 0.5);
        return shuffled.slice(0, Math.min(count, shuffled.length));
    }

    selectExampleQuestion(question) {
        // Fill input with the question
        this.queryInput.value = question;

        // Hide example questions
        const container = document.getElementById('example-questions-container');
        if (container) {
            container.style.display = 'none';
        }

        // Send the query
        this.sendQuery();
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new ChatApp();
});
