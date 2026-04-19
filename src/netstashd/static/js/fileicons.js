/**
 * File type icons and utilities
 * 
 * Uses SVG icons from /static/assets/icons/ with emoji fallback.
 * To add SVG icons: download from Heroicons (MIT) and place in assets/icons/
 */
const FileIcons = {
    // Base path for SVG icons
    svgBasePath: '/static/assets/icons/',
    
    // SVG icons are available (set to false for emoji fallback)
    useSvg: true,
    
    // SVG icon names (maps to filename without .svg extension)
    svgIcons: {
        folder: 'folder',
        file: 'document',
        image: 'photo',
        video: 'film',
        audio: 'musical-note',
        document: 'document-text',
        spreadsheet: 'table-cells',
        presentation: 'presentation-chart-bar',
        archive: 'archive-box',
        code: 'code-bracket',
        web: 'globe-alt',
        data: 'circle-stack',
        text: 'document-text',
        executable: 'cog-6-tooth',
        font: 'language',
        pdf: 'document',
    },
    
    // Emoji fallbacks (used when SVG not available)
    emojis: {
        folder: '📁',
        file: '📄',
        image: '🖼️',
        video: '🎬',
        audio: '🎵',
        document: '📄',
        spreadsheet: '📊',
        presentation: '📽️',
        archive: '📦',
        code: '💻',
        web: '🌐',
        data: '📋',
        text: '📝',
        executable: '⚙️',
        font: '🔤',
        pdf: '📑',
    },
    
    // Extension to icon type mapping
    extensionTypes: {
        // Images
        jpg: 'image', jpeg: 'image', png: 'image', gif: 'image', svg: 'image', 
        webp: 'image', bmp: 'image', ico: 'image', tiff: 'image', tif: 'image',
        
        // Videos
        mp4: 'video', webm: 'video', mov: 'video', avi: 'video', mkv: 'video',
        wmv: 'video', flv: 'video', m4v: 'video',
        
        // Audio
        mp3: 'audio', wav: 'audio', flac: 'audio', ogg: 'audio', m4a: 'audio',
        aac: 'audio', wma: 'audio', aiff: 'audio',
        
        // Documents
        pdf: 'pdf', doc: 'document', docx: 'document', odt: 'document', rtf: 'document',
        
        // Spreadsheets
        xls: 'spreadsheet', xlsx: 'spreadsheet', csv: 'spreadsheet', ods: 'spreadsheet',
        
        // Presentations
        ppt: 'presentation', pptx: 'presentation', odp: 'presentation',
        
        // Archives
        zip: 'archive', tar: 'archive', gz: 'archive', rar: 'archive', '7z': 'archive',
        bz2: 'archive', xz: 'archive', tgz: 'archive',
        
        // Code
        js: 'code', ts: 'code', jsx: 'code', tsx: 'code',
        py: 'code', rb: 'code', php: 'code', java: 'code',
        c: 'code', cpp: 'code', h: 'code', hpp: 'code',
        cs: 'code', go: 'code', rs: 'code', swift: 'code',
        kt: 'code', scala: 'code', r: 'code',
        
        // Web
        html: 'web', htm: 'web', css: 'web', scss: 'web', sass: 'web', less: 'web',
        
        // Data
        json: 'data', xml: 'data', yaml: 'data', yml: 'data', toml: 'data',
        
        // Text
        txt: 'text', md: 'text', markdown: 'text', log: 'text', ini: 'text', cfg: 'text',
        
        // Executables
        exe: 'executable', msi: 'executable', dmg: 'executable', app: 'executable', 
        deb: 'executable', rpm: 'executable',
        
        // Fonts
        ttf: 'font', otf: 'font', woff: 'font', woff2: 'font', eot: 'font',
    },
    
    // File type categories for preview support
    categories: {
        image: ['jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'bmp', 'ico'],
        video: ['mp4', 'webm', 'mov', 'ogg'],
        audio: ['mp3', 'wav', 'flac', 'ogg', 'm4a', 'aac', 'webm'],
        text: ['txt', 'md', 'markdown', 'log', 'ini', 'cfg', 'json', 'xml', 'yaml', 'yml', 'toml'],
        code: ['js', 'ts', 'jsx', 'tsx', 'py', 'rb', 'php', 'java', 'c', 'cpp', 'h', 'hpp', 
               'cs', 'go', 'rs', 'swift', 'kt', 'scala', 'html', 'htm', 'css', 'scss', 'sass'],
        pdf: ['pdf'],
    },

    /**
     * Get icon type for a filename
     */
    getIconType(filename, isDir = false) {
        if (isDir) return 'folder';
        const ext = this.getExtension(filename);
        return this.extensionTypes[ext] || 'file';
    },

    /**
     * Get icon for a filename (emoji string)
     */
    getIcon(filename, isDir = false) {
        const type = this.getIconType(filename, isDir);
        return this.emojis[type] || this.emojis.file;
    },

    /**
     * Get icon HTML (SVG with emoji fallback)
     */
    getIconHtml(filename, isDir = false, className = 'file-icon') {
        const type = this.getIconType(filename, isDir);
        
        if (this.useSvg) {
            const svgName = this.svgIcons[type] || this.svgIcons.file;
            return `<img src="${this.svgBasePath}${svgName}.svg" alt="" class="${className}" loading="lazy">`;
        }
        
        const emoji = this.emojis[type] || this.emojis.file;
        return `<span class="${className}">${emoji}</span>`;
    },

    /**
     * Get file extension (lowercase)
     */
    getExtension(filename) {
        const parts = filename.toLowerCase().split('.');
        return parts.length > 1 ? parts[parts.length - 1] : '';
    },

    /**
     * Get file category for preview type
     */
    getCategory(filename) {
        const ext = this.getExtension(filename);
        
        for (const [category, extensions] of Object.entries(this.categories)) {
            if (extensions.includes(ext)) {
                return category;
            }
        }
        return 'unknown';
    },

    /**
     * Check if file can be previewed
     */
    canPreview(filename) {
        const category = this.getCategory(filename);
        return ['image', 'video', 'audio', 'text', 'code', 'pdf'].includes(category);
    },

    /**
     * Get MIME type for preview
     */
    getMimeType(filename) {
        const ext = this.getExtension(filename);
        const mimeTypes = {
            // Images
            jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
            gif: 'image/gif', svg: 'image/svg+xml', webp: 'image/webp',
            bmp: 'image/bmp', ico: 'image/x-icon',
            // Videos
            mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
            ogg: 'video/ogg',
            // Audio
            mp3: 'audio/mpeg', wav: 'audio/wav', flac: 'audio/flac',
            m4a: 'audio/mp4', aac: 'audio/aac',
            // Text
            txt: 'text/plain', md: 'text/markdown', json: 'application/json',
            xml: 'application/xml', html: 'text/html', css: 'text/css',
            js: 'text/javascript',
            // PDF
            pdf: 'application/pdf',
        };
        return mimeTypes[ext] || 'application/octet-stream';
    },

    /**
     * Get language for syntax highlighting (if needed later)
     */
    getLanguage(filename) {
        const ext = this.getExtension(filename);
        const languages = {
            js: 'javascript', ts: 'typescript', jsx: 'jsx', tsx: 'tsx',
            py: 'python', rb: 'ruby', php: 'php', java: 'java',
            c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp',
            cs: 'csharp', go: 'go', rs: 'rust', swift: 'swift',
            html: 'html', htm: 'html', css: 'css', scss: 'scss',
            json: 'json', xml: 'xml', yaml: 'yaml', yml: 'yaml',
            md: 'markdown', sql: 'sql', sh: 'bash', bash: 'bash',
        };
        return languages[ext] || 'plaintext';
    }
};
