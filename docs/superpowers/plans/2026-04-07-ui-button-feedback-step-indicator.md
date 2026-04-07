# UI Button Feedback & Step Indicator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add visible click feedback to all buttons and redesign the step indicator as pill cards with clear completed/active/future states.

**Architecture:** Pure CSS changes plus a rewrite of the `render_steps()` Python function in `app.py`. No new files, dependencies, or JavaScript.

**Tech Stack:** Streamlit CSS overrides, Python (inline HTML generation)

**Spec:** `docs/superpowers/specs/2026-04-07-ui-button-feedback-step-indicator-design.md`

---

### Task 1: Add `:active` click feedback to all standard buttons

**Files:**
- Modify: `app.py:223-236` (button CSS block)

- [ ] **Step 1: Update the standard button CSS block**

Replace the existing button CSS at lines 223–236 with:

```css
/* ── Buttons ───────────────────────────────────────────────────── */
.stButton > button {
    background: #111111 !important;
    border: 1px solid #2a2a2a !important;
    color: #cccccc !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background: #1a1a1a !important;
    border-color: #3a3a3a !important;
    color: #ffffff !important;
}
.stButton > button:active {
    background: #0a0a0a !important;
    border-color: #4a90d9 !important;
    color: #ffffff !important;
    transform: scale(0.97) !important;
}
```

The old code is lines 223–236 of `app.py`. The `old_string` for the Edit tool is:

```
/* ── Buttons ───────────────────────────────────────────────────── */
.stButton > button {
    background: #111111 !important;
    border: 1px solid #2a2a2a !important;
    color: #cccccc !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: #1a1a1a !important;
    border-color: #3a3a3a !important;
    color: #ffffff !important;
}
```

- [ ] **Step 2: Verify the app still loads**

