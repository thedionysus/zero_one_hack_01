"""The thin Claude chat shell: NL curveball -> one Change, and diff -> narration.

Both jobs degrade to deterministic fallbacks (app/changes) when no client is
available, so the app demos fully with no ANTHROPIC_API_KEY. The Anthropic
client is injected (constructed in main.py only when a key is present), which
keeps this module unit-testable with a fake client and stdlib-only at import.
"""
import os

from app import changes

_MODEL = "claude-haiku-4-5"  # fast/cheap for a short NL->one-change + narration

_TOOL = {
    "name": "apply_change",
    "description": (
        "Translate the user's procurement curveball into exactly ONE concrete "
        "change to the decision inputs."),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": ["trend", "level", "stock", "demand", "carry",
                              "risk", "fertilizer", "reset"]},
            "value": {"description": "fraction for trend/level/carry, tonnes for "
                                     "stock, t/mo for demand, a quantile like "
                                     "'p70' for risk, a slug for fertilizer, or "
                                     "null for reset"},
        },
        "required": ["kind", "value"],
    },
}

_SYSTEM = (
    "You convert a fertilizer-procurement manager's plain-English curveball into "
    "exactly one tool call. A rising/spiking/surging price story is a 'trend' "
    "(fraction per month). A flat 'prices are X% higher' is a 'level' (fraction). "
    "Stock/runway news sets 'stock' (tonnes). Always call apply_change once.")


def _load_dotenv():
    """Populate ANTHROPIC_API_KEY from a gitignored repo-root .env if unset.

    Minimal stdlib loader (no python-dotenv dep): reads KEY=VALUE lines, ignores
    blanks/comments, and does not override an already-set environment variable.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def build_client():
    """Anthropic client if a key is available (env or .env), else None.

    None => the app uses the deterministic offline path (rule-based parse +
    template narration), so it still demos with no key. Set PROCUREMENT_NO_LLM=1
    to force the offline path even when a key exists (used by the app tests so
    they never hit the network).
    """
    if os.environ.get("PROCUREMENT_NO_LLM") == "1":
        return None
    _load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    import anthropic  # lazy: only when a key is present
    return anthropic.Anthropic()


def _extract_tool_change(message):
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and block.name == "apply_change":
            inp = block.input
            return changes.Change(inp["kind"], inp.get("value"))
    return None


def _extract_text(message):
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return block.text
    return None


def parse_curveball(text, client=None):
    """NL -> one Change. LLM (tool use) when client is given, else rule-based.

    Any LLM/parse failure degrades to rule_based_parse so a live demo never
    crashes on a network/rate-limit/auth error.
    """
    if client is None:
        return changes.rule_based_parse(text)
    try:
        message = client.messages.create(
            model=_MODEL, max_tokens=256, system=_SYSTEM, tools=[_TOOL],
            tool_choice={"type": "tool", "name": "apply_change"},
            messages=[{"role": "user", "content": text}])
        change = _extract_tool_change(message)
    except Exception:
        change = None
    return change if change is not None else changes.rule_based_parse(text)


def narrate(diff, change, eur_per_usd, client=None):
    """Before->after narration. Template by default; LLM rephrases if client given.

    Falls back to the template on any LLM failure or empty response.
    """
    template = changes.narrate_template(diff, change, eur_per_usd)
    if client is None:
        return template
    try:
        message = client.messages.create(
            model=_MODEL, max_tokens=160,
            system="Rephrase the procurement update in one or two crisp sentences "
                   "for a warehouse manager. Keep every number exactly as given.",
            messages=[{"role": "user", "content": template}])
        text = _extract_text(message)
    except Exception:
        text = None
    return text if text is not None else template
