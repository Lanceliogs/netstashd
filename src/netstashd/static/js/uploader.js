/**
 * Represents a single file upload in progress
 */
function createUploadEntry(xhr, file, name) {
    return {
        xhr,
        file,
        name,
        loaded: 0,
        sizeAdjusted: false,
    };
}

/**
 * Multi-file uploader with global progress tracking
 */
class Uploader {
    constructor(stashId, currentPath = '') {
        this.stashId = stashId;
        this.currentPath = currentPath;
        
        // Global tracking
        this.totalFiles = 0;
        this.completedFiles = 0;
        this.totalBytes = 0;
        this.uploadedBytes = 0;
        this.errors = []; // [{name, error}]
        this.activeUploads = new Map();
        this.uploadCounter = 0;
        this.isUploading = false;
        
        // Directory tracking for empty folder structures
        this.pendingDirs = new Set();
        this.dirsWithFiles = new Set();
        this.emptyDirs = new Set();
        this.totalDirs = 0;
        this.createdDirs = 0;
        
        // Speed tracking
        this.startTime = 0;
        this.lastTime = 0;
        this.lastBytes = 0;
        this.currentSpeed = 0;
        
        // Bind the beforeunload handler so we can add/remove it
        this._beforeUnloadHandler = this._handleBeforeUnload.bind(this);
    }

    /**
     * Warn user before leaving page during upload
     */
    _handleBeforeUnload(e) {
        if (this.isUploading) {
            e.preventDefault();
            // Modern browsers ignore custom messages, but we still need to set returnValue
            e.returnValue = 'Upload in progress. Are you sure you want to leave?';
            return e.returnValue;
        }
    }

    /**
     * Upload multiple files
     */
    uploadFiles(files) {
        if (files.length === 0) return;
        
        this.startUpload();
        
        for (const file of files) {
            const relativePath = file.webkitRelativePath || '';
            this.queueFile(file, relativePath);
        }
    }

    /**
     * Handle dropped items (files or folders)
     */
    async uploadDroppedItems(items) {
        const entries = [];
        for (const item of items) {
            if (item.kind === 'file') {
                const entry = item.webkitGetAsEntry();
                if (entry) {
                    entries.push(entry);
                }
            }
        }
        
        if (entries.length === 0) return;
        
        this.startUpload();
        this.pendingDirs.clear();
        this.dirsWithFiles = new Set();
        
        for (const entry of entries) {
            await this.processEntry(entry, '');
        }
        
        // Find directories that won't be created by file uploads
        // (directories that don't contain any files, directly or indirectly)
        this.emptyDirs = new Set();
        for (const dir of this.pendingDirs) {
            const hasFiles = Array.from(this.dirsWithFiles).some(
                fileDir => fileDir === dir || fileDir.startsWith(dir + '/')
            );
            if (!hasFiles) {
                this.emptyDirs.add(dir);
            }
        }
        
        // Create empty directories if any exist
        if (this.emptyDirs.size > 0) {
            await this.createEmptyDirectories();
        }
    }

    /**
     * Initialize upload UI
     */
    startUpload() {
        if (!this.isUploading) {
            this.isUploading = true;
            this.totalFiles = 0;
            this.completedFiles = 0;
            this.totalBytes = 0;
            this.uploadedBytes = 0;
            this.errors = [];
            this.activeUploads.clear();
            
            // Reset directory tracking
            this.pendingDirs.clear();
            this.dirsWithFiles = new Set();
            this.emptyDirs = new Set();
            this.totalDirs = 0;
            this.createdDirs = 0;
            
            // Reset speed tracking
            this.startTime = Date.now();
            this.lastTime = this.startTime;
            this.lastBytes = 0;
            this.currentSpeed = 0;
            
            // Prevent accidental navigation during upload
            window.addEventListener('beforeunload', this._beforeUnloadHandler);
        }
        
        this.showProgress();
    }

