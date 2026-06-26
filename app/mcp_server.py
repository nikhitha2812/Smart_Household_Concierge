import sys
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("homesync")

@mcp.tool()
def get_household_rules() -> str:
    """Get the household quiet hours and policies.

    Returns:
        A string listing quiet hours, chore policy, and split guidelines.
    """
    return (
        "HomeSync Household Rules:\n"
        "1. Quiet Hours: Sunday-Thursday: 10:00 PM - 7:00 AM; Friday-Saturday: 11:30 PM - 8:00 AM.\n"
        "2. Chores: All chores must be completed on their scheduled rotation. Missing a chore incurs a $5 fee added to the household fund.\n"
        "3. Grocery Split: Shared household items (cleaning supplies, spices, paper towels) are split equally. Personal groceries are paid individually.\n"
        "4. Expenses: All shared expenses must be logged within 48 hours of purchase."
    )

@mcp.tool()
def notify_roommates(message: str) -> str:
    """Simulate sending a broadcast notification or alert to all roommates.

    Args:
        message: The notification message text to broadcast.

    Returns:
        A confirmation string indicating the notification was sent successfully.
    """
    # Simulated notification broadcast
    return f"Broadcast Sent Successfully! Roommates notified: '{message}'"

@mcp.tool()
def calculate_split(total_amount: float, participants: list[str]) -> str:
    """Calculate the equal split of an expense total among roommates.

    Args:
        total_amount: The total expense amount to split (e.g. 120.0).
        participants: A list of names of roommates participating in this expense.

    Returns:
        A structured string detailing the split calculation per person.
    """
    if not participants:
        return "Error: No participants provided for split calculation."
    
    per_person = total_amount / len(participants)
    participants_str = ", ".join(participants)
    return (
        f"Expense Split Calculation:\n"
        f"Total Amount: ${total_amount:.2f}\n"
        f"Split Among: {participants_str} ({len(participants)} people)\n"
        f"Each Person Owes: ${per_person:.2f}"
    )

@mcp.tool()
def get_chore_points() -> str:
    """Get the point values associated with completing household chores.

    Returns:
        A structured breakdown of chores and their completion points.
    """
    return (
        "Household Chore Point Allocations:\n"
        "- Dishwashing: 10 points\n"
        "- Vacuuming Living Room: 15 points\n"
        "- Taking out Trash & Recycling: 5 points\n"
        "- Cleaning the Bathroom: 25 points\n"
        "- Grocery Shopping: 20 points\n"
        "\nComplete chores to earn points and claim rewards from the roommate points store!"
    )

if __name__ == "__main__":
    # Standard stdio execution
    mcp.run()
