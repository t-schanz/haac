"""CLI entry point for haac."""

import argparse
import asyncio
import sys

from haac.config import load_config
from haac.client import HAClient
from haac.models import PlanResult, HaacConfigError
from haac.output import print_plan, print_apply_change, print_delete, print_pull_add, print_warnings, console

# Import providers to trigger registration
import haac.providers.floors  # noqa: F401
import haac.providers.labels  # noqa: F401
import haac.providers.areas  # noqa: F401
import haac.providers.devices  # noqa: F401
import haac.providers.entities  # noqa: F401
import haac.providers.automations  # noqa: F401
import haac.providers.scenes  # noqa: F401
import haac.providers.helpers  # noqa: F401
import haac.providers.dashboard  # noqa: F401

from haac.providers import get_providers, get_provider, validate_references


async def _build_context(providers, client, config):
    """Build context dict with desired + current state for all providers."""
    from haac.git_ctx import GitContext

    context = {
        "git_ctx": GitContext(config.project_dir),
        "state_dir": config.state_dir,
    }
    for p in providers:
        if p.has_state_file(config.state_dir):
            context[f"desired_{p.name}"] = await p.read_desired(config.state_dir)
        context[p.name] = await p.read_current(client)
    return context


async def _run_plan(config):
    plan = PlanResult()

    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        desired_state = {
            p.name: context[f"desired_{p.name}"]
            for p in providers
            if f"desired_{p.name}" in context
        }
        plan.warnings = validate_references(desired_state)

        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)
            plan.results.append(result)

    print_plan(plan)
    return plan


async def _run_apply(config):
    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        desired_state = {
            p.name: context[f"desired_{p.name}"]
            for p in providers
            if f"desired_{p.name}" in context
        }
        warnings = validate_references(desired_state)
        print_warnings(warnings)

        any_changes = False
        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)

            if result.changes:
                any_changes = True
                console.print(f"\n[bold]{result.provider_name.title()}:[/bold]")
                for change in result.changes:
                    await provider.apply_change(client, change)
                    print_apply_change(change)

                # Refetch after apply for dependent providers
                context[provider.name] = await provider.read_current(client)

        if not any_changes:
            console.print("[green]No changes needed — HA matches desired state.[/green]")
        else:
            console.print("\n[bold green]Done.[/bold green]")


async def _run_pull(config):
    added = 0

    async with HAClient(config.ha_url, config.ha_token) as client:
        for provider in get_providers():
            new_names = await provider.pull(config.state_dir, client)
            for name in new_names:
                print_pull_add(provider.name, name)
            added += len(new_names)

    if added == 0:
        console.print("[green]No new items to pull — repo is up to date.[/green]")
    else:
        console.print(f"\n[bold green]Done.[/bold green] Added {added} new items.")


async def _run_delete(config, targets):
    async with HAClient(config.ha_url, config.ha_token) as client:
        for target in targets:
            if ":" not in target:
                console.print(f"[red]Error:[/red] invalid target \"{target}\" — expected kind:id")
                sys.exit(1)
            kind, ha_id = target.split(":", 1)
            # Try both singular and plural provider names
            provider = get_provider(f"{kind}s") or get_provider(kind)
            if not provider:
                console.print(f"[red]Error:[/red] unknown kind \"{kind}\"")
                sys.exit(1)
            try:
                await provider.delete(client, ha_id)
                print_delete(kind, ha_id)
            except RuntimeError as e:
                console.print(f"[red]Error:[/red] {e}")


def main():
    parser = argparse.ArgumentParser(prog="haac", description="Home Assistant as Code")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="Initialize a new haac project")
    subparsers.add_parser("plan", help="Show what would change in HA")
    subparsers.add_parser("apply", help="Apply changes to HA")
    subparsers.add_parser("pull", help="Pull HA state into local files (additive)")

    delete_parser = subparsers.add_parser("delete", help="Delete resources from HA")
    delete_parser.add_argument("targets", nargs="+", metavar="kind:id")

    args = parser.parse_args()

    if args.command == "init":
        from haac.init import run_init
        run_init()
        return

    config = load_config()

    if not config.ha_url:
        console.print("[red]Error:[/red] ha_url not set. Run [cyan]haac init[/cyan] or create haac.yaml.")
        sys.exit(1)
    if not config.ha_token:
        console.print("[red]Error:[/red] HA_TOKEN not set. Run [cyan]haac init[/cyan] or create .env with HA_TOKEN.")
        sys.exit(1)

    try:
        if args.command == "plan":
            plan = asyncio.run(_run_plan(config))
            sys.exit(2 if plan.has_changes else 0)
        elif args.command == "apply":
            asyncio.run(_run_apply(config))
        elif args.command == "pull":
            asyncio.run(_run_pull(config))
        elif args.command == "delete":
            asyncio.run(_run_delete(config, args.targets))
    except HaacConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
