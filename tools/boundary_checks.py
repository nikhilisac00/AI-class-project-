"""
Boundary sensors — validate each agent's output before the next agent
consumes it.

Returns a list of error strings. Empty list means the output passed.
Callers retry the agent once on failure; if errors persist they log and
continue rather than halt the pipeline.
"""

from tools.schemas import validate_analysis

_VALID_RISK_TIERS    = {"HIGH", "MEDIUM", "LOW"}
_VALID_NEWS_RISK     = {"HIGH", "MEDIUM", "LOW", "CLEAN", "UNKNOWN"}
_VALID_RECS          = {"PROCEED", "REQUEST MORE INFO", "PASS"}
_VALID_VERDICTS      = {"CONFIRMED", "UPGRADED", "DOWNGRADED", "INCONCLUSIVE"}


def check_analysis(analysis: dict) -> list[str]:
    """Delegate to the existing schema validator."""
    return validate_analysis(analysis) or []


def check_news_report(report: dict) -> list[str]:
    if not isinstance(report, dict):
        return ["news_report is not a dict"]
    errors = []
    risk = report.get("overall_news_risk", "")
    if risk not in _VALID_NEWS_RISK:
        errors.append(f"overall_news_risk={risk!r} not in {_VALID_NEWS_RISK}")
    if not isinstance(report.get("news_flags"), list):
        errors.append("news_flags missing or not a list")
    return errors


def check_risk_report(report: dict) -> list[str]:
    if not isinstance(report, dict):
        return ["risk_report is not a dict"]
    errors = []
    tier = report.get("overall_risk_tier", "")
    if tier not in _VALID_RISK_TIERS:
        errors.append(f"overall_risk_tier={tier!r} not in {_VALID_RISK_TIERS}")
    if not isinstance(report.get("flags"), list):
        errors.append("flags missing or not a list")
    return errors


def check_scorecard(scorecard: dict) -> list[str]:
    if not isinstance(scorecard, dict):
        return ["scorecard is not a dict"]
    errors = []
    rec = scorecard.get("recommendation", "")
    if rec not in _VALID_RECS:
        errors.append(f"recommendation={rec!r} not in {_VALID_RECS}")
    if scorecard.get("overall_score") is None:
        errors.append("overall_score missing")
    return errors


def check_director_review(review: dict) -> list[str]:
    if not isinstance(review, dict):
        return ["director_review is not a dict"]
    verdict = review.get("verdict", "")
    if verdict not in _VALID_VERDICTS:
        return [f"verdict={verdict!r} not in {_VALID_VERDICTS}"]
    return []
