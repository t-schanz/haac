"""Rich console output for plan/apply."""

from rich.console import Console

from haac.models import PlanResult, Change, Unmanaged, ValidationWarning

console = Console()


def print_plan(plan: PlanResult) -> None:
    print_warnings(plan.warnings)

    if not plan.has_changes and plan.total_unmanaged == 0:
        console.print("[green]No changes needed — HA matches desired state.[/green]")
        return

    for result in plan.results:
        if not result.changes and not result.unmanaged:
            continue
        if result.changes:
            console.print(f"\n[bold]{result.provider_name.title()}:[/bold]")
            for c in result.changes:
                if c.action == "create":
                    console.print(f"  [green]+[/green] create \"[green]{c.name}[/green]\"")
                elif c.action == "update":
                    detail = f" [dim]({', '.join(c.details)})[/dim]" if c.details else ""
                    console.print(f"  [yellow]~[/yellow] update \"[yellow]{c.name}[/yellow]\"{detail}")
                elif c.action == "rename":
                    detail = f" [dim]({', '.join(c.details)})[/dim]" if c.details else ""
                    console.print(f"  [magenta]→[/magenta] rename \"[magenta]{c.name}[/magenta]\"{detail}")

    all_unmanaged = [u for r in plan.results for u in r.unmanaged]
    if all_unmanaged:
        console.print(f"\n[bold]Unmanaged[/bold] [dim](exists in HA but not in state files):[/dim]")
        console.print("  [dim]Delete with: haac delete <kind:id>[/dim]")
        for u in all_unmanaged:
            console.print(f"  [red]-[/red] \"{u.name}\" [dim]({u.resource_type}:{u.ha_id})[/dim]")

    parts = []
    if plan.total_creates: parts.append(f"{plan.total_creates} to create")
    if plan.total_updates: parts.append(f"{plan.total_updates} to update")
    if plan.total_renames: parts.append(f"{plan.total_renames} to rename")
    if plan.total_unmanaged: parts.append(f"{plan.total_unmanaged} unmanaged")
    console.print(f"\n[bold]Summary:[/bold] {', '.join(parts)}")


def print_warnings(warnings: list[ValidationWarning]) -> None:
    if not warnings:
        return
    console.print("\n[bold yellow]Warnings:[/bold yellow]")
    for w in warnings:
        console.print(f"  [yellow]⚠[/yellow] {w.file}: {w.message}")


def print_apply_change(c: Change) -> None:
    if c.action == "create":
        console.print(f"  [green]+[/green] created {c.resource_type} \"[green]{c.name}[/green]\"")
    elif c.action == "update":
        console.print(f"  [yellow]~[/yellow] updated {c.resource_type} \"[yellow]{c.name}[/yellow]\"")
    elif c.action == "rename":
        console.print(f"  [magenta]→[/magenta] renamed {c.resource_type} \"[magenta]{c.name}[/magenta]\"")


def print_pull_add(resource_type: str, name: str) -> None:
    console.print(f"  [green]+[/green] added {resource_type} \"[green]{name}[/green]\"")


def print_delete(resource_type: str, ha_id: str) -> None:
    console.print(f"  [red]-[/red] deleted {resource_type} \"[red]{ha_id}[/red]\"")
