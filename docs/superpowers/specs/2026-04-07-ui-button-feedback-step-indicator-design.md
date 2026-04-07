# UI Improvements: Button Click Feedback & Step Indicator Redesign

**Date:** 2026-04-07
**Status:** Approved
**Scope:** CSS-only changes to `app.py` (Approach 1)

## Problem

1. Buttons have no visual feedback on click — users can't tell if their action registered.
2. The step indicator (Search → Confirm → Analyze → Review) doesn't differentiate between completed, active, and future steps. It's too small and easy to miss.

## Solution Overview

All changes are pure CSS plus a rewrite of the `render_steps()` Python function. No new dependencies, no JavaScript, no Streamlit component changes.

## Section 1: Button Click Feedback

### All buttons (`.stButton > button`)

| State | Property | Value |
|-------|----------|-------|
| Default | `background` | `#111111` |
| Default | `border` | `1px solid #2a2a2a` |
| Default | `transition` | `all 0.15s ease` |
| Hover | `background` | `#1a1a1a` |
| Hover | `border-color` | `#3a3a3a` |
| Hover | `color` | `#ffffff` |
| Active (`:active`) | `transform` | `scale(0.97)` |
| Active (`:active`) | `background` | `#0a0a0a` |
| Active (`:active`) | `border-color` | `#4a90d9` (accent blue flash) |

### Primary buttons (`button[kind="primary"]`)

Same `:active` scale effect. On click, gradient shifts from `linear-gradient(135deg, #1a3a6e, #2271c2)` to a slightly darker version (`#0e2144, #1a3a6e`).

### Chip buttons (example firms — `div[data-testid="column"] .stButton > button`)

Same subtle `scale(0.97)` + brief blue border flash on `:active`. Consistent with other buttons.

## Section 2: Step Indicator — Pill Cards

Replace `render_steps()` output from inline circle+text to a horizontal row of pill cards.

### Layout

- Container: `display: flex; gap: 8px;` — no connector lines
- Each pill: `border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px; flex: 1;`

### Three visual states

**Completed** (step < current_step):
- Background: `#0d2a1d`
- Border: `1px solid #2ecc71`
- Icon: checkmark (`✓`) in green, no numbered circle
- Text: `color: #2ecc71; font-weight: 700`
- Subtitle: `color: #1a5a32`; text says "Completed"

**Active** (step == current_step):
- Background: `#0d1f35`
- Border: `1.5px solid #4a90d9`
- Box-shadow: `0 0 10px rgba(74,144,217,0.3)` — subtle blue glow
- Circle: `background: #2271c2; color: white; font-weight: 800`; 22px round
- Name: `color: #ffffff; font-weight: 800`
- Subtitle: `color: #4a90d9`; shows step description (e.g., "Select from IAPD")

**Future** (step > current_step):
- Background: `#0a0a0a`
- Border: `1px solid #1a1a1a`
- Opacity: `0.5`
- Circle: `background: #1a1d2a; border: 1px solid #22253a; color: #3d4260`
- Name: `color: #3d4260; font-weight: 400`
- Subtitle: `color: #2a2d40`

### Step definitions (unchanged)

| Step | Name | Description |
|------|------|-------------|
| 1 | Search | Firm name or CRD |
| 2 | Confirm | Select from IAPD |
| 3 | Analyze | 8 agents run |
| 4 | Review | Download report |

### Current step logic (unchanged)

```python
_current_step = (
    4 if st.session_state.pipeline_done else
    3 if st.session_state.get("_pipeline_running") else
    2 if st.session_state.confirmed_firm else
    1
)
```

## Section 3: "Run Due Diligence" Button — Elevated Primary

When **enabled** (firm confirmed + API key present):
- Background: `linear-gradient(135deg, #1a3a6e, #2271c2)` — brighter than standard primary
- Border: `1px solid #2271c2`
- Box-shadow: `0 0 10px rgba(34,113,194,0.25)` — subtle persistent blue halo
- Same `:active` scale/darken feedback as all other buttons

When **disabled**: standard muted style (`#111111` background, `#2a2a2a` border), no glow.

## Files Changed

| File | Change |
|------|--------|
| `app.py` lines ~223–247 | Update button CSS (`:hover`, `:active` states) |
| `app.py` lines ~420–434 | Update chip button CSS (`:active` state) |
| `app.py` lines ~613–641 | Rewrite `render_steps()` function (pill cards) |
| `app.py` lines ~873–878 | Add elevated style to Run DD button |

## Out of Scope

- No JavaScript additions
- No new Streamlit components or dependencies
- No changes to app logic, session state, or data flow
- No animated pulses or ripple effects
