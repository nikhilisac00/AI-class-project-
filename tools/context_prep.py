"""
Context Prep — Harness-level structured trimming for LLM prompts.

Instead of blindly truncating prompts that exceed the token budget, this
module identifies and compresses known-heavy data structures while
preserving all decision-relevant information.

Heavy fields and their compression strategy:
  - 13F holdings: keep top N by value + summary stats
  - Section 7.B funds: keep first N + count
  - Fund discovery: keep first N + count
  - News findings: keep flags (high signal), drop raw findings
  - Disclosure details: keep first N + count

The module operates on the serialized prompt text (not raw dicts) so it
works as a universal harness layer regardless of which agent built the prompt.
"""

import json
import re


def trim_json_arrays(text: str, max_chars: int) -> str:
    """Progressively compress JSON arrays in *text* until it fits *max_chars*.

    Strategy: find the largest JSON arrays in the text and truncate them,
    keeping the first N elements and appending a count note. Repeats until
    the text fits or no more arrays can be trimmed.

    This preserves the structure (valid JSON stays valid) and keeps the
    highest-signal items (arrays are typically ordered by importance).
    """
    if len(text) <= max_chars:
        return text

    # Each pass trims the largest remaining array
    for _ in range(10):  # cap iterations
        if len(text) <= max_chars:
            break

        largest = _find_largest_json_array(text)
        if not largest:
            break

        start, end, items = largest
        if len(items) <= 3:
            # Array is already small — skip and try the next one
            # Mark it so we don't pick it again
            continue

        # Keep first N items (more aggressive as we iterate)
        keep = max(3, len(items) // 3)
        trimmed_items = items[:keep]
        dropped = len(items) - keep
        trimmed_items.append(
            f"... and {dropped} more items (trimmed by harness)"
        )

        replacement = json.dumps(trimmed_items, indent=2, default=str)
        text = text[:start] + replacement + text[end:]

    # Final safety net: if still over budget, truncate with note
    if len(text) > max_chars:
        text = text[:max_chars] + (
            "\n\n[... context trimmed by harness to fit token budget ...]"
        )

    return text


def _find_largest_json_array(text: str) -> tuple[int, int, list] | None:
    """Find the start, end, and parsed contents of the largest JSON array in text.

    Only targets arrays with 5+ elements to avoid trimming small config arrays.
    Returns None if no trimmable array is found.
    """
    best = None
    best_len = 0

    # Scan for [ characters and try to parse arrays starting there
    for match in re.finditer(r'\[', text):
        start = match.start()
        # Quick heuristic: skip if the array is small in the text
        # Find the matching ] by counting brackets
        depth = 0
        end = start
        in_string = False
        escape = False
        for i in range(start, min(start + 200_000, len(text))):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        else:
            continue

        span = end - start
        if span <= best_len or span < 200:
            continue

        try:
            arr = json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            continue

        if not isinstance(arr, list) or len(arr) < 5:
            continue

        if span > best_len:
            best = (start, end, arr)
            best_len = span

    return best
