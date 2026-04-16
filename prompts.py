from __future__ import annotations

from schemas import ScoreResult


def build_summary_prompt(jd_text: str, score_result: ScoreResult) -> str:
    return f"""
You are a local resume scanner. Produce plain text only.

Rules:
- Keep the response concise.
- Include a final summary, missing requirement explanation, and risk flags.
- Do not mention any cloud services.

Job Description:
{jd_text}

Fit Score: {score_result.fit_score}
Decision: {score_result.decision}
Scorecard: {score_result.scorecard.model_dump()}
Matched Requirements: {[item.requirement for item in score_result.matched_requirements]}
Missing Requirements: {[item.requirement for item in score_result.missing_requirements]}
Risk Flags: {[f"{item.category}: {item.message}" for item in score_result.risk_flags]}
""".strip()


def build_fallback_summary(score_result: ScoreResult) -> str:
    matched = score_result.matched_requirements[:2]
    missing = score_result.missing_requirements[:2]
    risks = score_result.risk_flags[:2]

    parts = [f"Decision: {score_result.decision}. Fit score: {score_result.fit_score}."]
    if matched:
        parts.append("Matched: " + "; ".join(item.requirement for item in matched) + ".")
    if missing:
        parts.append("Missing: " + "; ".join(item.requirement for item in missing) + ".")
    if risks:
        parts.append("Risks: " + "; ".join(item.message for item in risks) + ".")
    return " ".join(parts)
