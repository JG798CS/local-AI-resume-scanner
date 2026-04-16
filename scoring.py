from __future__ import annotations

import math
import re

from llm import OllamaClient, OllamaError
from schemas import (
    DepartmentPreferences,
    DepartmentProfile,
    HardFilterResult,
    MatchEvidence,
    MissingRequirement,
    RequirementMatch,
    ResumeChunk,
    RiskFlag,
    ScoreResult,
    Scorecard,
    SoftScoreBreakdown,
    StructuredInterviewFeedback,
    StructuredJD,
    TransferableSkill,
)

EXPERIENCE_PATTERN = re.compile(r"(\d+)\s*\+?\s*(?:years|year|yrs|yr)")
TOOL_KEYWORDS = {"python", "fastapi", "sql", "postgresql", "ollama", "yaml", "pymupdf", "docker", "kubernetes"}
DOMAIN_KEYWORDS = {"recruiting", "resume", "screening", "hr", "hiring", "talent", "saas", "platform"}
TRANSFERABLE_SKILL_MAP = {
    "sql": ["postgresql", "mysql", "sqlite", "database"],
    "fastapi": ["flask", "django", "api", "backend"],
    "python": ["java", "golang", "javascript", "programming"],
    "ollama": ["llm", "rag", "inference"],
    "stakeholder management": ["cross-functional", "collaboration", "partner management"],
    "roadmap": ["planning", "prioritization", "strategy"],
}
POSITIVE_NOTE_SIGNALS = {
    "technical_depth": ["deep", "strong technically", "system design", "architecture", "debugging"],
    "communication": ["clear", "communicates well", "concise", "articulate", "explains well"],
    "domain_fit": ["domain fit", "understands recruiting", "hr tech", "relevant domain"],
    "learning_agility": ["learns quickly", "adaptable", "picks up fast", "growth mindset"],
    "ownership": ["ownership", "drives", "proactive", "takes initiative"],
    "collaboration": ["collaborative", "partnered", "cross-functional", "team player"],
    "stability_confidence": ["stable", "consistent", "reliable", "low risk"],
}
NEGATIVE_NOTE_SIGNALS = {
    "technical_depth": ["shallow", "weak technically"],
    "communication": ["unclear", "rambling"],
    "domain_fit": ["limited domain fit"],
    "learning_agility": ["slow to learn"],
    "ownership": ["passive"],
    "collaboration": ["difficult to work with"],
    "stability_confidence": ["flight risk", "unstable", "short tenure"],
}
RECOMMENDATION_SIGNALS = {
    "strong hire": 1.0,
    "hire": 0.85,
    "lean hire": 0.7,
    "mixed": 0.5,
    "hold": 0.35,
    "no hire": 0.1,
    "reject": 0.0,
}
CONCERN_MARKERS = ["concern", "risk", "gap", "weak", "unclear", "worry"]


