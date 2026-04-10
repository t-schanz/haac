"""haac init — interactive project setup."""

import asyncio
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt, Confirm

from haac.client import HAClient

console = Console()


def _write_haac_yaml(project_dir: Path, ha_url: str) -> None:
    path = project_dir / "haac.yaml"
    path.write_text(f'ha_url: "{ha_url}"\n')
    console.print(f"  [green]+[/green] created haac.yaml")


def _write_env(project_dir: Path, token: str) -> None:
    path = project_dir / ".env"
    path.write_text(f"HA_TOKEN={token}\n")
    console.print(f"  [green]+[/green] created .env")


def _write_gitignore(project_dir: Path) -> None:
    path = project_dir / ".gitignore"
    if path.exists():
        content = path.read_text()
        if ".env" in content:
            return
        path.write_text(content.rstrip() + "\n.env\n")
        console.print(f"  [yellow]~[/yellow] updated .gitignore")
    else:
        path.write_text(".env\n")
        console.print(f"  [green]+[/green] created .gitignore")


def _create_state_dir(project_dir: Path) -> None:
    state_dir = project_dir / "state"
    state_dir.mkdir(exist_ok=True)
    console.print(f"  [green]+[/green] created state/")


async def _test_connection(ha_url: str, token: str) -> bool:
    try:
        async with HAClient(ha_url, token) as client:
            await client.ws_command("config/floor_registry/list")
        return True
    except Exception as e:
        console.print(f"  [red]Error:[/red] {e}")
        return False


def run_init() -> None:
    console.print("\n[bold]haac init[/bold] — Home Assistant as Code\n")

    project_dir = Path.cwd()

    # Check if already initialized
    if (project_dir / "haac.yaml").exists():
        if not Confirm.ask("haac.yaml already exists. Reinitialize?", default=False):
            return

    # Ask for HA URL
    ha_url = Prompt.ask(
        "Home Assistant URL",
        default="http://homeassistant.local:8123",
    )
    ha_url = ha_url.rstrip("/")

    # Ask for token
    console.print(
        "\n[dim]Generate a long-lived access token at:[/dim]"
        f"\n[dim]  {ha_url}/profile → Long-Lived Access Tokens[/dim]\n"
    )
    token = Prompt.ask("HA access token")

    if not token:
        console.print("[red]Error:[/red] token is required")
        return

    # Test connection
    console.print("\n[bold]Testing connection...[/bold]")
    if asyncio.run(_test_connection(ha_url, token)):
        console.print("  [green]Connected successfully.[/green]")
    else:
        if not Confirm.ask("Connection failed. Save config anyway?", default=False):
            return

    # Create files
    console.print(f"\n[bold]Setting up project in {project_dir}[/bold]")
    _write_haac_yaml(project_dir, ha_url)
    _write_env(project_dir, token)
    _write_gitignore(project_dir)
    _create_state_dir(project_dir)

    console.print("\n[bold green]Done![/bold green]")
    console.print("\nNext steps:")
    console.print("  [cyan]haac pull[/cyan]    — import current HA state")
    console.print("  [cyan]haac plan[/cyan]    — see what would change")
    console.print("  [cyan]haac apply[/cyan]   — push changes to HA")

    # Offer to pull
    if Confirm.ask("\nPull current HA state now?", default=True):
        from haac.config import load_config
        config = load_config(project_dir)

        # Import providers
        import haac.providers.floors  # noqa: F401
        import haac.providers.labels  # noqa: F401
        import haac.providers.areas  # noqa: F401
        import haac.providers.devices  # noqa: F401
        import haac.providers.entities  # noqa: F401
        import haac.providers.automations  # noqa: F401
        import haac.providers.scenes  # noqa: F401
        import haac.providers.helpers  # noqa: F401
        import haac.providers.dashboard  # noqa: F401

        from haac.cli import _run_pull
        asyncio.run(_run_pull(config))
