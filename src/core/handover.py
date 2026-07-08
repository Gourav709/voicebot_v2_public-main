"""
Handover module — transfers the call to a human representative.

Currently a placeholder: logs the transfer to console and signals the
orchestrator to end the conversation.

Replace the body of `transfer()` with your actual telephony integration
(e.g. Exotel call transfer API, Twilio warm transfer, etc.)
"""
from rich.console import Console

console = Console()


def transfer(customer_context: dict, reason: str = "") -> None:
    """
    Initiate a call transfer to a human representative.

    Args:
        customer_context: Customer info dict (name, mobile, pan, etc.)
        reason:           Why the transfer was triggered (for logging/routing)

    TODO: Replace placeholder with real telephony transfer call.
          E.g. Exotel: POST /Calls/connect with agent number
               Twilio: conference room or warm transfer via REST API
    """
    name   = customer_context.get("customer_name", "Customer")
    mobile = customer_context.get("mobile_no", "unknown")

    console.print()
    console.print("─" * 80)
    console.print("[bold yellow]HANDOVER INITIATED[/bold yellow]")
    console.print(f"   Customer : {name} ({mobile})")
    if reason:
        console.print(f"   Reason   : {reason}")
    console.print("   Status   : [bold green]Transferring to human representative...[/bold green]")
    console.print("   [dim](Placeholder — wire in your telephony API here)[/dim]")
    console.print("─" * 80)
    console.print()