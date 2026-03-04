/**
 * KB Health Analytics Manager
 */
class KBHealthAnalytics {
    constructor() {
        this.selectedDays = 7;
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Time range buttons
        document.querySelectorAll('.kbhealth-time-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.kbhealth-time-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                this.selectedDays = e.target.dataset.days === 'all' ? null : parseInt(e.target.dataset.days);
                this.loadHealth();
            });
        });

        // Load when KB Health tab is shown
        const kbHealthTab = document.querySelector('[data-tab="kbhealth"]');
        if (kbHealthTab) {
            kbHealthTab.addEventListener('click', () => {
                setTimeout(() => this.loadHealth(), 100);
            });
        }
    }

    async loadHealth() {
        try {
            const params = new URLSearchParams();
            if (this.selectedDays) {
                params.append('days', this.selectedDays);
            }

            const response = await fetch(`/api/admin/kb/health?${params}`, {
                credentials: 'include',
            });

            if (!response.ok) {
                throw new Error('Failed to load KB health metrics');
            }

            const data = await response.json();
            this.renderHealthScore(data.health_score);
            this.renderStructuralMetrics(data.structural);
            this.renderRetrievalMetrics(data.retrieval);
            this.renderUncitedDocuments(data.retrieval.uncited_documents || []);
        } catch (error) {
            console.error('Error loading KB health:', error);
            adminPanel.showToast('Failed to load KB health metrics', 'error');
        }
    }

    renderHealthScore(score) {
        const container = document.getElementById('kbhealth-score-content');
        if (!score) {
            container.innerHTML = '<p style="color: var(--text-secondary);">No data available</p>';
            return;
        }

        const total = score.total;
        const color = total >= 75 ? '#4CAF50' : total >= 50 ? '#FF9800' : '#F44336';
        const label = total >= 75 ? 'Good' : total >= 50 ? 'Fair' : 'Needs Attention';

        const factors = score.factors;
        const factorHtml = Object.entries(factors).map(([key, val]) => {
            const pct = (val.score / val.max * 100).toFixed(0);
            const name = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            return `
                <div style="margin-bottom: 0.5rem;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.875rem; margin-bottom: 0.25rem;">
                        <span>${this.escapeHtml(name)}</span>
                        <span style="font-weight: 600;">${val.score} / ${val.max}</span>
                    </div>
                    <div style="background: var(--border, #D5C9B8); border-radius: 4px; height: 8px; overflow: hidden;">
                        <div style="width: ${pct}%; height: 100%; background: ${color}; border-radius: 4px; transition: width 0.5s;"></div>
                    </div>
                </div>`;
        }).join('');

        container.innerHTML = `
            <div style="display: flex; align-items: center; gap: 2rem; margin-bottom: 1.5rem;">
                <div style="text-align: center; min-width: 120px;">
                    <div style="font-size: 3rem; font-weight: 700; color: ${color};">${total}</div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">${label}</div>
                </div>
                <div style="flex: 1;">
                    ${factorHtml}
                </div>
            </div>`;
    }

    renderStructuralMetrics(structural) {
        const container = document.getElementById('kbhealth-structural-content');
        if (!structural || structural.total_documents === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">Knowledge base is empty. Upload documents to see health metrics.</p>';
            return;
        }

        // Stat cards
        const statsHtml = `
            <div class="stats-grid" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-file-alt"></i></div>
                    <div class="stat-content">
                        <h3>Documents</h3>
                        <p class="stat-value">${structural.total_documents.toLocaleString()}</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-puzzle-piece"></i></div>
                    <div class="stat-content">
                        <h3>Chunks</h3>
                        <p class="stat-value">${structural.total_chunks.toLocaleString()}</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-layer-group"></i></div>
                    <div class="stat-content">
                        <h3>Avg Chunks/Doc</h3>
                        <p class="stat-value">${structural.avg_chunks_per_doc}</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-magic"></i></div>
                    <div class="stat-content">
                        <h3>Enhanced</h3>
                        <p class="stat-value">${structural.enhanced_percentage}%</p>
                    </div>
                </div>
            </div>`;

        // File type breakdown as horizontal bars
        const fileTypes = structural.file_type_breakdown || {};
        const maxCount = Math.max(...Object.values(fileTypes), 1);
        const typeBarHtml = Object.entries(fileTypes)
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => {
                const pct = (count / maxCount * 100).toFixed(0);
                return `
                    <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;">
                        <span style="min-width: 60px; font-size: 0.875rem; text-align: right; color: var(--text-secondary);">${this.escapeHtml(type)}</span>
                        <div style="flex: 1; background: var(--border, #D5C9B8); border-radius: 4px; height: 20px; overflow: hidden;">
                            <div style="width: ${pct}%; height: 100%; background: var(--primary, #7A5C3E); border-radius: 4px; transition: width 0.5s;"></div>
                        </div>
                        <span style="min-width: 30px; font-size: 0.875rem; font-weight: 600;">${count}</span>
                    </div>`;
            }).join('');

        // Freshness info
        const staleInfo = structural.stale_count > 0
            ? `<span style="color: #F44336; font-weight: 600;">${structural.stale_count} stale</span> (>${structural.stale_threshold_days} days)`
            : '<span style="color: #4CAF50;">All documents are fresh</span>';

        const freshnessHtml = `
            <div style="margin-top: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--text-primary);">Freshness</h4>
                <div style="display: flex; gap: 2rem; flex-wrap: wrap; font-size: 0.875rem; color: var(--text-secondary);">
                    <div>Avg Age: <strong>${structural.avg_age_days} days</strong></div>
                    <div>Status: ${staleInfo}</div>
                </div>
            </div>`;

        // Chunk distribution
        const dist = structural.chunk_distribution || {};
        const distHtml = `
            <div style="margin-top: 1.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--text-primary);">Chunk Distribution</h4>
                <div style="display: flex; gap: 2rem; flex-wrap: wrap; font-size: 0.875rem; color: var(--text-secondary);">
                    <div>Min: <strong>${dist.min}</strong></div>
                    <div>Max: <strong>${dist.max}</strong></div>
                    <div>Avg: <strong>${dist.avg}</strong></div>
                    <div>Median: <strong>${dist.median}</strong></div>
                </div>
            </div>`;

        container.innerHTML = statsHtml + `
            <div style="margin-top: 0.5rem;">
                <h4 style="margin-bottom: 0.75rem; color: var(--text-primary);">File Types</h4>
                ${typeBarHtml || '<p style="color: var(--text-secondary);">No file type data</p>'}
            </div>` + freshnessHtml + distHtml;
    }

    renderRetrievalMetrics(retrieval) {
        const container = document.getElementById('kbhealth-retrieval-content');
        if (!retrieval || retrieval.total_replies_analyzed === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 2rem;">No retrieval data available for this time period.</p>';
            return;
        }

        const coverageColor = retrieval.citation_coverage_pct >= 60 ? '#4CAF50' : retrieval.citation_coverage_pct >= 30 ? '#FF9800' : '#F44336';
        const lowRelColor = retrieval.low_relevance_rate <= 20 ? '#4CAF50' : retrieval.low_relevance_rate <= 50 ? '#FF9800' : '#F44336';

        container.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-reply"></i></div>
                    <div class="stat-content">
                        <h3>Replies Analyzed</h3>
                        <p class="stat-value">${retrieval.total_replies_analyzed.toLocaleString()}</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-bullseye"></i></div>
                    <div class="stat-content">
                        <h3>Citation Coverage</h3>
                        <p class="stat-value" style="color: ${coverageColor};">${retrieval.citation_coverage_pct}%</p>
                        <p style="font-size: 0.75rem; color: var(--text-secondary);">${retrieval.cited_document_count} of ${retrieval.total_kb_documents} docs cited</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-exclamation-triangle"></i></div>
                    <div class="stat-content">
                        <h3>Low Relevance Rate</h3>
                        <p class="stat-value" style="color: ${lowRelColor};">${retrieval.low_relevance_rate}%</p>
                        <p style="font-size: 0.75rem; color: var(--text-secondary);">${retrieval.low_relevance_count} of ${retrieval.total_replies_analyzed} replies</p>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-file-excel"></i></div>
                    <div class="stat-content">
                        <h3>Uncited Documents</h3>
                        <p class="stat-value">${retrieval.uncited_count}</p>
                    </div>
                </div>
            </div>`;
    }

    renderUncitedDocuments(uncited) {
        const container = document.getElementById('kbhealth-uncited-content');

        if (!uncited || uncited.length === 0) {
            container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 1rem;">All documents have been cited at least once.</p>';
            return;
        }

        const maxShow = 20;
        const shown = uncited.slice(0, maxShow);
        const remaining = uncited.length - maxShow;

        const rows = shown.map(filename => `
            <tr>
                <td style="padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border, #D5C9B8); font-size: 0.875rem;">
                    <i class="fas fa-file" style="color: var(--text-secondary); margin-right: 0.5rem;"></i>
                    ${this.escapeHtml(filename)}
                </td>
            </tr>
        `).join('');

        const moreHtml = remaining > 0
            ? `<p style="text-align: center; color: var(--text-secondary); font-size: 0.875rem; padding: 0.5rem;">...and ${remaining} more</p>`
            : '';

        container.innerHTML = `
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr>
                        <th style="text-align: left; padding: 0.5rem 0.75rem; border-bottom: 2px solid var(--border, #D5C9B8); color: var(--text-secondary); font-size: 0.875rem;">Filename</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
            ${moreHtml}`;
    }

    refresh() {
        this.loadHealth();
        adminPanel.showToast('KB health metrics refreshed', 'success');
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