def score_resume(
    jd_text: str,
    resume_text: str,
    chunks: list[ResumeChunk],
    profile: DepartmentProfile,
    department_preferences: DepartmentPreferences,
    interview_notes_text: str | None,
    candidate_stage: str,
    ollama: OllamaClient,
) -> ScoreResult:
    structured_jd = parse_structured_jd(jd_text)
    structured_interview_feedback = parse_interview_notes(interview_notes_text)
    hard_filter_results, hard_missing, hard_risks, years_found = evaluate_hard_filters(profile=profile, resume_text=resume_text)

    matched_requirements: list[RequirementMatch] = []
    missing_requirements = list(hard_missing)
    evidence: list[MatchEvidence] = []
    risk_flags = list(hard_risks)
    error_notes: list[str] = []

    try:
        jd_components = evaluate_jd_scoring(
            structured_jd=structured_jd,
            chunks=chunks,
            profile=profile,
            ollama=ollama,
        )
    except OllamaError as exc:
        jd_components = build_jd_fallback(chunks=chunks, profile=profile, structured_jd=structured_jd)
        error_notes.append(f"Semantic scoring unavailable: {exc}")

    matched_requirements.extend(jd_components["matches"])
    missing_requirements.extend(jd_components["missing"])
    evidence.extend(jd_components["evidence"])
    risk_flags.extend(jd_components["risks"])

    transferable_skills = detect_transferable_skills(
        resume_text=resume_text,
        missing_requirements=missing_requirements,
        policy=department_preferences.transferable_skill_policy,
    )
    transferable_skill_score = compute_transferable_skill_score(transferable_skills)
    if transferable_skills and transferable_skill_score >= 0.45:
        risk_flags.append(RiskFlag(category="transferable_strength", message="Candidate shows credible adjacent skills for some missing requirements."))

    department_preference_score = score_department_preferences(
        preferences=department_preferences,
        resume_text=resume_text,
    )

    interview_feedback_score = 0.0
    if candidate_stage == "post_interview":
        if interview_notes_text:
            interview_feedback_score = compute_interview_feedback_score(structured_interview_feedback)
        else:
            error_notes.append("Interview notes were not provided for post_interview scoring; interview feedback score defaulted to 0.0.")

    if profile.minimum_years_experience is not None:
        minimum_years = profile.minimum_years_experience
        if years_found >= minimum_years + 6:
            risk_flags.append(RiskFlag(category="overqualified", message="Candidate may be significantly above the target tenure level."))
        elif years_found < minimum_years:
            risk_flags.append(RiskFlag(category="underqualified", message="Observed tenure appears below the stated minimum."))

    jd_match_score = compute_jd_match_score(jd_components["breakdown"], profile)
    fit_score = compute_fit_score(
        candidate_stage=candidate_stage,
        jd_match_score=jd_match_score,
        department_preference_score=department_preference_score,
        interview_feedback_score=interview_feedback_score,
        transferable_skill_score=transferable_skill_score,
    )
    scorecard = Scorecard(
        candidate_stage=candidate_stage,
        jd_match_score=round(jd_match_score, 3),
        department_preference_score=round(department_preference_score, 3),
        interview_feedback_score=round(interview_feedback_score, 3),
        transferable_skill_score=round(transferable_skill_score, 3),
    )
    decision = choose_decision(
        fit_score=fit_score,
        hard_filter_results=hard_filter_results,
        candidate_stage=candidate_stage,
    )

    return ScoreResult(
        fit_score=fit_score,
        decision=decision,
        matched_requirements=matched_requirements,
        missing_requirements=dedupe_missing(missing_requirements),
        risk_flags=dedupe_risks(risk_flags),
        evidence=evidence,
        hard_filter_results=hard_filter_results,
        soft_score_breakdown=jd_components["breakdown"],
        structured_jd=structured_jd,
        error_notes=error_notes,
        scorecard=scorecard,
        structured_department_preferences=department_preferences,
        structured_interview_feedback=structured_interview_feedback,
        transferable_skills=transferable_skills,
    )


def parse_structured_jd(jd_text: str) -> StructuredJD:
    must_have: list[str] = []
    nice_to_have: list[str] = []
    responsibilities: list[str] = []
    section = "must_have"

    for raw_line in jd_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = line.lower().strip(":")
        if "nice to have" in normalized or "preferred" in normalized:
            section = "nice_to_have"
            continue
        if "responsibilit" in normalized:
            section = "responsibilities"
            continue
        if "requirement" in normalized or "must" in normalized or "qualification" in normalized:
            section = "must_have"
            continue

        bullet = clean_bullet(line)
        if not bullet:
            continue
        if any(word in bullet.lower() for word in ("nice to have", "bonus", "preferred")):
            nice_to_have.append(bullet)
        elif section == "nice_to_have":
            nice_to_have.append(bullet)
        elif section == "responsibilities":
            responsibilities.append(bullet)
        else:
            must_have.append(bullet)

    if not must_have and jd_text.strip():
        must_have = [item.strip() for item in re.split(r"[\n\.]+", jd_text) if item.strip()][:6]

    return StructuredJD(
        must_have=must_have[:8],
        nice_to_have=nice_to_have[:6],
        responsibilities=responsibilities[:8],
        domain_keywords=sorted(extract_keywords(jd_text, DOMAIN_KEYWORDS)),
        tool_keywords=sorted(extract_keywords(jd_text, TOOL_KEYWORDS)),
    )


