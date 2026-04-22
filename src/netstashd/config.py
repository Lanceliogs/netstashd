"""Application configuration using pydantic-settings."""

import re
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_size(value: str | int | float) -> int:
    """Parse a human-readable size string into bytes.
    
    Accepts:
        - Integers (bytes): 1073741824
        - Strings with units: "1GB", "1 GB", "1.5gb", "500MB", "100 mb"
        
    Supported units: B, KB, MB, GB, TB (case-insensitive)
    """
    if isinstance(value, (int, float)):
        return int(value)
    
    if not isinstance(value, str):
        raise ValueError(f"Cannot parse size from {type(value)}")
    
    value = value.strip().upper()
    
    # Try to parse as plain number first
    try:
        return int(value)
    except ValueError:
        pass
    
    # Parse with unit suffix
    match = re.match(r"^([\d.]+)\s*(B|KB|MB|GB|TB)?$", value)
    if not match:
        raise ValueError(
            f"Invalid size format: '{value}'. "
            "Use formats like '100MB', '1.5GB', '500 MB', or bytes as integer."
        )
    
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


# Custom type that accepts human-readable sizes
ByteSize = Annotated[int, BeforeValidator(parse_size)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage
    share_root: Path = Path("/data/stashes")

    # Auth
    admin_secret: str = "change-me-to-something-random"
    session_secret: str = "change-me-session-secret"

    # Limits (admin) - accepts "10GB", "500MB", or raw bytes
    global_max_bytes: ByteSize = 10 * 1024 * 1024 * 1024  # 10 GB
    reserve_bytes: ByteSize = 500 * 1024 * 1024  # 500 MB
    max_stash_size_bytes: ByteSize = 5 * 1024 * 1024 * 1024  # 5 GB
    max_ttl_days: int = 30

    # Limits (guest) - more restrictive defaults
    guest_max_stash_size_bytes: ByteSize = 100 * 1024 * 1024  # 100 MB
    guest_max_ttl_days: int = 7
    guest_require_ttl: bool = True  # Guests cannot create immortal stashes

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Session
    session_max_age_days: int = 365  # How long session cookies persist

    # Logging
    log_level: str = "INFO"

    # Cleanup settings
    expired_grace_days: int = 7  # Days to keep files after stash expires
    cleanup_on_startup: bool = True  # Run cleanup when server starts
    cleanup_interval_hours: int = 6  # Background cleanup interval (0 = disabled)

    # Temporary access codes
    code_ttl_seconds: int = 120  # How long access codes are valid

    @property
    def db_path(self) -> Path:
        return self.share_root / "stashes.db"

    @property
    def usable_bytes(self) -> int:
        """Maximum bytes available for stashes (global max minus reserve)."""
        return self.global_max_bytes - self.reserve_bytes


settings = Settings()
