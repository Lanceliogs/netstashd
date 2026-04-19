/**
 * Preview panel controller
 */
class PreviewPanel {
    constructor(stashId, currentPath) {
        this.stashId = stashId;
        this.currentPath = currentPath;
        this.selectedFile = null;
        this.isOpen = false;
        
        this.panel = document.getElementById('preview-panel');
        this.content = document.getElementById('preview-content');
        this.placeholder = document.getElementById('preview-placeholder');
    }

    /**
     * Select a file and show preview
     */
    select(filename, isDir) {
        // Update selection UI
        document.querySelectorAll('.file-row').forEach(row => {
            row.classList.remove('selected');
        });
        
        const row = document.querySelector(`.file-row[data-name="${CSS.escape(filename)}"]`);
        if (row) {
            row.classList.add('selected');
        }

        this.selectedFile = { name: filename, isDir };
        
        if (isDir) {
            this.showFolderInfo(filename);
        } else {
            this.showFilePreview(filename);
        }
        
        this.open();
    }

    /**
     * Open the preview panel
     */
    open() {
        this.isOpen = true;
        this.panel.classList.add('open');
        document.body.classList.add('preview-open');
    }

    /**
     * Close the preview panel
     */
    close() {
        this.isOpen = false;
        this.panel.classList.remove('open');
        document.body.classList.remove('preview-open');
    }

    /**
     * Toggle panel open/closed
     */
    toggle() {
        if (this.isOpen) {
            this.close();
        } else if (this.selectedFile) {
            this.open();
        }
    }

    /**
     * Clear selection
     */
    clearSelection() {
        document.querySelectorAll('.file-row').forEach(row => {
            row.classList.remove('selected');
        });
        this.selectedFile = null;
        this.showPlaceholder();
        this.close();
    }

    /**
     * Show placeholder when nothing selected
     */
    showPlaceholder() {
        this.content.innerHTML = '';
        this.placeholder.style.display = 'flex';
    }

    /**
     * Fetch file metadata from API
     */
    async fetchMetadata(filename) {
        try {
            const response = await fetch(`/s/${this.stashId}/meta/${this.getFullPath(filename)}`);
            if (!response.ok) return null;
            return await response.json();
        } catch {
            return null;
        }
    }

    /**
     * Format file size for display
     */
    formatSize(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
    }

