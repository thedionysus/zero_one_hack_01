# Chat UI Visibility Redesign — Design

**Date:** 2026-05-30
**Scope:** `app/main.py` only (plus its tests). No `lib/` core changes.
**Status:** Approved (design); ready for implementation plan.

## Problem

The Streamlit demo has a working chat ("curveball") shell, but it does not read as a
chat interface:

- `st.chat_input` (`app/main.py:155`) is pinned by Streamlit to the **bottom of the
  viewport**.
- The conversation history (`app/main.py:192–196`) renders at the **bottom of a long,
  wide dashboard page** — under the metrics, both chart columns, and the trust table.

So the input and the messages are physically separated, the history is easy to miss,
and there is no visual "chat" framing (no panel, border, or persistent pane). It looks
like a dashboard with a stray text box.

## Goal

Make the chat unmistakably a chat: a single, prominent, bordered panel near the top of
the page that contains the conversation **and** its input together, with standard chat
affordances — without changing the decision core or the existing
curveball → move-levers → re-solve → narrate behavior.

## Decisions (locked)

- **Placement:** a top conversation **card** directly under the page title, above the
  metrics row.
- **Input:** the **native `st.chat_input`, rendered inline inside the card** (not the
  pinned viewport-bottom bar). Verified supported in Streamlit 1.58: a `chat_input`
  nested in a non-main container renders with `position = "inline"`.
- **Extras (all four):**
  - **Example-prompt chips** shown when the log is empty; one click fires that curveball.
  - **Fixed-height scrollable history** so a long conversation does not push the dashboard
    down the page.
  - **Clear control** that **resets the shock levers (trend + level) and wipes the chat
    transcript**.
  - **"Thinking" spinner** around the live LLM calls (visible on the Claude path; instant
    offline).
  - Plus chat essentials taken as given: role **avatars** (🧑 user / 🤖 agent), a
    **bordered titled panel** (`💬 Ask the agent`), and an **empty-state hint**.

## Approaches considered

1. **Single bordered card with an inline native `st.chat_input` — CHOSEN.** Keeps
   Streamlit's real chat-input UX (Enter-to-send, clear-on-submit, placeholder) while
   placing the input inside the card.
2. **Card with a custom `st.form` (text_input + Send).** Rejected: re-implements what
   `st.chat_input` already provides; more code, worse UX.
3. **Keep `st.chat_input` pinned at the viewport bottom; card shows history only.**
   Rejected: leaves the input separated from the conversation — the exact problem.

## Layout

A bordered, titled card (`💬 Ask the agent`) directly under the page title, above the
metrics. Top-to-bottom inside the card:

```
┌──────────────────────────────────────────────────┐
│ Fertilizer Procurement Decision Agent             │
│ ╔════════════ 💬 Ask the agent ═══════════════╗   │
│ ║ [ scrollable history, fixed height ]         ║   │
│ ║   🧑 gas spiked, prices +25%/mo              ║   │
│ ║   🤖 flips WAIT → BUY_NOW, saving €5.6M…      ║   │
│ ║ [example chips — only when log is empty]     ║   │
│ ║ [ inline st.chat_input … ]                   ║   │
│ ║ (Clear)                                      ║   │
│ ╚═════════════════════════════════════════════╝   │
│ [Rec]   [Target]   [Saving]                       │
│ forecast chart   calib chart / trust              │
│ savings bar      trust table                      │
└──────────────────────────────────────────────────┘
```

Charts, metrics, trust table, and the sidebar levers stay where they are.

## Components (all in `app/main.py`)

- `_chat_card(cal)` — builds the card: header, fixed-height history container, empty-state
  hint + example chips, inline `st.chat_input`, Clear button. Captures and returns any
  submitted input/chip/clear intent so `main()` can process it **before** the sidebar.
- `_example_chips()` — renders the clickable demo prompts; a click is routed through the
  same `_handle_curveball` path as typed input.
- `_clear_chat()` — wipes `st.session_state.chat_log` and zeroes the shock levers
  (`trend = 0.0`, `level = 0.0`), then reruns.
- Reused unchanged: `_handle_curveball`, `_resolve_pending`, `_write_change_to_widgets`,
  `_state_from_session`, `_sidebar`.

Held container references let the card be **created early** but its **history filled late**
(see ordering below).

## Data flow & ordering invariant (the crux)

The curveball (typed, chip, or clear) mutates widget `session_state` keys
(`trend`, `level`, `stock`, …). Streamlit forbids modifying a widget's state key **after**
that widget is instantiated. The sidebar sliders are those widgets. Therefore the card's
inputs must be **created and processed before `_sidebar`**, while the history is rendered
**after** the re-solve:

```
set_page_config
cal = get_calibrated();  _init_session(cal)
st.title(...) ; st.caption(...)                      # title early
card = st.container(border=True)                     # created early, under title
  with card:
    history = st.container(height=H)                 # placeholder, filled later
    (empty-state hint + example chips if log empty)
    prompt = st.chat_input(...)                      # inline; returns submitted text
    clear  = st.button("Clear")
process prompt / chip / clear  → writes widget state # BEFORE sidebar  ← invariant
state = _sidebar(cal)                                # sliders read updated state
res   = solve_state(state, cal) ; plan = res[...]
_resolve_pending(plan)                               # narrate → append to chat_log
with history:                                        # DEFERRED fill
    render chat_log messages with avatars (or hint)
metrics / charts / trust table                       # unchanged, below the card
```

This preserves today's behavior: a typed curveball or a chip moves the sliders **and**
re-solves the charts on the same run.

## Behavior of the four extras

- **Example chips:** buttons whose label text is fed to `_handle_curveball`. Processed
  early (same as the input). Shown only when `chat_log` is empty.
- **Fixed-height scroll:** history lives in `st.container(height=H)`; the input stays
  fixed below the scroll region (it is a direct child of the card, not of the scroll
  container).
- **Clear:** processed early; resets `chat_log` to `[]` and sets `trend`/`level`
  session-state to `0.0`, then `st.rerun()`.
- **Thinking spinner:** wrap the live LLM calls (`agent.parse_curveball`,
  `agent.narrate`) in `st.spinner("Thinking…")`. No-op cost on the offline path.

## Testing

Offline path only (`PROCUREMENT_NO_LLM=1`), via `streamlit.testing.v1.AppTest`.

- **Existing smoke tests keep passing** — `at.chat_input[0]` still resolves to the inline
  input; the curveball-flips-recommendation, unparseable-handled, and stock-curveball
  tests are unchanged.
- **New:**
  - Clicking an example chip fires its curveball and flips the recommendation metric.
  - Clear empties the chat log **and** zeroes the `trend` and `level` sliders.
  - The app renders without exception with the card present and a populated transcript
    (avatars/messages visible).

## Out of scope / NOT changing

- No `lib/` core changes.
- No change to parse/solve/narrate semantics or the offline-fallback contract.
- Charts, metrics, trust table, and sidebar levers stay as they are.
