"""CLI for netstashd - talks to the server API."""

import os
import webbrowser
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="netstashd",
    help="netstashd CLI - Manage stashes via the server API",
)
secrets_app = typer.Typer(help="Manage API keys and secrets")
cleanup_app = typer.Typer(help="Cleanup expired stashes")
app.add_typer(secrets_app, name="secrets")
app.add_typer(cleanup_app, name="cleanup")

console = Console()

API_KEY_FILE = Path.home() / ".netstashd_api_key"


def get_server() -> str:
    """Get server URL from environment or default."""
    return os.environ.get("NETSTASHD_SERVER", "http://localhost:8000")


def get_api_key() -> str:
    """Get API key from file or environment.
    
    Priority: ~/.netstashd_api_key > NETSTASHD_API_KEY env var
    """
    # Try file first
    if API_KEY_FILE.exists():
        key = API_KEY_FILE.read_text().strip()
        if key:
            return key
    
    # Fall back to env var
    key = os.environ.get("NETSTASHD_API_KEY", "")
    if not key:
        console.print("[red]Error:[/red] No API key found.")
        console.print(f"Set NETSTASHD_API_KEY env var or save key to {API_KEY_FILE}")
        raise typer.Exit(1)
    return key


def save_api_key(key: str) -> None:
    """Save API key to the local file."""
    API_KEY_FILE.write_text(key)
    # Restrict permissions on Unix
    try:
        API_KEY_FILE.chmod(0o600)
    except OSError:
        pass
    console.print(f"[green]API key saved to {API_KEY_FILE}[/green]")


def make_request(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an authenticated request to the server."""
    server = get_server()
    api_key = get_api_key()
    
    headers = kwargs.pop("headers", {})
    headers["X-API-Key"] = api_key
    
    url = f"{server}{path}"
    
    try:
        response = httpx.request(method, url, headers=headers, **kwargs)
        return response
    except httpx.ConnectError:
        console.print(f"[red]Error:[/red] Cannot connect to server at {server}")
        raise typer.Exit(1)


@app.command()
def list():
    """List all stashes."""
    response = make_request("GET", "/api/stashes")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    stashes = response.json()
    
    if not stashes:
        console.print("No stashes found.")
        return
    
    table = Table(title="Stashes")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Usage")
    table.add_column("Expires")
    table.add_column("Protected")
    
    for stash in stashes:
        used = stash["used_bytes"]
        max_size = stash["max_size_bytes"]
        usage_pct = (used / max_size * 100) if max_size > 0 else 0
        usage = f"{format_bytes(used)} / {format_bytes(max_size)} ({usage_pct:.0f}%)"
        
        expires = stash.get("expires_at", "")
        if expires:
            expires = expires[:10]
        else:
            expires = "Never"
        
        protected = "Yes" if stash["is_password_protected"] else "No"
        
        table.add_row(
            stash["name"],
            stash["id"],
            usage,
            expires,
            protected,
        )
    
    console.print(table)


@app.command()
def info(stash_id: str):
    """Get info about a stash."""
    response = make_request("GET", f"/api/stashes/{stash_id}")
    
    if response.status_code == 404:
        console.print(f"[red]Error:[/red] Stash not found: {stash_id}")
        raise typer.Exit(1)
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    stash = response.json()
    
    console.print(f"[bold]Name:[/bold] {stash['name']}")
    console.print(f"[bold]ID:[/bold] {stash['id']}")
    console.print(f"[bold]Usage:[/bold] {format_bytes(stash['used_bytes'])} / {format_bytes(stash['max_size_bytes'])}")
    console.print(f"[bold]Password Protected:[/bold] {'Yes' if stash['is_password_protected'] else 'No'}")
    
    expires = stash.get("expires_at")
    if expires:
        console.print(f"[bold]Expires:[/bold] {expires[:10]}")
    else:
        console.print("[bold]Expires:[/bold] Never")
    
    console.print(f"[bold]Created:[/bold] {stash['created_at'][:19]}")


@app.command()
def open(stash_id: str):
    """Open a stash in the default browser."""
    server = get_server()
    url = f"{server}/s/{stash_id}"
    console.print(f"Opening {url}")
    webbrowser.open(url)


@app.command()
def delete(
    stash_id: str,
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a stash."""
    if not force:
        confirm = typer.confirm(f"Delete stash {stash_id}? This cannot be undone")
        if not confirm:
            raise typer.Abort()
    
    response = make_request("DELETE", f"/s/{stash_id}")
    
    if response.status_code == 404:
        console.print(f"[red]Error:[/red] Stash not found: {stash_id}")
        raise typer.Exit(1)
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    console.print(f"[green]Deleted stash {stash_id}[/green]")


@app.command()
def status():
    """Check server status."""
    response = make_request("GET", "/api/status")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] Server returned {response.status_code}")
        raise typer.Exit(1)
    
    data = response.json()
    console.print(f"[green]Server is running[/green]")
    console.print(f"[bold]Global Max:[/bold] {format_bytes(data['global_max_bytes'])}")
    console.print(f"[bold]Remaining:[/bold] {format_bytes(data['remaining_bytes'])}")


