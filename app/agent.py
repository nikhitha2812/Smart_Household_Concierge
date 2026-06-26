import os
import re
import json
import datetime
from typing import Any
from pydantic import BaseModel, Field

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import AgentTool, McpToolset

from google.adk.workflow import Workflow, Edge, START, node
from google.adk.agents.context import Context
from google.genai import types
from mcp import StdioServerParameters

from app.config import config

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"  # Always False for API key


# Define state schema for HomeSync
class HomeSyncState(BaseModel):
    user_input: str = ""
    chores: list[dict] = Field(default_factory=list)
    grocery_list: list[dict] = Field(default_factory=list)
    expenses: list[dict] = Field(default_factory=list)
    audit_logs: list[dict] = Field(default_factory=list)
    security_error: str = ""

# Helper to extract text from Content object
def extract_text(content: Any) -> str:
    if hasattr(content, "parts") and content.parts:
        parts = []
        for p in content.parts:
            if hasattr(p, "text") and p.text:
                parts.append(p.text)
        return "".join(parts)
    elif isinstance(content, dict) and "parts" in content:
        parts = []
        for p in content["parts"]:
            if isinstance(p, dict) and "text" in p:
                parts.append(p["text"])
        return "".join(parts)
    return str(content)

# Define local state management tools that agents can run
def get_chores(ctx: Context) -> str:
    """Get the current list of chores and their scheduling details.
    
    Returns:
        A list of current chores, who they are assigned to, and their status.
    """
    chores = ctx.state.get("chores") or []
    if not chores:
        return "No chores currently scheduled."
    
    lines = ["Current Chores:"]
    for c in chores:
        status_symbol = "[x]" if c.get("completed") else "[ ]"
        lines.append(f"- {status_symbol} {c['name']} (Assigned to: {c['assigned_to']}, Freq: {c['frequency']})")
    return "\n".join(lines)

def add_chore(ctx: Context, name: str, assigned_to: str, frequency: str) -> str:
    """Add a new chore to the household schedule.

    Args:
        name: Name of the chore (e.g., Clean Kitchen).
        assigned_to: Name of roommate responsible.
        frequency: How often it runs (e.g., Weekly, Daily).

    Returns:
        A confirmation string.
    """
    chores = ctx.state.get("chores") or []
    chores.append({
        "name": name,
        "assigned_to": assigned_to,
        "frequency": frequency,
        "completed": False
    })
    ctx.state["chores"] = chores
    return f"Chore '{name}' added and assigned to {assigned_to} ({frequency})."

def complete_chore(ctx: Context, name: str) -> str:
    """Mark a household chore as completed.

    Args:
        name: Name of the chore to complete.

    Returns:
        A confirmation string.
    """
    chores = ctx.state.get("chores") or []
    found = False
    for c in chores:
        if c["name"].lower() == name.lower():
            c["completed"] = True
            found = True
            break
    
    if found:
        ctx.state["chores"] = chores
        return f"Chore '{name}' successfully marked as completed."
    return f"Chore '{name}' not found."

def get_grocery_list(ctx: Context) -> str:
    """Get the current shared grocery list.

    Returns:
        A text representation of the grocery list.
    """
    g_list = ctx.state.get("grocery_list") or []
    if not g_list:
        return "The grocery list is currently empty."
    
    lines = ["Shared Grocery List:"]
    for item in g_list:
        lines.append(f"- {item['item_name']} ({item['quantity']}) - Category: {item['category']}")
    return "\n".join(lines)

def add_grocery_item(ctx: Context, item_name: str, quantity: str, category: str) -> str:
    """Add an item to the shared household grocery list.

    Args:
        item_name: Name of the grocery item.
        quantity: Quantity or description (e.g., 2 bottles, 1 pack).
        category: Food/store category (e.g., Produce, Dairy, Bakery).

    Returns:
        A confirmation string.
    """
    g_list = ctx.state.get("grocery_list") or []
    g_list.append({
        "item_name": item_name,
        "quantity": quantity,
        "category": category
    })
    ctx.state["grocery_list"] = g_list
    return f"Added {quantity} of '{item_name}' ({category}) to the grocery list."