Run: `streamlit run app.py` (or reload the Streamlit Cloud deployment). Confirm the page loads without errors and buttons render with the dark background.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add :active click feedback to standard buttons"
```

---

### Task 2: Add `:active` click feedback to primary buttons

**Files:**
- Modify: `app.py:237-247` (primary button CSS block)

- [ ] **Step 1: Replace the primary button CSS block**

Replace the existing primary button CSS at lines 237–247 with:

```css
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1a3a6e, #2271c2) !important;
    border: 1px solid #2271c2 !important;
    color: #ffffff !important;
    padding: 0.4rem 1.5rem !important;
    letter-spacing: 0.02em !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2271c2, #4a90d9) !important;
    border-color: #4a90d9 !important;
}
.stButton > button[kind="primary"]:active {
    background: linear-gradient(135deg, #0e2144, #1a3a6e) !important;
    transform: scale(0.97) !important;
}
```

The old code is lines 237–247 of `app.py`. The `old_string` for the Edit tool is:

```
.stButton > button[kind="primary"] {
    background: #1a1a1a !important;
    border: 1px solid #404040 !important;
    color: #ffffff !important;
    padding: 0.4rem 1.5rem !important;
    letter-spacing: 0.02em !important;
}
.stButton > button[kind="primary"]:hover {
    background: #252525 !important;
    border-color: #555555 !important;
}
```

- [ ] **Step 2: Verify primary buttons render with gradient**

Reload the app. The "Search" button should show a blue gradient. Clicking it should briefly scale down and darken.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add gradient and :active feedback to primary buttons"
```

---

### Task 3: Add `:active` click feedback to chip buttons

**Files:**
- Modify: `app.py:420-434` (chip button CSS block)

- [ ] **Step 1: Replace the chip button CSS block**

Replace the existing chip button CSS at lines 420–434 with:

```css
div[data-testid="column"] .stButton > button {
    background: #0a0a0a !important;
    border: 1px solid #222222 !important;
    border-radius: 20px !important;
    color: #666666 !important;
    font-size: 0.70rem !important;
    font-weight: 600 !important;
    padding: 4px 0 !important;
    transition: all 0.15s ease !important;
}
div[data-testid="column"] .stButton > button:hover {
    background: #141414 !important;
    border-color: #333333 !important;
    color: #cccccc !important;
}
div[data-testid="column"] .stButton > button:active {
    background: #0a0a0a !important;
    border-color: #4a90d9 !important;
    color: #ffffff !important;
    transform: scale(0.97) !important;
}
```

The old code is lines 420–434 of `app.py`. The `old_string` for the Edit tool is:

```
div[data-testid="column"] .stButton > button {
    background: #0a0a0a !important;
    border: 1px solid #222222 !important;
    border-radius: 20px !important;
    color: #666666 !important;
    font-size: 0.70rem !important;
    font-weight: 600 !important;
    padding: 4px 0 !important;
    transition: all 0.15s !important;
}
div[data-testid="column"] .stButton > button:hover {
    background: #141414 !important;
    border-color: #333333 !important;
    color: #cccccc !important;
}
```

- [ ] **Step 2: Verify chip buttons have click feedback**

Reload the app (no firm confirmed — step 1 view). The example firm chips ("Ares Management", etc.) should scale down and flash a blue border on click.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add :active click feedback to chip buttons"
```

---

### Task 4: Rewrite `render_steps()` as pill cards

**Files:**
- Modify: `app.py:613-641` (`render_steps` function)

- [ ] **Step 1: Replace the `render_steps` function**

Replace the entire function at lines 613–641 with:

```python
def render_steps(current_step):
    steps = [
        ("Search",  "Firm name or CRD"),
        ("Confirm", "Select from IAPD"),
        ("Analyze", "8 agents run"),
        ("Review",  "Download report"),
    ]
    html = '<div style="display:flex;gap:8px;padding:0 2px">'
    for i, (name, desc) in enumerate(steps, 1):
        completed = i < current_step
        active = i == current_step

        if completed:
            pill_bg = "#0d2a1d"
            pill_border = "1px solid #2ecc71"
            pill_shadow = ""
            pill_opacity = ""
            icon = '<div style="font-size:14px;color:#2ecc71;flex-shrink:0">&#10003;</div>'
            name_style = "font-size:11px;font-weight:700;color:#2ecc71"
            desc_style = "font-size:9px;color:#1a5a32"
            desc_text = "Completed"
        elif active:
            pill_bg = "#0d1f35"
            pill_border = "1.5px solid #4a90d9"
            pill_shadow = "box-shadow:0 0 10px rgba(74,144,217,0.3);"
            pill_opacity = ""
            icon = (
                f'<div style="width:22px;height:22px;border-radius:50%;background:#2271c2;'
                f'display:flex;align-items:center;justify-content:center;font-size:11px;'
                f'color:white;font-weight:800;flex-shrink:0">{i}</div>'
            )
            name_style = "font-size:11px;font-weight:800;color:#ffffff"
            desc_style = "font-size:9px;color:#4a90d9"
            desc_text = desc
        else:
            pill_bg = "#0a0a0a"
            pill_border = "1px solid #1a1a1a"
            pill_shadow = ""
            pill_opacity = "opacity:0.5;"
            icon = (
                f'<div style="width:22px;height:22px;border-radius:50%;background:#1a1d2a;'
                f'border:1px solid #22253a;display:flex;align-items:center;justify-content:center;'
                f'font-size:11px;color:#3d4260;font-weight:600;flex-shrink:0">{i}</div>'
            )
            name_style = "font-size:11px;font-weight:400;color:#3d4260"
            desc_style = "font-size:9px;color:#2a2d40"
            desc_text = desc

        html += (
            f'<div style="flex:1;background:{pill_bg};border:{pill_border};border-radius:8px;'
            f'padding:10px 14px;display:flex;align-items:center;gap:10px;{pill_shadow}{pill_opacity}">'
            f'{icon}'
            f'<div>'
            f'<div style="{name_style}">{name}</div>'
            f'<div style="{desc_style}">{desc_text}</div>'
            f'</div></div>'
        )
    html += '</div>'
    return html
```

The old code is lines 613–641 of `app.py`. The `old_string` for the Edit tool is the entire existing `render_steps` function from `def render_steps(current_step):` through `    return html` (the line just before `_current_step = (`).

- [ ] **Step 2: Verify the step indicator renders correctly**

Reload the app. At the initial state (no search yet), step 1 "Search" should be the active pill (blue glow, white text), and steps 2–4 should be dimmed (gray, 50% opacity). After searching and confirming a firm, step 1 should show a green checkmark with "Completed", and step 2 should become the active blue pill.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Redesign step indicator as pill cards with completed/active/future states"
```

---

### Task 5: Add elevated style to "Run Due Diligence" button

**Files:**
- Modify: `app.py:873-878` (run button block)

- [ ] **Step 1: Add an inline CSS block before the run button**

Insert a `st.markdown` call with a `<style>` tag immediately before the existing `run_button = st.button(...)` call at line 873. The new code replaces lines 873–878:

```python
    st.markdown("""
    <style>
    div[data-testid="stVerticalBlock"] .stButton > button[kind="primary"]:not([disabled]) {
        box-shadow: 0 0 10px rgba(34,113,194,0.25) !important;
    }
    </style>
    """, unsafe_allow_html=True)
    run_button = st.button(
        f"Run Due Diligence on {st.session_state.confirmed_firm.get('firm_name', '')}",
        type="primary",
        use_container_width=True,
        disabled=not openai_key,
    )
```

The old code is lines 873–878 of `app.py`. The `old_string` for the Edit tool is:

```
    run_button = st.button(
        f"Run Due Diligence on {st.session_state.confirmed_firm.get('firm_name', '')}",
        type="primary",
        use_container_width=True,
        disabled=not openai_key,
    )
```

- [ ] **Step 2: Verify the run button has a subtle glow when enabled**

Reload the app. Confirm a firm. If an API key is set, the "Run Due Diligence" button should have a subtle blue halo around it. If no API key is set (disabled), it should look muted with no glow.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Add elevated glow to Run Due Diligence button when enabled"
```

---

### Task 6: Final verification and push

- [ ] **Step 1: Reload the full app and walk through the flow**

1. Load the app — step 1 pill is blue, steps 2–4 are dimmed
2. Click an example chip — chip scales down briefly, search runs
3. Click "Use this firm" — step 1 turns green checkmark, step 2 becomes blue
4. See "Run Due Diligence" button with subtle blue glow
5. Click it — button scales down and darkens briefly

- [ ] **Step 2: Push all commits**

```bash
git push
```