def parse_interview_notes(notes_text: str | None) -> StructuredInterviewFeedback:
    if not notes_text:
        return StructuredInterviewFeedback()

    lower = notes_text.lower()
    signals: dict[str, float] = {}
    for field, keywords in POSITIVE_NOTE_SIGNALS.items():
        score = 0.0
        for keyword in keywords:
            if keyword in lower:
                score += 0.3
        for keyword in NEGATIVE_NOTE_SIGNALS.get(field, []):
            if keyword in lower:
                score -= 0.3
        signals[field] = max(0.0, min(score, 1.0))

    recommendation = 0.0
    for label, value in RECOMMENDATION_SIGNALS.items():
        if label in lower:
            recommendation = max(recommendation, value)

    concerns = [
        sentence.strip()
        for sentence in re.split(r"[\n\.]+", notes_text)
        if sentence.strip() and any(marker in sentence.lower() for marker in CONCERN_MARKERS)
    ]

    return StructuredInterviewFeedback(
        technical_depth=signals.get("technical_depth", 0.0),
        communication=signals.get("communication", 0.0),
        domain_fit=signals.get("domain_fit", 0.0),
        learning_agility=signals.get("learning_agility", 0.0),
        ownership=signals.get("ownership", 0.0),
        collaboration=signals.get("collaboration", 0.0),
        stability_confidence=signals.get("stability_confidence", 0.0),
        interviewer_recommendation=recommendation,
        concerns=concerns[:5],
        overall_sentiment=max(0.0, min((sum(signals.values()) / max(len(signals), 1) + recommendation) / 2, 1.0)),
    )


def evaluate_hard_filters(
    profile: DepartmentProfile,
    resume_text: str,
) -> tuple[list[HardFilterResult], list[MissingRequirement], list[RiskFlag], int]:
    haystack = resume_text.lower()
    results: list[HardFilterResult] = []
    missing: list[MissingRequirement] = []
    risks: list[RiskFlag] = []

    for skill in profile.must_have_skills:
        passed = skill.lower() in haystack
        results.append(HardFilterResult(name=f"required_skill:{skill}", passed=passed, details="Found in resume text." if passed else "Required skill not found in resume text."))
        if not passed:
            missing.append(MissingRequirement(requirement=skill, reason=f"Must-have skill '{skill}' was not found in the resume."))
            risks.append(RiskFlag(category="missing_must_have", message=f"Missing required skill: {skill}."))

    years_found = max(extract_years(resume_text), default=0)
    minimum_years = profile.minimum_years_experience
    if minimum_years is not None:
        passed = years_found >= minimum_years
        details = f"Detected {years_found} years; minimum is {minimum_years}."
        results.append(HardFilterResult(name="minimum_years_experience", passed=passed, details=details))
        if not passed:
            missing.append(MissingRequirement(requirement=f"{minimum_years}+ years experience", reason=f"Resume suggests about {years_found} years of experience."))
            risks.append(RiskFlag(category="unclear_tenure", message=details))

    for language in profile.required_languages:
        passed = language.lower() in haystack
        results.append(HardFilterResult(name=f"language:{language}", passed=passed, details="Found in resume text." if passed else "Language requirement not found in resume text."))
        if not passed:
            missing.append(MissingRequirement(requirement=language, reason=f"Required language '{language}' was not found in the resume."))
            risks.append(RiskFlag(category="missing_must_have", message=f"Missing required language: {language}."))

    for location in profile.location_constraints:
        passed = location.lower() in haystack
        results.append(HardFilterResult(name=f"location:{location}", passed=passed, details=f"Location requirement: {location}."))
        if not passed:
            risks.append(RiskFlag(category="missing_must_have", message=f"Location alignment is unclear for {location}."))

    if profile.work_authorization:
        passed = profile.work_authorization.lower() in haystack
        results.append(HardFilterResult(name="work_authorization", passed=passed, details=f"Work authorization requirement: {profile.work_authorization}."))
        if not passed:
            risks.append(RiskFlag(category="missing_must_have", message=f"Work authorization not confirmed for {profile.work_authorization}."))

    for education in profile.required_education:
        passed = education.lower() in haystack
        results.append(HardFilterResult(name=f"education:{education}", passed=passed, details=f"Education requirement: {education}."))
        if not passed:
            missing.append(MissingRequirement(requirement=education, reason=f"Required education '{education}' was not found in the resume."))
            risks.append(RiskFlag(category="missing_must_have", message=f"Required education missing: {education}."))

    return results, missing, risks, years_found