    /**
     * Recursively process a file system entry
     */
    async processEntry(entry, path) {
        if (entry.isFile) {
            const file = await this.getFile(entry);
            const relativePath = path ? `${path}/${entry.name}` : '';
            // Track which directory this file is in
            if (path) {
                const fileDir = this.currentPath ? `${this.currentPath}/${path}` : path;
                this.dirsWithFiles.add(fileDir);
            }
            this.queueFile(file, relativePath);
        } else if (entry.isDirectory) {
            const dirPath = path ? `${path}/${entry.name}` : entry.name;
            const fullPath = this.currentPath ? `${this.currentPath}/${dirPath}` : dirPath;
            this.pendingDirs.add(fullPath);
            
            const entries = await this.readDirectory(entry);
            for (const childEntry of entries) {
                await this.processEntry(childEntry, dirPath);
            }
        }
    }

    /**
     * Get File from FileSystemFileEntry
     */
    getFile(entry) {
        return new Promise((resolve, reject) => {
            entry.file(resolve, reject);
        });
    }

    /**
     * Read directory contents
     */
    readDirectory(dirEntry) {
        return new Promise((resolve, reject) => {
            const reader = dirEntry.createReader();
            const entries = [];
            
            const readBatch = () => {
                reader.readEntries((batch) => {
                    if (batch.length === 0) {
                        resolve(entries);
                    } else {
                        entries.push(...batch);
                        readBatch();
                    }
                }, reject);
            };
            
            readBatch();
        });
    }

    /**
     * Create empty directories (ones that won't be created by file uploads)
     */
    async createEmptyDirectories() {
        const dirs = Array.from(this.emptyDirs).sort();
        this.totalDirs = dirs.length;
        this.createdDirs = 0;
        
        // If we also have files uploading, don't show separate UI - just create dirs quietly
        if (this.totalFiles > 0) {
            for (const dir of dirs) {
                try {
                    await fetch(
                        `/api/stashes/${this.stashId}/mkdir?path=${encodeURIComponent(dir)}`,
                        { method: 'POST' }
                    );
                } catch (e) {
                    // Silently ignore - empty dir creation is best-effort when files exist
                }
            }
            return;
        }
        
        // No files - show directory creation progress
        this.showDirectoryProgress();
        
        for (const dir of dirs) {
            try {
                const response = await fetch(
                    `/api/stashes/${this.stashId}/mkdir?path=${encodeURIComponent(dir)}`,
                    { method: 'POST' }
                );
                
                if (!response.ok) {
                    const data = await response.json().catch(() => ({}));
                    this.errors.push({ name: dir, error: data.detail || 'Failed to create directory' });
                }
            } catch (e) {
                this.errors.push({ name: dir, error: 'Network error' });
            }
            
            this.createdDirs++;
            this.updateDirectoryProgress();
        }
        
        this.showDirectoryComplete();
    }

    /**
     * Show directory creation progress UI
     */
    showDirectoryProgress() {
        const container = document.getElementById('upload-progress');
        container.style.display = 'block';
        container.innerHTML = `
            <div class="upload-header">
                <div class="upload-status">
                    <span class="upload-status-text">Creating folders...</span>
                </div>
                <button class="btn btn-small btn-secondary upload-cancel" onclick="uploader.cancelDirs()">Cancel</button>
            </div>
            <div class="upload-progress-bar">
                <div class="upload-progress-fill" style="width: 0%"></div>
            </div>
            <div class="upload-stats">
                <span class="upload-percent">0%</span>
                <span class="upload-details">
                    <span class="upload-dir-count">0 of ${this.totalDirs} folders</span>
                </span>
            </div>
            <div class="upload-errors" style="display: none;">
                <button class="upload-errors-toggle" onclick="uploader.toggleErrors()">
                    <span class="upload-errors-icon">⚠</span>
                    <span class="upload-errors-count"></span>
                </button>
                <div class="upload-errors-list" style="display: none;"></div>
            </div>
        `;
    }

