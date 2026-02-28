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

            // Load additional analytics
            this.loadOptimizationAnalytics();
            this.loadSourceAnalytics();

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
                            <div class="query-item" style="margin-bottom: 1rem; padding: 1rem; background: var(--bg-secondary, #F7F2EA); border-radius: 6px;">
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
                <a href="#" onclick="document.getElementById('${id}-short').style.display='none'; document.getElementById('${id}-full').style.display='block'; return false;" style="color: var(--primary, #7A5C3E);">
                    [Show More]
                </a>
            </span>
            <span id="${id}-full" style="display: none;">${this.escapeHtml(text)}
                <a href="#" onclick="document.getElementById('${id}-full').style.display='none'; document.getElementById('${id}-short').style.display='block'; return false;" style="color: var(--primary, #7A5C3E);">
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

    async loadOptimizationAnalytics() {
        try {
            const params = this.currentTimeRange ? `?days=${this.currentTimeRange}` : '';
            const response = await fetch(`/api/admin/analytics/optimization${params}`);

            if (!response.ok) {
                throw new Error('Failed to load optimization analytics');
            }

            const data = await response.json();
            this.renderOptimizationAnalytics(data);
        } catch (error) {
            console.error('Error loading optimization analytics:', error);
            const container = document.getElementById('optimization-container');
            if (container) {
                container.innerHTML = '<p style="color: var(--text-secondary, #666);">Error loading optimization analytics</p>';
            }
        }
    }

    renderOptimizationAnalytics(data) {
        const container = document.getElementById('optimization-container');
        if (!container) return;

        if (data.total_queries === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary, #666);">No queries in this period</p>';
            return;
        }

        const optimizationRate = data.optimization_rate.toFixed(1);
        const avgExpansion = data.avg_query_expansion.toFixed(1);

        container.innerHTML = `
            <div class="stats-grid" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-magic"></i></div>
                    <div class="stat-content">
                        <div class="stat-label">Optimization Rate</div>
                        <div class="stat-value">${optimizationRate}%</div>
                        <div class="stat-sub">${data.optimized_count} of ${data.total_queries} queries</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-expand-arrows-alt"></i></div>
                    <div class="stat-content">
                        <div class="stat-label">Avg Query Expansion</div>
                        <div class="stat-value">${avgExpansion}%</div>
                        <div class="stat-sub">Average length increase</div>
                    </div>
                </div>
            </div>
            ${data.sample_optimizations.length > 0 ? `
                <div class="optimization-samples">
                    <h4 style="margin-bottom: 1rem;">Sample Optimizations</h4>
                    ${data.sample_optimizations.map((sample, i) => `
                        <div class="optimization-sample" style="margin-bottom: 1rem; padding: 1rem; background: var(--bg-secondary, #F7F2EA); border-radius: 6px;">
                            <div style="margin-bottom: 0.5rem;">
                                <strong>Original:</strong> <span style="color: var(--text-secondary, #666);">${this.escapeHtml(sample.original_query)}</span>
                            </div>
                            <div>
                                <strong>Optimized:</strong> <span style="color: var(--success, #5B8C7A);">${this.escapeHtml(sample.optimized_query)}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        `;
    }

    async loadSourceAnalytics() {
        try {
            const params = this.currentTimeRange ? `?days=${this.currentTimeRange}` : '';
            const response = await fetch(`/api/admin/analytics/sources${params}`);

            if (!response.ok) {
                throw new Error('Failed to load source analytics');
            }

            const data = await response.json();
            this.renderSourceAnalytics(data);
        } catch (error) {
            console.error('Error loading source analytics:', error);
            const container = document.getElementById('sources-container');
            if (container) {
                container.innerHTML = '<p style="color: var(--text-secondary, #666);">Error loading source analytics</p>';
            }
        }
    }

    renderSourceAnalytics(data) {
        const container = document.getElementById('sources-container');
        if (!container) return;

        if (data.total_replies === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary, #666);">No replies with sources in this period</p>';
            return;
        }

        const avgSources = data.avg_sources_per_reply.toFixed(1);
        const avgScore = data.avg_relevance_score ? (data.avg_relevance_score * 100).toFixed(1) : 'N/A';

        container.innerHTML = `
            <div class="stats-grid" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-file-alt"></i></div>
                    <div class="stat-content">
                        <div class="stat-label">Total Replies</div>
                        <div class="stat-value">${data.total_replies}</div>
                        <div class="stat-sub">${data.replies_with_sources} with sources</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-layer-group"></i></div>
                    <div class="stat-content">
                        <div class="stat-label">Avg Sources/Reply</div>
                        <div class="stat-value">${avgSources}</div>
                        <div class="stat-sub">Documents cited</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-star"></i></div>
                    <div class="stat-content">
                        <div class="stat-label">Avg Relevance</div>
                        <div class="stat-value">${avgScore}${avgScore !== 'N/A' ? '%' : ''}</div>
                        <div class="stat-sub">Source quality</div>
                    </div>
                </div>
            </div>
            ${data.top_sources.length > 0 ? `
                <div class="top-sources">
                    <h4 style="margin-bottom: 1rem;">Most Cited Documents</h4>
                    <div class="table-responsive">
                        <table class="users-table">
                            <thead>
                                <tr>
                                    <th>Document</th>
                                    <th>Citations</th>
                                    <th>Avg Score</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.top_sources.slice(0, 10).map(source => `
                                    <tr>
                                        <td>${this.escapeHtml(source.filename)}</td>
                                        <td>${source.citation_count}</td>
                                        <td>${(source.avg_score * 100).toFixed(1)}%</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            ` : ''}
        `;
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
