"""Safe local launcher that derives Streamlit bind settings from config.toml."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from reviewlens.config import AppSettings, load_settings


def build_streamlit_command(
    settings: AppSettings,
    *,
    python_executable: str = sys.executable,
    script_path: Path | None = None,
) -> tuple[str, ...]:
    selected_script = script_path or Path(__file__).with_name("streamlit_app.py")
    return (
        python_executable,
        "-m",
        "streamlit",
        "run",
        str(selected_script.resolve()),
        f"--server.address={settings.app.bind_host}",
        f"--server.port={settings.app.port}",
        "--server.headless=true",
        "--server.enableCORS=true",
        "--server.enableXsrfProtection=true",
        "--client.showErrorDetails=none",
        "--browser.gatherUsageStats=false",
    )


def main() -> None:
    command = build_streamlit_command(load_settings())
    subprocess.run(command, check=True)  # noqa: S603 - fixed module and validated local config