    /**
     * Update directory creation progress
     */
    updateDirectoryProgress() {
        const percent = Math.round((this.createdDirs / this.totalDirs) * 100);
        
        const statusText = document.querySelector('.upload-status-text');
        const progressFill = document.querySelector('.upload-progress-fill');
        const percentText = document.querySelector('.upload-percent');
        const dirCount = document.querySelector('.upload-dir-count');
        
        if (statusText) {
            statusText.textContent = `Creating folders...`;
        }
        if (progressFill) {
            progressFill.style.width = `${percent}%`;
        }
        if (percentText) {
            percentText.textContent = `${percent}%`;
        }
        if (dirCount) {
            dirCount.textContent = `${this.createdDirs} of ${this.totalDirs} folders`;
        }
    }

    /**
     * Show directory creation complete
     */
    showDirectoryComplete() {
        this.isUploading = false;
        window.removeEventListener('beforeunload', this._beforeUnloadHandler);
        
        const statusText = document.querySelector('.upload-status-text');
        const progressFill = document.querySelector('.upload-progress-fill');
        const percentText = document.querySelector('.upload-percent');
        const cancelBtn = document.querySelector('.upload-cancel');
        
        if (cancelBtn) {
            cancelBtn.style.display = 'none';
        }
        
        const successCount = this.totalDirs - this.errors.length;
        
        if (progressFill) {
            progressFill.style.width = '100%';
            progressFill.classList.add(this.errors.length > 0 ? 'has-errors' : 'complete');
        }
        
        if (statusText) {
            if (this.errors.length === 0) {
                statusText.innerHTML = `<span class="upload-success">✓</span> ${successCount} folder${successCount !== 1 ? 's' : ''} created`;
            } else {
                statusText.innerHTML = `<span class="upload-success">✓</span> ${successCount} created`;
            }
        }
        
        if (percentText) {
            percentText.textContent = 'Done';
        }
        
        if (this.errors.length > 0) {
            const errorsSection = document.querySelector('.upload-errors');
            const errorsCount = document.querySelector('.upload-errors-count');
            const errorsList = document.querySelector('.upload-errors-list');
            
            if (errorsSection) {
                errorsSection.style.display = 'block';
            }
            if (errorsCount) {
                errorsCount.textContent = `${this.errors.length} failed`;
            }
            if (errorsList) {
                errorsList.innerHTML = this.errors.map(e => 
                    `<div class="upload-error-item">
                        <span class="upload-error-name">${this.escapeHtml(e.name)}</span>
                        <span class="upload-error-msg">${this.escapeHtml(e.error)}</span>
                    </div>`
                ).join('');
            }
        } else {
            setTimeout(() => window.location.reload(), 800);
        }
    }

    /**
     * Cancel directory creation
     */
    cancelDirs() {
        this.pendingDirs.clear();
        this.emptyDirs.clear();
        this.isUploading = false;
        window.removeEventListener('beforeunload', this._beforeUnloadHandler);
        
        const container = document.getElementById('upload-progress');
        container.style.display = 'none';
        
        if (this.createdDirs > 0) {
            window.location.reload();
        }
    }

