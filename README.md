# [>] netstashd

A simple file sharing web application for your local network. Run it on your laptop, access files from any browser on the LAN.
It's basically there to replace USB sticks when on the same network and not connected to the internet, and on Windows when,
well, some people think that ssh and other basic human rights should be firewalled on already secure or isolated environment (seriously...).

## Features

- **Stash-based sharing**: Create isolated file storage areas with unique IDs
- **Drag & drop uploads**: Files and folders, with progress tracking
- **Batch operations**: Select multiple items to download or delete
- **Password protection**: Optional per-stash passwords
- **Quotas & TTL**: Set max size and expiration per stash
- **ZIP downloads**: Download folders or selections as ZIP archives
- **Rename**: Rename files and folders inline
- **Admin dashboard**: Manage all stashes from one place
- **CLI**: List, open, and manage stashes from the command line

## Quick Start

### Local Development

```bash
cd netstashd
poetry install

# Copy and edit config
cp .env.example .env
# Edit .env with your settings (especially ADMIN_SECRET)

# Run the server
poetry run netstashd-server
# Or: poetry run python -m netstashd
```

Open http://localhost:8000 in your browser.

### Docker

```bash
cp .env.example .env
# Edit .env with your ADMIN_SECRET

docker-compose up -d
```

## Configuration

Set these in `.env` or as environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SHARE_ROOT` | Directory to store stashes | `/data/stashes` |
| `ADMIN_SECRET` | Password for admin access and API | (required) |
| `SESSION_SECRET` | Secret for session cookies | (required) |
| `GLOBAL_MAX_BYTES` | Total storage limit | `10GB` |
| `RESERVE_BYTES` | Reserved free space | `500MB` |
| `MAX_STASH_SIZE_BYTES` | Max size per stash (admin) | `5GB` |
| `MAX_TTL_DAYS` | Max stash lifetime (admin) | 30 days |
| `GUEST_MAX_STASH_SIZE_BYTES` | Max size per stash (guest) | `100MB` |
| `GUEST_MAX_TTL_DAYS` | Max stash lifetime (guest) | 7 days |
| `GUEST_REQUIRE_TTL` | Force guests to set TTL (no immortal stashes) | `true` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `SESSION_MAX_AGE_DAYS` | How long session cookies persist in browser | 365 |

**Size formats:** All `*_BYTES` settings accept human-readable sizes: `100MB`, `1.5GB`, `10 GB`, or raw bytes.

## CLI Usage

The CLI talks to the server via API. Configure it with:

```bash
export NETSTASHD_SERVER=http://localhost:8000

# Option 1: Save API key to file (recommended, persists across sessions)
netstashd secrets set-api-key

# Option 2: Use environment variable
export NETSTASHD_API_KEY=your-admin-secret
```

The CLI checks `~/.netstashd_api_key` first, then falls back to the `NETSTASHD_API_KEY` env var.

### Stash Commands

```bash
# List all stashes
netstashd list

# Get stash info
netstashd info <stash-id>

# Open stash in browser
netstashd open <stash-id>

# Print stash URL
netstashd url <stash-id>

# Delete a stash
netstashd delete <stash-id>

# Check server status
netstashd status
```

### Secrets Management

```bash
# Check secrets status (file vs env source)
netstashd secrets status

# Rotate API key (generates new key, saves to ~/.netstashd_api_key)
netstashd secrets rotate-api-key

# Rotate session secret (invalidates all browser sessions, requires restart)
netstashd secrets rotate-session-secret

# Manually set API key
netstashd secrets set-api-key

# Show current API key (masked)
netstashd secrets show-api-key
```

## Usage

1. **Create a stash**: Anyone can create a stash from the home page (with guest limits), or admins can create larger/longer-lived stashes from the dashboard
2. **Share the URL**: Give the stash URL (`/s/<id>`) to others on your network
3. **Upload files**: Drag & drop files or folders, or click to browse
4. **Download**: Click the `⋯` menu on any item, or select multiple and batch download
5. **Manage**: Rename, delete, or create folders from the UI
6. **My Stashes**: Stashes you create or access are remembered in your browser session

## URL Structure

| Route | Purpose |
|-------|---------|
| `/s/<id>` | Stash root |
| `/s/<id>/fs/<path>` | Browse subfolder |
| `/s/<id>/download/<path>` | Download file or folder (ZIP) |
| `/dashboard` | Admin dashboard |
| `/login` | Admin login |

## Security Notes

- The stash ID (UUID) acts as a capability token — anyone with the URL can access (unless password-protected)
- Use stash passwords for sensitive content
- The admin password protects the dashboard and CLI access
- Guests can create stashes but with restricted size/TTL limits
- Guest stashes are tracked via session cookies (persist for 1 year by default, configurable via `SESSION_MAX_AGE_DAYS`)
- This is designed for **trusted local networks**, not public internet exposure

## License

MIT