def evaluate_jd_scoring(
    structured_jd: StructuredJD,
    chunks: list[ResumeChunk],
    profile: DepartmentProfile,
    ollama: OllamaClient,
) -> dict[str, object]:
    resume_texts = [chunk.content for chunk in chunks]
    chunk_embeddings = ollama.embed_texts(resume_texts)

    matches: list[RequirementMatch] = []
    missing: list[MissingRequirement] = []
    evidence: list[MatchEvidence] = []
    risks: list[RiskFlag] = []

    must_have_items = list(dict.fromkeys(structured_jd.must_have or profile.must_have_skills))
    nice_to_have_items = list(dict.fromkeys(structured_jd.nice_to_have + profile.nice_to_have_skills))

    must_have_score = score_bucket(
        items=must_have_items,
        label="must_have",
        chunks=chunks,
        chunk_embeddings=chunk_embeddings,
        ollama=ollama,
        matches=matches,
        missing=missing,
        evidence=evidence,
    )
    nice_to_have_score = score_bucket(
        items=nice_to_have_items,
        label="nice_to_have",
        chunks=chunks,
        chunk_embeddings=chunk_embeddings,
        ollama=ollama,
        matches=matches,
        missing=missing,
        evidence=evidence,
    )

    seniority = lexical_alignment(profile.seniority_keywords, chunks)
    domain = lexical_alignment(list(set(profile.preferred_domains + structured_jd.domain_keywords)), chunks)
    tools = lexical_alignment(list(set(profile.tool_keywords + structured_jd.tool_keywords)), chunks)

    if must_have_score < 0.55 and must_have_items:
        risks.append(RiskFlag(category="missing_must_have", message="Core job requirements have weak semantic support in the resume."))
    if domain < 0.35 and (profile.preferred_domains or structured_jd.domain_keywords):
        risks.append(RiskFlag(category="weak_domain_match", message="Relevant domain experience appears limited or unclear."))
    if tools < 0.4 and (profile.tool_keywords or structured_jd.tool_keywords):
        risks.append(RiskFlag(category="weak_tool_match", message="Tool stack overlap looks weaker than expected."))

    breakdown = SoftScoreBreakdown(
        must_have_semantic=round(must_have_score, 3),
        nice_to_have_semantic=round(nice_to_have_score, 3),
        seniority_alignment=round(seniority, 3),
        domain_alignment=round(domain, 3),
        tool_stack_alignment=round(tools, 3),
        semantic_scoring_available=True,
    )
    return {
        "matches": matches,
        "missing": missing,
        "evidence": evidence,
        "risks": risks,
        "breakdown": breakdown,
    }


def build_jd_fallback(
    chunks: list[ResumeChunk],
    profile: DepartmentProfile,
    structured_jd: StructuredJD,
) -> dict[str, object]:
    domain = lexical_alignment(list(set(profile.preferred_domains + structured_jd.domain_keywords)), chunks)
    tools = lexical_alignment(list(set(profile.tool_keywords + structured_jd.tool_keywords)), chunks)
    seniority = lexical_alignment(profile.seniority_keywords, chunks)
    return {
        "matches": [],
        "missing": [
            MissingRequirement(
                requirement=item,
                reason="Semantic matching was unavailable, so this requirement could not be scored.",
            )
            for item in (structured_jd.must_have or profile.must_have_skills)[:3]
        ],
        "evidence": [],
        "risks": [RiskFlag(category="missing_must_have", message="Semantic scoring was unavailable; must-have coverage could not be confirmed.")],
        "breakdown": SoftScoreBreakdown(
            must_have_semantic=0.0,
            nice_to_have_semantic=0.0,
            seniority_alignment=round(seniority, 3),
            domain_alignment=round(domain, 3),
            tool_stack_alignment=round(tools, 3),
            semantic_scoring_available=False,
        ),
    }