    /**
     * Queue and upload a single file
     */
    queueFile(file, relativePath = '') {
        const uploadId = ++this.uploadCounter;
        const displayName = relativePath || file.name;
        
        this.totalFiles++;
        this.totalBytes += file.size;
        this.updateProgress();

        const xhr = new XMLHttpRequest();
        const formData = new FormData();
        formData.append('file', file);

        this.activeUploads.set(uploadId, createUploadEntry(xhr, file, displayName));

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const upload = this.activeUploads.get(uploadId);
                if (upload) {
                    // Adjust totalBytes on first progress event to account for multipart overhead
                    if (!upload.sizeAdjusted && e.total > 0) {
                        this.totalBytes += e.total - upload.file.size;
                        upload.sizeAdjusted = true;
                    }
                    
                    const delta = e.loaded - upload.loaded;
                    this.uploadedBytes += delta;
                    upload.loaded = e.loaded;
                    this.updateProgress();
                }
            }
        });

        xhr.addEventListener('load', () => {
            const upload = this.activeUploads.get(uploadId);
            this.activeUploads.delete(uploadId);
            
            if (xhr.status >= 200 && xhr.status < 300) {
                this.completedFiles++;
            } else {
                let errorMsg = 'Upload failed';
                try {
                    const response = JSON.parse(xhr.responseText);
                    errorMsg = response.detail || errorMsg;
                } catch (e) {}
                this.errors.push({ name: upload?.name || 'Unknown file', error: errorMsg });
                this.completedFiles++;
            }
            
            this.updateProgress();
            this.checkAllComplete();
        });

        xhr.addEventListener('error', () => {
            const upload = this.activeUploads.get(uploadId);
            this.activeUploads.delete(uploadId);
            this.errors.push({ name: upload?.name || 'Unknown file', error: 'Network error' });
            this.completedFiles++;
            this.updateProgress();
            this.checkAllComplete();
        });

        xhr.addEventListener('abort', () => {
            this.activeUploads.delete(uploadId);
            this.completedFiles++;
            this.updateProgress();
            this.checkAllComplete();
        });

        // Build upload path
        let uploadPath = this.currentPath;
        if (relativePath) {
            const relativeDir = relativePath.substring(0, relativePath.lastIndexOf('/'));
            if (relativeDir) {
                uploadPath = uploadPath ? `${uploadPath}/${relativeDir}` : relativeDir;
            }
        }
        
        const url = uploadPath 
            ? `/api/stashes/${this.stashId}/upload?path=${encodeURIComponent(uploadPath)}`
            : `/api/stashes/${this.stashId}/upload`;
        
        xhr.open('POST', url);
        xhr.send(formData);
    }

    /**
     * Show progress UI
     */
    showProgress() {
        const container = document.getElementById('upload-progress');
        container.style.display = 'block';
        container.innerHTML = `
            <div class="upload-header">
                <div class="upload-status">
                    <span class="upload-status-text">Preparing upload...</span>
                </div>
                <button class="btn btn-small btn-secondary upload-cancel" onclick="uploader.cancel()">Cancel</button>
            </div>
            <div class="upload-progress-bar">
                <div class="upload-progress-fill" style="width: 0%"></div>
            </div>
            <div class="upload-stats">
                <span class="upload-percent">0%</span>
                <span class="upload-details">
                    <span class="upload-speed"></span>
                    <span class="upload-eta"></span>
                    <span class="upload-size"></span>
                </span>
            </div>
            <div class="upload-errors" style="display: none;">
                <button class="upload-errors-toggle" onclick="uploader.toggleErrors()">
                    <span class="upload-errors-icon">⚠</span>
                    <span class="upload-errors-count"></span>
                </button>
                <div class="upload-errors-list" style="display: none;"></div>
            </div>
        `;
    }

    /**
     * Update progress UI
     */
    updateProgress() {
        const percent = this.totalBytes > 0 
            ? Math.min(100, Math.round((this.uploadedBytes / this.totalBytes) * 100))
            : 0;
        
        // Calculate speed (using rolling average)
        const now = Date.now();
        const timeDelta = (now - this.lastTime) / 1000; // seconds
        
        if (timeDelta >= 0.5) { // Update speed every 500ms
            const bytesDelta = this.uploadedBytes - this.lastBytes;
            const instantSpeed = bytesDelta / timeDelta;
            
            // Smooth the speed with exponential moving average
            if (this.currentSpeed === 0) {
                this.currentSpeed = instantSpeed;
            } else {
                this.currentSpeed = this.currentSpeed * 0.7 + instantSpeed * 0.3;
            }
            
            this.lastTime = now;
            this.lastBytes = this.uploadedBytes;
        }
        
        const statusText = document.querySelector('.upload-status-text');
        const progressFill = document.querySelector('.upload-progress-fill');
        const percentText = document.querySelector('.upload-percent');
        const sizeText = document.querySelector('.upload-size');
        const speedText = document.querySelector('.upload-speed');
        
        if (statusText) {
            statusText.textContent = `Uploading ${Math.min(this.completedFiles + 1, this.totalFiles)} of ${this.totalFiles} files`;
        }
        if (progressFill) {
            progressFill.style.width = `${percent}%`;
        }
        if (percentText) {
            percentText.textContent = `${percent}%`;
        }
        if (sizeText) {
            sizeText.textContent = this.formatBytes(this.uploadedBytes);
        }
        if (speedText && this.currentSpeed > 0) {
            speedText.textContent = `${this.formatBytes(this.currentSpeed)}/s`;
        }
        
        // Calculate ETA
        const etaText = document.querySelector('.upload-eta');
        if (etaText && this.currentSpeed > 0) {
            const remainingBytes = this.totalBytes - this.uploadedBytes;
            const etaSeconds = remainingBytes / this.currentSpeed;
            etaText.textContent = this.formatTime(etaSeconds);
        }
    }

    /**
     * Format seconds as human-readable time
     */
    formatTime(seconds) {
        if (!isFinite(seconds) || seconds < 0) return '';
        
        seconds = Math.round(seconds);
        
        if (seconds < 60) {
            return `${seconds}s left`;
        } else if (seconds < 3600) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return secs > 0 ? `${mins}m ${secs}s left` : `${mins}m left`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const mins = Math.floor((seconds % 3600) / 60);
            return mins > 0 ? `${hours}h ${mins}m left` : `${hours}h left`;
        }
    }

    /**
     * Check if all uploads are complete
     */
    checkAllComplete() {
        if (this.completedFiles >= this.totalFiles) {
            this.showComplete();
        }
    }

    /**
     * Show completion UI
     */
    showComplete() {
        this.isUploading = false;
        window.removeEventListener('beforeunload', this._beforeUnloadHandler);
        
        const statusText = document.querySelector('.upload-status-text');
        const progressFill = document.querySelector('.upload-progress-fill');
        const percentText = document.querySelector('.upload-percent');
        const cancelBtn = document.querySelector('.upload-cancel');
        
        // Hide cancel button
        if (cancelBtn) {
            cancelBtn.style.display = 'none';
        }
        
        const successCount = this.totalFiles - this.errors.length;
        
        if (progressFill) {
            progressFill.style.width = '100%';
            progressFill.classList.add(this.errors.length > 0 ? 'has-errors' : 'complete');
        }
        
        if (statusText) {
            if (this.errors.length === 0) {
                statusText.innerHTML = `<span class="upload-success">✓</span> ${successCount} file${successCount !== 1 ? 's' : ''} uploaded`;
            } else {
                statusText.innerHTML = `<span class="upload-success">✓</span> ${successCount} uploaded`;
            }
        }
        
        if (percentText) {
            percentText.textContent = 'Done';
        }
        
        // Show errors if any
        if (this.errors.length > 0) {
            const errorsSection = document.querySelector('.upload-errors');
            const errorsCount = document.querySelector('.upload-errors-count');
            const errorsList = document.querySelector('.upload-errors-list');
            
            if (errorsSection) {
                errorsSection.style.display = 'block';
            }
            if (errorsCount) {
                errorsCount.textContent = `${this.errors.length} failed`;
            }
            if (errorsList) {
                errorsList.innerHTML = this.errors.map(e => 
                    `<div class="upload-error-item">
                        <span class="upload-error-name">${this.escapeHtml(e.name)}</span>
                        <span class="upload-error-msg">${this.escapeHtml(e.error)}</span>
                    </div>`
                ).join('');
            }
        } else {
            // Auto-reload on success
            setTimeout(() => window.location.reload(), 800);
        }
    }

    /**
     * Toggle error list visibility
     */
    toggleErrors() {
        const list = document.querySelector('.upload-errors-list');
        if (list) {
            list.style.display = list.style.display === 'none' ? 'block' : 'none';
        }
    }

    /**
     * Cancel all pending uploads
     */
    cancelAll() {
        for (const { xhr } of this.activeUploads.values()) {
            xhr.abort();
        }
        this.activeUploads.clear();
    }

    /**
     * Cancel upload and hide UI
     */
    cancel() {
        this.cancelAll();
        this.isUploading = false;
        window.removeEventListener('beforeunload', this._beforeUnloadHandler);
        
        const container = document.getElementById('upload-progress');
        container.style.display = 'none';
        
        // Refresh to show any partially uploaded files
        if (this.completedFiles > 0) {
            window.location.reload();
        }
    }

    /**
     * Format bytes as human-readable string
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
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