@app.command()
def url(stash_id: str):
    """Print the URL for a stash."""
    server = get_server()
    url = f"{server}/s/{stash_id}"
    console.print(url)


def format_bytes(size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# --- Secrets management commands ---


@secrets_app.command("status")
def secrets_status():
    """Check which secrets are using file storage vs env vars."""
    response = make_request("GET", "/api/secrets/status")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    data = response.json()
    
    console.print("[bold]Server secrets status:[/bold]")
    console.print(f"  Admin API Key: loaded from [cyan]{data['admin_secret']['source']}[/cyan]")
    console.print(f"  Session Secret: loaded from [cyan]{data['session_secret']['source']}[/cyan]")
    
    console.print()
    console.print("[bold]CLI API key:[/bold]")
    if API_KEY_FILE.exists():
        console.print(f"  Loaded from [cyan]{API_KEY_FILE}[/cyan]")
    else:
        console.print("  Loaded from [cyan]NETSTASHD_API_KEY env var[/cyan]")


@secrets_app.command("rotate-api-key")
def rotate_api_key(
    save: bool = typer.Option(True, "--save/--no-save", help="Save new key to ~/.netstashd_api_key"),
):
    """Rotate the admin API key.
    
    Generates a new API key on the server and optionally saves it locally.
    The old key is immediately invalidated.
    """
    confirm = typer.confirm(
        "This will invalidate the current API key immediately. Continue?"
    )
    if not confirm:
        raise typer.Abort()
    
    response = make_request("POST", "/api/secrets/rotate-api-key")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    data = response.json()
    new_key = data["new_api_key"]
    
    console.print("[green]API key rotated successfully![/green]")
    
    if save:
        save_api_key(new_key)
    else:
        console.print()
        console.print("[yellow]New API key (save this!):[/yellow]")
        console.print(f"  {new_key}")
        console.print()
        console.print(f"[dim]To save manually: echo '{new_key}' > ~/.netstashd_api_key[/dim]")


@secrets_app.command("rotate-session-secret")
def rotate_session_secret():
    """Rotate the session secret.
    
    WARNING: This invalidates ALL browser sessions!
    Users will need to log in again and re-authenticate to stashes.
    Requires server restart to take effect.
    """
    console.print("[yellow]WARNING: This will invalidate ALL browser sessions![/yellow]")
    console.print("Users will need to log in again after you restart the server.")
    console.print()
    
    confirm = typer.confirm("Are you sure you want to rotate the session secret?")
    if not confirm:
        raise typer.Abort()
    
    response = make_request("POST", "/api/secrets/rotate-session-secret")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    console.print("[green]Session secret rotated.[/green]")
    console.print("[yellow]Restart the server for changes to take effect.[/yellow]")


@secrets_app.command("set-api-key")
def set_api_key(
    key: str = typer.Option(..., prompt=True, hide_input=True, help="The API key to save"),
):
    """Save an API key to ~/.netstashd_api_key for CLI use.
    
    Use this to configure the CLI with an existing API key.
    """
    save_api_key(key)


@secrets_app.command("show-api-key")
def show_api_key():
    """Show the current API key being used by the CLI."""
    try:
        key = get_api_key()
        # Show only first/last 4 chars for security
        if len(key) > 12:
            masked = f"{key[:4]}...{key[-4:]}"
        else:
            masked = "****"
        
        console.print(f"[bold]API Key:[/bold] {masked}")
        
        if API_KEY_FILE.exists():
            console.print(f"[dim]Source: {API_KEY_FILE}[/dim]")
        else:
            console.print("[dim]Source: STASHD_API_KEY environment variable[/dim]")
    except typer.Exit:
        pass


# --- Cleanup commands ---


def parse_size(size_str: str) -> int:
    """Parse a human-readable size string into bytes."""
    import re
    size_str = size_str.strip().upper()
    
    match = re.match(r"^([\d.]+)\s*(B|KB|MB|GB|TB)?$", size_str)
    if not match:
        raise typer.BadParameter(f"Invalid size format: {size_str}")
    
    number = float(match.group(1))
    unit = match.group(2) or "B"
    
    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 ** 2,
        "GB": 1024 ** 3,
        "TB": 1024 ** 4,
    }
    
    return int(number * multipliers[unit])