def score_bucket(
    items: list[str],
    label: str,
    chunks: list[ResumeChunk],
    chunk_embeddings: list,
    ollama: OllamaClient,
    matches: list[RequirementMatch],
    missing: list[MissingRequirement],
    evidence: list[MatchEvidence],
) -> float:
    if not items:
        return 1.0
    item_embeddings = ollama.embed_texts(items)
    scores: list[float] = []
    for item, item_embedding in zip(items, item_embeddings):
        best_score = -1.0
        best_chunk = chunks[0]
        for chunk, chunk_embedding in zip(chunks, chunk_embeddings):
            score = cosine_similarity(item_embedding.vector, chunk_embedding.vector)
            if score > best_score:
                best_score = score
                best_chunk = chunk
        normalized = max(best_score, 0.0)
        scores.append(normalized)
        snippet = quote_snippet(best_chunk.content)
        if normalized >= 0.55:
            matches.append(RequirementMatch(requirement=item, score=round(normalized, 3), evidence=f"{best_chunk.section_label}: {snippet}"))
            evidence.append(MatchEvidence(matched_jd_item=item, matched_resume_snippet=snippet, section_label=best_chunk.section_label, similarity_score=round(normalized, 3)))
        else:
            reason_prefix = "Must-have" if label == "must_have" else "Nice-to-have"
            missing.append(MissingRequirement(requirement=item, reason=f"{reason_prefix} item had only weak resume evidence in section '{best_chunk.section_label}' ({normalized:.2f})."))
    return sum(scores) / len(scores)


def score_department_preferences(preferences: DepartmentPreferences, resume_text: str) -> float:
    resume_lower = resume_text.lower()
    positive_sets = [
        preferences.preferred_backgrounds,
        preferences.preferred_company_types,
        preferences.preferred_company_stage,
        preferences.preferred_traits,
        preferences.preferred_domains,
        preferences.preferred_working_style,
    ]
    total_terms = sum(len(items) for items in positive_sets)
    positive_hits = sum(1 for items in positive_sets for item in items if item.lower() in resume_lower)
    dislike_hits = sum(1 for item in preferences.disliked_signals if item.lower() in resume_lower)
    if total_terms == 0 and not preferences.disliked_signals:
        return 0.5
    positive_score = positive_hits / total_terms if total_terms else 0.5
    penalty = min(dislike_hits * 0.2, 0.6)
    weighted_bonus = (
        sum(preferences.preference_weights.values()) / len(preferences.preference_weights)
        if preferences.preference_weights
        else 0.0
    )
    return max(0.0, min(1.0, 0.5 + (positive_score * 0.5) + weighted_bonus * 0.05 - penalty))


def compute_interview_feedback_score(feedback: StructuredInterviewFeedback) -> float:
    metrics = [
        feedback.technical_depth,
        feedback.communication,
        feedback.domain_fit,
        feedback.learning_agility,
        feedback.ownership,
        feedback.collaboration,
        feedback.stability_confidence,
        feedback.interviewer_recommendation,
    ]
    base = sum(metrics) / len(metrics)
    penalty = min(len(feedback.concerns) * 0.05, 0.25)
    return max(0.0, min(1.0, base - penalty))


def detect_transferable_skills(
    resume_text: str,
    missing_requirements: list[MissingRequirement],
    policy: str = "balanced",
) -> list[TransferableSkill]:
    resume_lower = resume_text.lower()
    found_resume_terms = extract_candidate_terms(resume_lower)
    transferable: list[TransferableSkill] = []
    for item in missing_requirements:
        jd_skill = item.requirement.lower()
        if jd_skill in found_resume_terms:
            transferable.append(
                TransferableSkill(
                    jd_skill=item.requirement,
                    candidate_skill=jd_skill,
                    relationship="direct_match",
                    score=1.0,
                    reason=f"Resume text still includes {item.requirement}.",
                )
            )
            continue
        related = TRANSFERABLE_SKILL_MAP.get(jd_skill, [])
        candidate_skill = next((term for term in related if term in found_resume_terms), None)
        if candidate_skill:
            relationship = "similar_skill" if candidate_skill in {"postgresql", "flask", "django", "mysql", "sqlite"} else "transferable_skill"
            base_score = 0.7 if relationship == "similar_skill" else 0.5
            score = min(base_score + (0.1 if policy == "aggressive" else 0.0), 1.0)
            transferable.append(
                TransferableSkill(
                    jd_skill=item.requirement,
                    candidate_skill=candidate_skill,
                    relationship=relationship,
                    score=score,
                    reason=f"Resume shows {candidate_skill}, which is relevant to {item.requirement}.",
                )
            )
        else:
            weak_candidate = next((term for term in found_resume_terms if any(token in term for token in jd_skill.split())), "")
            relationship = "weak_relation" if weak_candidate else "no_relation"
            score = 0.2 if weak_candidate else 0.0
            transferable.append(
                TransferableSkill(
                    jd_skill=item.requirement,
                    candidate_skill=weak_candidate,
                    relationship=relationship,
                    score=score,
                    reason=(
                        f"Resume shows loosely related term {weak_candidate}."
                        if weak_candidate
                        else f"No meaningful relation was found for {item.requirement}."
                    ),
                )
            )
    return transferable