    /**
     * Format date for display
     */
    formatDate(isoString) {
        const date = new Date(isoString);
        return date.toLocaleDateString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    /**
     * Render metadata HTML
     */
    renderMetadata(meta) {
        if (!meta) return '';
        return `
            <div class="preview-metadata">
                <div class="meta-row">
                    <span class="meta-label">Size</span>
                    <span class="meta-value">${this.formatSize(meta.size)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">Modified</span>
                    <span class="meta-value">${this.formatDate(meta.modified_at)}</span>
                </div>
                <div class="meta-row">
                    <span class="meta-label">Created</span>
                    <span class="meta-value">${this.formatDate(meta.created_at)}</span>
                </div>
            </div>
        `;
    }

    /**
     * Show folder info
     */
    async showFolderInfo(name) {
        this.placeholder.style.display = 'none';
        this.content.innerHTML = `
            <div class="preview-info">
                <div class="preview-icon">📁</div>
                <div class="preview-filename">${this.escapeHtml(name)}</div>
                <div class="preview-meta">Folder</div>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="/s/${this.stashId}/fs/${this.getFullPath(name)}" class="btn btn-primary">Open</a>
                    <a href="/s/${this.stashId}/download/${this.getFullPath(name)}" class="btn btn-secondary">Download ZIP</a>
                </div>
            </div>
        `;
        
        const meta = await this.fetchMetadata(name);
        const metaContainer = document.getElementById('preview-meta');
        if (metaContainer) {
            metaContainer.outerHTML = this.renderMetadata(meta);
        }
    }

    /**
     * Show file preview based on type
     */
    async showFilePreview(filename) {
        this.placeholder.style.display = 'none';
        
        const category = FileIcons.getCategory(filename);
        const downloadUrl = `/s/${this.stashId}/download/${this.getFullPath(filename)}`;
        const icon = FileIcons.getIcon(filename);
        
        let previewHtml = '';
        
        switch (category) {
            case 'image':
                previewHtml = this.renderImagePreview(filename, downloadUrl);
                break;
            case 'video':
                previewHtml = this.renderVideoPreview(filename, downloadUrl);
                break;
            case 'audio':
                previewHtml = this.renderAudioPreview(filename, downloadUrl, icon);
                break;
            case 'text':
            case 'code':
                previewHtml = this.renderTextPreview(filename, downloadUrl, icon);
                break;
            case 'pdf':
                previewHtml = this.renderPdfPreview(filename, downloadUrl);
                break;
            default:
                previewHtml = this.renderGenericPreview(filename, downloadUrl, icon);
        }
        
        this.content.innerHTML = previewHtml;
        
        // Load text content if needed
        if (category === 'text' || category === 'code') {
            this.loadTextContent(filename, downloadUrl);
        }
        
        // Load metadata
        const meta = await this.fetchMetadata(filename);
        const metaContainer = document.getElementById('preview-meta');
        if (metaContainer) {
            metaContainer.outerHTML = this.renderMetadata(meta);
        }
    }

    /**
     * Render image preview
     */
    renderImagePreview(filename, url) {
        return `
            <div class="preview-media">
                <img src="${url}" alt="${this.escapeHtml(filename)}" loading="lazy">
            </div>
            <div class="preview-details">
                <div class="preview-filename">${this.escapeHtml(filename)}</div>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                </div>
            </div>
        `;
    }

    /**
     * Render video preview
     */
    renderVideoPreview(filename, url) {
        const mimeType = FileIcons.getMimeType(filename);
        return `
            <div class="preview-media">
                <video controls preload="metadata">
                    <source src="${url}" type="${mimeType}">
                    Your browser doesn't support video playback.
                </video>
            </div>
            <div class="preview-details">
                <div class="preview-filename">${this.escapeHtml(filename)}</div>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                </div>
            </div>
        `;
    }

    /**
     * Render audio preview
     */
    renderAudioPreview(filename, url, icon) {
        const mimeType = FileIcons.getMimeType(filename);
        return `
            <div class="preview-info">
                <div class="preview-icon">${icon}</div>
                <div class="preview-filename">${this.escapeHtml(filename)}</div>
                <audio controls preload="metadata" class="preview-audio">
                    <source src="${url}" type="${mimeType}">
                    Your browser doesn't support audio playback.
                </audio>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                </div>
            </div>
        `;
    }

    /**
     * Render text/code preview
     */
    renderTextPreview(filename, url, icon) {
        return `
            <div class="preview-text">
                <div class="preview-text-header">
                    <span class="preview-filename">${this.escapeHtml(filename)}</span>
                </div>
                <pre class="preview-code" id="preview-code-content"><code>Loading...</code></pre>
            </div>
            <div class="preview-details">
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                </div>
            </div>
        `;
    }

    /**
     * Render PDF preview
     */
    renderPdfPreview(filename, url) {
        return `
            <div class="preview-media preview-pdf">
                <iframe src="${url}" title="${this.escapeHtml(filename)}"></iframe>
            </div>
            <div class="preview-details">
                <div class="preview-filename">${this.escapeHtml(filename)}</div>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                    <a href="${url}" class="btn btn-secondary" target="_blank">Open in new tab</a>
                </div>
            </div>
        `;
    }

    /**
     * Render generic file preview (no preview available)
     */
    renderGenericPreview(filename, url, icon) {
        const ext = FileIcons.getExtension(filename).toUpperCase() || 'FILE';
        return `
            <div class="preview-info">
                <div class="preview-icon">${icon}</div>
                <div class="preview-filename">${this.escapeHtml(filename)}</div>
                <div class="preview-meta">${ext} file</div>
                <div class="preview-metadata-container" id="preview-meta">Loading...</div>
                <div class="preview-actions">
                    <a href="${url}" class="btn btn-primary" download>Download</a>
                </div>
            </div>
        `;
    }

    /**
     * Load text file content for preview
     */
    async loadTextContent(filename, url) {
        const codeElement = document.getElementById('preview-code-content');
        if (!codeElement) return;
        
        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to load');
            
            let text = await response.text();
            
            // Limit preview size
            const maxLength = 50000;
            if (text.length > maxLength) {
                text = text.substring(0, maxLength) + '\n\n... (truncated)';
            }
            
            codeElement.querySelector('code').textContent = text;
        } catch (error) {
            codeElement.querySelector('code').textContent = 'Unable to load preview';
        }
    }

    /**
     * Get full path for a file
     */
    getFullPath(filename) {
        return this.currentPath ? `${this.currentPath}/${filename}` : filename;
    }

    /**
     * Escape HTML entities
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