@cleanup_app.command("run")
def cleanup_run(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without deleting"),
):
    """Run cleanup of stashes past their grace period.
    
    This deletes stashes where expiration + grace period has elapsed.
    """
    response = make_request("POST", f"/api/cleanup?dry_run={str(dry_run).lower()}")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    data = response.json()
    
    if dry_run:
        console.print("[yellow]DRY RUN - no changes made[/yellow]")
    
    if data["deleted_count"] == 0:
        console.print("No stashes ready for cleanup.")
    else:
        action = "Would delete" if dry_run else "Deleted"
        console.print(f"[green]{action} {data['deleted_count']} stash(es)[/green]")
        console.print(f"[bold]Space freed:[/bold] {format_bytes(data['freed_bytes'])}")
        
        if data["stash_ids"]:
            console.print()
            console.print("[bold]Stash IDs:[/bold]")
            for stash_id in data["stash_ids"]:
                console.print(f"  {stash_id}")


@cleanup_app.command("free-space")
def cleanup_free_space(
    target: str = typer.Argument(..., help="Target space to free (e.g., '1GB', '500MB')"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without deleting"),
):
    """Delete oldest expired stashes until target space is freed.
    
    This deletes expired stashes (even those still in grace period),
    starting with the oldest, until the target space is freed.
    """
    try:
        target_bytes = parse_size(target)
    except typer.BadParameter as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    
    response = make_request(
        "POST",
        f"/api/cleanup/free-space?dry_run={str(dry_run).lower()}",
        json={"target_bytes": target_bytes},
    )
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    data = response.json()
    
    if dry_run:
        console.print("[yellow]DRY RUN - no changes made[/yellow]")
    
    console.print(f"[bold]Target:[/bold] {format_bytes(data['target_bytes'])}")
    
    if data["deleted_count"] == 0:
        console.print("[yellow]No expired stashes available to free space.[/yellow]")
    else:
        action = "Would free" if dry_run else "Freed"
        console.print(f"[green]{action} {format_bytes(data['freed_bytes'])} by deleting {data['deleted_count']} stash(es)[/green]")
        
        if data["freed_bytes"] < data["target_bytes"]:
            console.print(f"[yellow]Warning: Could not reach target. No more expired stashes available.[/yellow]")


@cleanup_app.command("purge")
def cleanup_purge(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted without deleting"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete ALL expired stashes immediately, ignoring grace period.
    
    Use with caution - this removes all expired stashes regardless of
    how much grace time remains.
    """
    if not force and not dry_run:
        confirm = typer.confirm("This will delete ALL expired stashes. Continue?")
        if not confirm:
            raise typer.Abort()
    
    response = make_request("POST", f"/api/cleanup/purge-expired?dry_run={str(dry_run).lower()}")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    data = response.json()
    
    if dry_run:
        console.print("[yellow]DRY RUN - no changes made[/yellow]")
    
    if data["deleted_count"] == 0:
        console.print("No expired stashes to purge.")
    else:
        action = "Would purge" if dry_run else "Purged"
        console.print(f"[green]{action} {data['deleted_count']} stash(es)[/green]")
        console.print(f"[bold]Space freed:[/bold] {format_bytes(data['freed_bytes'])}")


@cleanup_app.command("list")
def cleanup_list():
    """List all expired stashes (in grace period or ready for cleanup)."""
    response = make_request("GET", "/api/stashes/expired")
    
    if response.status_code != 200:
        console.print(f"[red]Error:[/red] {response.text}")
        raise typer.Exit(1)
    
    stashes = response.json()
    
    if not stashes:
        console.print("No expired stashes.")
        return
    
    table = Table(title="Expired Stashes")
    table.add_column("Name", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Disk Usage")
    table.add_column("Expired")
    table.add_column("Grace Remaining")
    table.add_column("Status")
    
    for item in stashes:
        stash = item["stash"]
        grace_seconds = item["grace_remaining_seconds"]
        
        if item["past_grace"]:
            grace_str = "-"
            status = "[red]Ready for cleanup[/red]"
        else:
            hours = grace_seconds // 3600
            days = hours // 24
            if days > 0:
                grace_str = f"{days}d {hours % 24}h"
            else:
                grace_str = f"{hours}h"
            status = "[yellow]In grace period[/yellow]"
        
        expires = stash.get("expires_at", "")[:10] if stash.get("expires_at") else "Never"
        
        table.add_row(
            stash["name"],
            stash["id"],
            format_bytes(item["disk_size"]),
            expires,
            grace_str,
            status,
        )
    
    console.print(table)


if __name__ == "__main__":
    app()