def compute_transferable_skill_score(transferable_skills: list[TransferableSkill]) -> float:
    if not transferable_skills:
        return 0.0
    return sum(item.score for item in transferable_skills) / len(transferable_skills)


def compute_jd_match_score(soft_score_breakdown: SoftScoreBreakdown, profile: DepartmentProfile) -> float:
    weights = profile.scoring_weights
    return max(
        0.0,
        min(
            1.0,
            (
                soft_score_breakdown.must_have_semantic * weights.must_have_semantic
                + soft_score_breakdown.nice_to_have_semantic * weights.nice_to_have_semantic
                + soft_score_breakdown.seniority_alignment * weights.seniority_alignment
                + soft_score_breakdown.domain_alignment * weights.domain_alignment
                + soft_score_breakdown.tool_stack_alignment * weights.tool_stack_alignment
            ),
        ),
    )


def compute_fit_score(
    candidate_stage: str,
    jd_match_score: float,
    department_preference_score: float,
    interview_feedback_score: float,
    transferable_skill_score: float,
) -> int:
    if candidate_stage == "post_interview":
        weighted = (
            jd_match_score * 0.35
            + department_preference_score * 0.20
            + interview_feedback_score * 0.30
            + transferable_skill_score * 0.15
        )
    else:
        weighted = (
            jd_match_score * 0.60
            + department_preference_score * 0.25
            + transferable_skill_score * 0.15
        )
    return max(0, min(100, round(weighted * 100)))


def choose_decision(fit_score: int, hard_filter_results: list[HardFilterResult], candidate_stage: str) -> str:
    hard_failures = sum(1 for item in hard_filter_results if not item.passed)
    if candidate_stage == "post_interview":
        if hard_failures >= 2 or fit_score < 35:
            return "reject"
        if hard_failures >= 1 or fit_score < 55:
            return "hold"
        if fit_score < 75:
            return "proceed_to_next_round"
        return "strong_hire"

    if hard_failures >= 2 or fit_score < 35:
        return "no"
    if hard_failures >= 1 or fit_score < 55:
        return "maybe"
    if fit_score < 75:
        return "yes"
    return "strong_yes"


def extract_years(text: str) -> list[int]:
    return [int(match.group(1)) for match in EXPERIENCE_PATTERN.finditer(text.lower())]


def lexical_alignment(keywords: list[str], chunks: list[ResumeChunk]) -> float:
    if not keywords:
        return 1.0
    joined = "\n".join(chunk.content.lower() for chunk in chunks)
    hits = sum(1 for keyword in keywords if keyword.lower() in joined)
    return hits / len(keywords)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def clean_bullet(text: str) -> str:
    stripped = text.strip().lstrip("-* ").strip()
    return stripped.replace("\u2022", "").strip()


def extract_keywords(text: str, vocabulary: set[str]) -> set[str]:
    lower = text.lower()
    return {keyword for keyword in vocabulary if keyword in lower}


def extract_candidate_terms(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z\+\#][a-zA-Z0-9_\-\+\# ]+", text))
    vocabulary = set().union(*TRANSFERABLE_SKILL_MAP.values())
    return {term for term in vocabulary if term in text} | {token.strip() for token in tokens if len(token.strip()) > 2}


def dedupe_missing(items: list[MissingRequirement]) -> list[MissingRequirement]:
    seen: set[str] = set()
    output: list[MissingRequirement] = []
    for item in items:
        key = f"{item.requirement}|{item.reason}"
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def dedupe_risks(items: list[RiskFlag]) -> list[RiskFlag]:
    seen: set[str] = set()
    output: list[RiskFlag] = []
    for item in items:
        key = f"{item.category}|{item.message}"
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def quote_snippet(text: str, limit: int = 220) -> str:
    snippet = " ".join(text.split())
    if len(snippet) > limit:
        snippet = snippet[: limit - 3].rstrip() + "..."
    return f"\"{snippet}\""