def remove_grocery_item(ctx: Context, item_name: str) -> str:
    """Remove an item from the shared grocery list.

    Args:
        item_name: Exact name of the item to remove.

    Returns:
        A confirmation string.
    """
    g_list = ctx.state.get("grocery_list") or []
    new_list = [x for x in g_list if x["item_name"].lower() != item_name.lower()]
    if len(new_list) < len(g_list):
        ctx.state["grocery_list"] = new_list
        return f"Removed '{item_name}' from the grocery list."
    return f"'{item_name}' was not found on the grocery list."

def get_expenses(ctx: Context) -> str:
    """Get all logged household expenses and overall balances.

    Returns:
        A summary of shared expenses and what each person owes/is owed.
    """
    expenses = ctx.state.get("expenses") or []
    if not expenses:
        return "No expenses logged yet."
    
    lines = ["Logged Expenses:"]
    balances = {}
    
    for e in expenses:
        lines.append(f"- {e['description']}: ${e['amount']:.2f} (Paid by {e['paid_by']})")
        # Update balance sheet
        paid_by = e["paid_by"]
        split_with = e["split_with"]
        per_person = e["amount"] / (len(split_with) + 1)
        
        balances[paid_by] = balances.get(paid_by, 0.0) + e["amount"] - per_person
        for person in split_with:
            balances[person] = balances.get(person, 0.0) - per_person
            
    lines.append("\nNet Balances (positive means you are owed, negative means you owe):")
    for person, bal in balances.items():
        lines.append(f"- {person}: ${bal:.2f}")
    return "\n".join(lines)

def add_expense(ctx: Context, description: str, amount: float, paid_by: str, split_with: list[str]) -> str:
    """Log a new shared expense and split it among roommates.

    Args:
        description: Details of what was bought.
        amount: Cost of the expense.
        paid_by: Person who paid.
        split_with: List of names of roommates splitting this expense.

    Returns:
        A confirmation string.
    """
    expenses = ctx.state.get("expenses") or []
    expenses.append({
        "description": description,
        "amount": amount,
        "paid_by": paid_by,
        "split_with": split_with
    })
    ctx.state["expenses"] = expenses
    return f"Logged shared expense '{description}' of ${amount:.2f} paid by {paid_by}."

def settle_balances(ctx: Context) -> str:
    """Settle all logged household expenses, resetting balances.

    Returns:
        A string indicating all expenses are settled.
    """
    ctx.state["expenses"] = []
    return "All expenses have been settled and balances reset to $0.00."

# Configure MCP toolset connection
# We run mcp_server.py as a stdio subprocess using the current python executable
import sys
mcp_params = StdioServerParameters(
    command=sys.executable,
    args=["app/mcp_server.py"] if os.path.exists("app/mcp_server.py") else ["homesync/app/mcp_server.py"],
)
mcp_toolset = McpToolset(connection_params=mcp_params)

# Specialized sub-agents
chore_agent = LlmAgent(
    name="chore_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the HomeSync Chore Specialist.\n"
        "Your task is to coordinate chore schedules, rotas, point values, and completion.\n"
        "Use your local tools (get_chores, add_chore, complete_chore) to manage chores.\n"
        "Use the MCP server tool get_chore_points to fetch chore points if asked."
    ),
    tools=[mcp_toolset, get_chores, add_chore, complete_chore]
)

grocery_agent = LlmAgent(
    name="grocery_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the HomeSync Grocery Specialist.\n"
        "Your task is to manage the shared roommate grocery list.\n"
        "Use local tools (get_grocery_list, add_grocery_item, remove_grocery_item) to keep it updated."
    ),
    tools=[get_grocery_list, add_grocery_item, remove_grocery_item]
)

budget_agent = LlmAgent(
    name="budget_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the HomeSync Budget and Split Specialist.\n"
        "Your task is to manage shared expenses, calculate splits, and check net balances.\n"
        "Use local tools (get_expenses, add_expense, settle_balances) to track expenses.\n"
        "Use MCP server tools (calculate_split, get_household_rules) to fetch split math or rules.\n"
        "Ensure all calculations are formatted clearly and look professional."
    ),
    tools=[mcp_toolset, get_expenses, add_expense, settle_balances]
)

# Wrap sub-agents in AgentTools for orchestrator delegation
chore_agent_tool = AgentTool(agent=chore_agent)
grocery_agent_tool = AgentTool(agent=grocery_agent)
budget_agent_tool = AgentTool(agent=budget_agent)

# Orchestrator agent
orchestrator = LlmAgent(
    name="orchestrator",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the HomeSync Orchestrator, the main roommate concierge.\n"
        "Your job is to route requests to the correct specialized sub-agent:\n"
        "- Use chore_agent for anything about chores (complete, add, list, points).\n"
        "- Use grocery_agent for managing grocery lists (add, remove, view items).\n"
        "- Use budget_agent for logged expenses, split calculations, balances, or roommate settlement.\n"
        "\nDelegate roommate requests using your tools. Be concise, friendly, and helpful."
    ),
    tools=[chore_agent_tool, grocery_agent_tool, budget_agent_tool]
)

# Security node function
@node
async def security_checkpoint(ctx: Context, node_input: Any):
    raw_text = extract_text(node_input)
    
    # 1. PII Redaction
    scrubbed_text = raw_text
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", scrubbed_text)
    
    phone_pattern = r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'
    scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)
    
    # 2. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", "system prompt", "ignore instructions",
        "ignore rules", "override instructions", "you are now a"
    ]
    has_injection = any(kw in raw_text.lower() for kw in injection_keywords)
    
    # 3. Domain policy checks: Budget Cap of $500
    has_policy_violation = False
    policy_violation_msg = ""
    
    # Simple regex to search for amounts exceeding $500
    amounts = re.findall(r'\$\s*(\d+(?:\.\d{2})?)|\b(\d+(?:\.\d{2})?)\s*dollars\b', raw_text, re.IGNORECASE)
    for amt in amounts:
        val_str = amt[0] or amt[1]
        try:
            val = float(val_str)
            if val > 500.0:
                has_policy_violation = True
                policy_violation_msg = f"Expense amount ${val:.2f} exceeds the household limit of $500."
                break
        except ValueError:
            pass
            
    # 4. Structured JSON Audit Log
    severity = "INFO"
    status = "CLEAN"
    route = "orchestrate"
    
    if has_injection:
        severity = "CRITICAL"
        status = "PROMPT_INJECTION_DETECTED"
        route = "security_violation"
    elif has_policy_violation:
        severity = "WARNING"
        status = f"POLICY_VIOLATION: {policy_violation_msg}"
        route = "security_violation"
        
    audit_log = {
        "timestamp": datetime.datetime.now().isoformat(),
        "severity": severity,
        "status": status,
        "input_length": len(raw_text),
        "route_selected": route
    }
    
    # Print the log in standard JSON format for audit purposes
    print(f"AUDIT_LOG: {json.dumps(audit_log)}")
    
    # Save the audit log to state
    logs = ctx.state.get("audit_logs") or []
    logs.append(audit_log)
    ctx.state["audit_logs"] = logs
    
    if route == "orchestrate":
        ctx.state["user_input"] = scrubbed_text
        ctx.route = "orchestrate"
        return scrubbed_text
    else:
        ctx.route = "security_violation"
        ctx.state["security_error"] = f"Request blocked due to: {status}"
        return f"Block: {status}"

# Security Violation Terminal Node
@node
async def security_violation_node(ctx: Context):
    error_msg = ctx.state.get("security_error") or "Request blocked due to security policy violation."
    return f"Security Checkpoint Alert: {error_msg}"

# Build workflow graph edges using explicit Edge instances
workflow = Workflow(
    name="homesync_workflow",
    description="Secure household concierge workflow.",
    state_schema=HomeSyncState,
    edges=[
        Edge(from_node=START, to_node=security_checkpoint),
        Edge(from_node=security_checkpoint, to_node=orchestrator, route="orchestrate"),
        Edge(from_node=security_checkpoint, to_node=security_violation_node, route="security_violation"),
    ]
)

# Export the app
app = App(
    name="app",
    root_agent=workflow
)

