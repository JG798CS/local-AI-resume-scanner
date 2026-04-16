from __future__ import annotations

import csv
import io
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from chunking import chunk_resume_text
from llm import OllamaClient, OllamaError
from parser import PdfParseError, extract_pdf_text
from prompts import build_fallback_summary, build_summary_prompt
from rules import (
    RuleLoadError,
    load_department_preferences,
    load_department_rules,
    load_department_rules_file,
    resolve_department_profile,
)
from schemas import (
    AggregatedInterviewFeedback,
    BatchErrorItem,
    BatchExportOutputs,
    BatchScanResponse,
    Candidate,
    CandidateComparisonItem,
    CandidateComparisonRequest,
    CandidateComparisonResponse,
    CandidateDetail,
    CandidateEvaluationRequest,
    CandidateFeedbackResponse,
    CandidateListResponse,
    ConflictAnalysis,
    DepartmentProfile,
    ExplainabilityBlock,
    ExplainabilityEvidenceSource,
    ExplainabilityItem,
    InterviewFeedback,
    InterviewFeedbackCreateRequest,
    Job,
    JobCreateRequest,
    JobDetail,
    RankedBatchResult,
    RecruiterSummary,
    ScanResponse,
    ScoreResult,
    ShortlistEntry,
    ShortlistPriorityRequest,
    ShortlistResponse,
    StageEvaluation,
    StageMoveRequest,
)
from scoring import parse_interview_notes, score_resume
from store import store

app = FastAPI(title="Local Resume Scanner")
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/ui/assets", StaticFiles(directory=FRONTEND_DIR), name="ui-assets")

STAGE_ORDER = {"initial_screen": 0, "first_round": 1, "second_round": 2}
SHORTLIST_DECISION_ORDER = {
    "strong_hire": 0,
    "proceed_to_second_round": 1,
    "strong_yes": 2,
    "yes": 3,
    "hold": 4,
    "maybe": 5,
    "reject": 6,
    "no": 7,
}


@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
async def ui_index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/ui/{path:path}", include_in_schema=False)
async def ui_routes(path: str) -> FileResponse:
    asset_path = FRONTEND_DIR / path
    if asset_path.exists() and asset_path.is_file():
        return FileResponse(asset_path)
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/scan", response_model=ScanResponse)
async def scan_resume(
    resume: UploadFile = File(...),
    jd_text: str = Form(...),
    department_profile: str | None = Form(default=None),
    department_rules_yaml: str | None = Form(default=None),
    department_preference_input: str | None = Form(default=None),
    department_preference_yaml: str | None = Form(default=None),
    interview_notes_text: str | None = Form(default=None),
    candidate_stage: str = Form(default="pre_interview"),
) -> ScanResponse:
    validate_request_inputs([resume], jd_text)

    try:
        profile = load_profile(department_profile=department_profile, department_rules_yaml=department_rules_yaml)
        department_preferences = load_department_preferences(department_preference_input or department_preference_yaml)
        candidate_stage = validate_candidate_stage(candidate_stage)
        ollama = OllamaClient()
        ranked_result, error = await process_upload(
            upload=resume,
            jd_text=jd_text,
            profile=profile,
            department_preferences=department_preferences,
            interview_notes_text=interview_notes_text,
            candidate_stage=candidate_stage,
            ollama=ollama,
            candidate_id="candidate_1",
        )
        if error is not None or ranked_result is None:
            raise HTTPException(status_code=400, detail=error.error if error else "Resume processing failed.")
        return scan_response_from_ranked(ranked_result)
    except (PdfParseError, RuleLoadError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Unexpected scan failure.") from exc


@app.post("/scan-batch", response_model=BatchScanResponse)
async def scan_batch(
    resumes: list[UploadFile] = File(...),
    jd_text: str = Form(...),
    department_profile: str | None = Form(default=None),
    department_rules_yaml: str | None = Form(default=None),
    department_preference_input: str | None = Form(default=None),
    department_preference_yaml: str | None = Form(default=None),
    interview_notes_text: str | None = Form(default=None),
    candidate_stage: str = Form(default="pre_interview"),
    export_formats: str | None = Form(default=None),
) -> BatchScanResponse:
    validate_request_inputs(resumes, jd_text)

    try:
        profile = load_profile(department_profile=department_profile, department_rules_yaml=department_rules_yaml)
        department_preferences = load_department_preferences(department_preference_input or department_preference_yaml)
        candidate_stage = validate_candidate_stage(candidate_stage)
        ollama = OllamaClient()
        ranked_results: list[RankedBatchResult] = []
        errors: list[BatchErrorItem] = []

        for index, resume in enumerate(resumes, start=1):
            ranked_result, error = await process_upload(
                upload=resume,
                jd_text=jd_text,
                profile=profile,
                department_preferences=department_preferences,
                interview_notes_text=interview_notes_text,
                candidate_stage=candidate_stage,
                ollama=ollama,
                candidate_id=f"candidate_{index}",
            )
            if ranked_result is not None:
                ranked_results.append(ranked_result)
            if error is not None:
                errors.append(error)

        ranked_results.sort(key=ranking_key)
        shortlist = build_shortlist(ranked_results)
        recruiter_summary = build_recruiter_summary(ranked_results)
        export_output = build_export_outputs(
            ranked_results=ranked_results,
            recruiter_summary=recruiter_summary,
            error_summary=errors,
            export_formats=export_formats,
        )
        return BatchScanResponse(
            total_resumes=len(resumes),
            ranked_results=ranked_results,
            shortlist=shortlist,
            error_summary=errors,
            recruiter_summary=recruiter_summary,
            export_outputs=export_output,
        )
    except RuleLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Unexpected batch scan failure.") from exc


@app.post("/jobs", response_model=Job)
async def create_job(request: JobCreateRequest) -> Job:
    if not request.jd_text.strip():
        raise HTTPException(status_code=400, detail="jd_text is required.")

    sanitized_rules_yaml = normalize_rules_override(request.department_rules_yaml)
    profile_name = resolve_optional_department_profile(
        department_profile=request.department_profile,
        department_rules_yaml=sanitized_rules_yaml,
    )

    preference_input = normalize_preference_input(request.default_department_preference_input)
    if preference_input is not None:
        load_department_preferences(preference_input)

    job = Job(
        job_id=generate_id("job"),
        title=request.title.strip(),
        department=request.department.strip(),
        jd_text=request.jd_text,
        department_profile=profile_name,
        department_rules_yaml=sanitized_rules_yaml,
        default_department_preference_input=preference_input,
        created_at=now_iso(),
        status=request.status or "open",
    )
    store.add_job(job)
    return job


@app.get("/jobs", response_model=list[JobDetail])
async def list_jobs() -> list[JobDetail]:
    return [build_job_detail(job) for job in store.list_jobs()]


@app.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str) -> JobDetail:
    return build_job_detail(require_job(job_id))


@app.post("/jobs/{job_id}/candidates", response_model=CandidateDetail)
async def add_candidate_to_job(
    job_id: str,
    resume: UploadFile = File(...),
    name: str | None = Form(default=None),
    source: str | None = Form(default=None),
    current_stage: str = Form(default="initial_screen"),
) -> CandidateDetail:
    job = require_job(job_id)
    stage = validate_workflow_stage(current_stage)
    filename = resume.filename or "candidate.pdf"
    if resume.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Resume must be a PDF upload.")

    try:
        resume_bytes = await resume.read()
        resume_text = extract_pdf_text(resume_bytes)
    except PdfParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    candidate = Candidate(
        candidate_id=generate_id("candidate"),
        job_id=job_id,
        name=(name or filename).strip(),
        filename=filename,
        current_stage=stage,
        source=source.strip() if source else None,
        created_at=now_iso(),
        shortlist_status=False,
    )
    store.add_candidate(candidate)
    store.save_candidate_document(candidate.candidate_id, filename=filename, resume_bytes=resume_bytes, resume_text=resume_text)
    try:
        evaluation = evaluate_candidate_for_stage(
            job=job,
            candidate=candidate,
            stage=stage,
            jd_text=job.jd_text,
            department_preference_input=job.default_department_preference_input,
            interview_notes_text=None,
        )
        store.add_stage_evaluation(evaluation)
    except Exception:
        pass
    return build_candidate_detail(candidate)


@app.get("/jobs/{job_id}/candidates", response_model=CandidateListResponse)
async def list_job_candidates(job_id: str) -> CandidateListResponse:
    require_job(job_id)
    return CandidateListResponse(items=store.list_candidates(job_id))


@app.get("/jobs/{job_id}/candidates/{candidate_id}", response_model=CandidateDetail)
async def get_candidate(job_id: str, candidate_id: str) -> CandidateDetail:
    return build_candidate_detail(require_candidate(job_id, candidate_id))


@app.post("/jobs/{job_id}/candidates/{candidate_id}/evaluate", response_model=StageEvaluation)
async def evaluate_candidate(
    job_id: str,
    candidate_id: str,
    request: CandidateEvaluationRequest,
) -> StageEvaluation:
    job = require_job(job_id)
    candidate = require_candidate(job_id, candidate_id)
    stage = validate_workflow_stage(request.stage or candidate.current_stage)
    evaluation = evaluate_candidate_for_stage(
        job=job,
        candidate=candidate,
        stage=stage,
        jd_text=request.jd_text or job.jd_text,
        department_preference_input=request.department_preference_input or job.default_department_preference_input,
        interview_notes_text=request.interview_notes_text,
    )
    store.add_stage_evaluation(evaluation)
    if candidate.current_stage != stage:
        store.update_candidate(candidate.model_copy(update={"current_stage": stage}))
    return evaluation


@app.post("/jobs/{job_id}/candidates/{candidate_id}/stage", response_model=CandidateDetail)
async def move_candidate_stage(
    job_id: str,
    candidate_id: str,
    request: StageMoveRequest,
) -> CandidateDetail:
    job = require_job(job_id)
    candidate = require_candidate(job_id, candidate_id)
    target_stage = validate_workflow_stage(request.target_stage)
    updated = candidate.model_copy(update={"current_stage": target_stage})
    store.update_candidate(updated)
    evaluation = evaluate_candidate_for_stage(
        job=job,
        candidate=updated,
        stage=target_stage,
        jd_text=job.jd_text,
        department_preference_input=job.default_department_preference_input,
        interview_notes_text=None,
    )
    store.add_stage_evaluation(evaluation)
    return build_candidate_detail(updated)


@app.post("/jobs/{job_id}/candidates/{candidate_id}/feedback", response_model=InterviewFeedback)
async def submit_candidate_feedback(
    job_id: str,
    candidate_id: str,
    request: InterviewFeedbackCreateRequest,
) -> InterviewFeedback:
    require_job(job_id)
    require_candidate(job_id, candidate_id)
    stage = validate_feedback_stage(request.stage)
    structured_feedback = parse_interview_notes(request.raw_notes)
    feedback = InterviewFeedback(
        feedback_id=generate_id("feedback"),
        candidate_id=candidate_id,
        stage=stage,
        interviewer_name=request.interviewer_name.strip(),
        submitted_at=now_iso(),
        raw_notes=request.raw_notes,
        structured_feedback=structured_feedback,
        recommendation=normalize_feedback_recommendation(request.recommendation, request.raw_notes),
        concerns=structured_feedback.concerns,
    )
    store.add_feedback(feedback)
    return feedback


@app.get("/jobs/{job_id}/candidates/{candidate_id}/feedback", response_model=CandidateFeedbackResponse)
async def list_candidate_feedback(job_id: str, candidate_id: str) -> CandidateFeedbackResponse:
    require_job(job_id)
    require_candidate(job_id, candidate_id)
    items = store.list_feedback(candidate_id)
    grouped = store.list_feedback_by_stage(candidate_id)
    aggregates = [aggregate_feedback(stage, stage_items) for stage, stage_items in grouped.items()]
    return CandidateFeedbackResponse(items=items, aggregates=aggregates)


@app.get("/jobs/{job_id}/shortlist", response_model=ShortlistResponse)
async def get_shortlist(job_id: str) -> ShortlistResponse:
    require_job(job_id)
    return ShortlistResponse(items=sorted_shortlist(job_id))


@app.post("/jobs/{job_id}/shortlist/generate", response_model=ShortlistResponse)
async def generate_shortlist(job_id: str) -> ShortlistResponse:
    require_job(job_id)
    generated: list[ShortlistEntry] = []
    for candidate in store.list_candidates(job_id):
        latest = latest_evaluation(candidate.candidate_id)
        if latest is None:
            continue
        entry = build_shortlist_entry(candidate, latest, latest.conflict_analysis)
        generated.append(store.upsert_shortlist_entry(entry))
        store.update_candidate(candidate.model_copy(update={"shortlist_status": True}))
    return ShortlistResponse(items=sort_shortlist_entries(generated))


@app.post("/jobs/{job_id}/shortlist/{candidate_id}", response_model=ShortlistResponse)
async def upsert_shortlist_entry_endpoint(
    job_id: str,
    candidate_id: str,
    request: ShortlistPriorityRequest,
) -> ShortlistResponse:
    candidate = require_candidate(job_id, candidate_id)
    latest = latest_evaluation(candidate.candidate_id)
    if latest is None:
        raise HTTPException(status_code=400, detail="Candidate must be evaluated before being added to the shortlist.")
    existing = store.get_shortlist_entry(job_id, candidate_id)
    entry = build_shortlist_entry(candidate, latest, latest.conflict_analysis)
    if existing and request.shortlist_priority is None:
        entry = entry.model_copy(update={"shortlist_priority": existing.shortlist_priority})
    else:
        entry = entry.model_copy(update={"shortlist_priority": request.shortlist_priority})
    store.upsert_shortlist_entry(entry)
    store.update_candidate(candidate.model_copy(update={"shortlist_status": True}))
    return ShortlistResponse(items=sorted_shortlist(job_id))


@app.delete("/jobs/{job_id}/shortlist/{candidate_id}", response_model=ShortlistResponse)
async def remove_shortlist_entry(job_id: str, candidate_id: str) -> ShortlistResponse:
    candidate = require_candidate(job_id, candidate_id)
    store.delete_shortlist_entry(job_id, candidate_id)
    store.update_candidate(candidate.model_copy(update={"shortlist_status": False}))
    return ShortlistResponse(items=sorted_shortlist(job_id))


@app.post("/jobs/{job_id}/compare", response_model=CandidateComparisonResponse)
async def compare_candidates(job_id: str, request: CandidateComparisonRequest) -> CandidateComparisonResponse:
    require_job(job_id)
    stage = validate_comparison_stage(request.stage)
    if len(request.candidate_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two candidates are required for comparison.")

    candidates = [require_candidate(job_id, candidate_id) for candidate_id in request.candidate_ids]
    if any(candidate.current_stage != stage for candidate in candidates):
        raise HTTPException(status_code=400, detail="All compared candidates must currently be in the requested stage.")

    items: list[CandidateComparisonItem] = []
    for candidate in candidates:
        evaluation = store.get_stage_evaluation(candidate.candidate_id, stage)
        if evaluation is None:
            raise HTTPException(status_code=400, detail=f"Candidate '{candidate.candidate_id}' has no evaluation for stage '{stage}'.")
        aggregate = aggregate_feedback(stage, store.list_feedback(candidate.candidate_id, stage))
        items.append(
            CandidateComparisonItem(
                candidate_id=candidate.candidate_id,
                name=candidate.name,
                filename=candidate.filename,
                current_stage=candidate.current_stage,
                fit_score=evaluation.fit_score,
                decision=evaluation.decision,
                scorecard=evaluation.scorecard,
                hard_filter_results=evaluation.hard_filter_results,
                top_matched_requirements=evaluation.matched_requirements[:3],
                top_missing_requirements=evaluation.missing_requirements[:3],
                top_risks=evaluation.risk_flags[:3],
                transferable_skill_highlights=evaluation.transferable_skills[:3],
                interview_feedback_summary=aggregate.summary,
                conflict_indicator=evaluation.conflict_analysis.has_conflict if evaluation.conflict_analysis else False,
                explainability_summary=build_explainability_summary(evaluation.explainability),
            )
        )

    ordered = sorted(items, key=lambda item: (-item.fit_score, item.name.lower()))
    return CandidateComparisonResponse(
        job_id=job_id,
        stage=stage,
        comparisons=ordered,
        comparative_summary=build_comparative_summary(ordered),
    )


def load_profile(department_profile: str | None, department_rules_yaml: str | None):
    normalized = department_profile.strip() if department_profile else ""
    if not normalized:
        return DepartmentProfile()
    rules_config = load_department_rules(department_rules_yaml) if department_rules_yaml else load_department_rules_file()
    _, profile = resolve_department_profile(rules_config, normalized)
    return profile


def resolve_department_profile_for_job(department_profile: str | None, department_rules_yaml: str | None):
    rules_config = load_department_rules(department_rules_yaml) if department_rules_yaml else load_department_rules_file()
    return resolve_department_profile(rules_config, department_profile)


def resolve_optional_department_profile(department_profile: str | None, department_rules_yaml: str | None) -> str | None:
    normalized = department_profile.strip() if department_profile else ""
    if not normalized:
        return None
    try:
        profile_name, _ = resolve_department_profile_for_job(
            department_profile=normalized,
            department_rules_yaml=department_rules_yaml,
        )
    except RuleLoadError:
        return None
    return profile_name


async def process_upload(
    upload: UploadFile,
    jd_text: str,
    profile,
    department_preferences,
    interview_notes_text: str | None,
    candidate_stage: str,
    ollama: OllamaClient,
    candidate_id: str,
) -> tuple[RankedBatchResult | None, BatchErrorItem | None]:
    filename = upload.filename or candidate_id
    if upload.content_type not in {"application/pdf", "application/octet-stream"}:
        return None, BatchErrorItem(candidate_id=candidate_id, filename=filename, error="Resume must be a PDF upload.")

    try:
        resume_bytes = await upload.read()
        evaluation = evaluate_resume_bytes(
            resume_bytes=resume_bytes,
            jd_text=jd_text,
            profile=profile,
            department_preferences=department_preferences,
            interview_notes_text=interview_notes_text,
            candidate_stage=candidate_stage,
            ollama=ollama,
        )
        return ranked_result_from_evaluation(evaluation, candidate_id, filename), None
    except (PdfParseError, OllamaError, ValueError) as exc:
        fallback = build_failure_result(candidate_id=candidate_id, filename=filename, error=str(exc))
        return fallback, BatchErrorItem(candidate_id=candidate_id, filename=filename, error=str(exc))


def evaluate_resume_bytes(
    resume_bytes: bytes,
    jd_text: str,
    profile,
    department_preferences,
    interview_notes_text: str | None,
    candidate_stage: str,
    ollama: OllamaClient,
    workflow_stage: str | None = None,
    conflict_analysis: ConflictAnalysis | None = None,
) -> ScanResponse:
    resume_text = extract_pdf_text(resume_bytes)
    chunks = chunk_resume_text(resume_text)
    result = score_resume(
        jd_text=jd_text,
        resume_text=resume_text,
        chunks=chunks,
        profile=profile,
        department_preferences=department_preferences,
        interview_notes_text=interview_notes_text,
        candidate_stage=candidate_stage,
        ollama=ollama,
    )
    summary = build_summary(result=result, jd_text=jd_text, ollama=ollama)
    explainability = build_explainability(result, workflow_stage=workflow_stage, conflict_analysis=conflict_analysis)
    return result.to_response(summary=summary, explainability=explainability, conflict_analysis=conflict_analysis)


def build_summary(result: ScoreResult, jd_text: str, ollama: OllamaClient) -> str:
    summary = build_fallback_summary(result)
    try:
        prompt = build_summary_prompt(jd_text=jd_text, score_result=result)
        summary = ollama.generate_summary(prompt)
        try:
            result.risk_flags = ollama.rewrite_risk_flags(result.risk_flags)
        except OllamaError:
            pass
    except OllamaError:
        pass
    return summary


def ranked_result_from_evaluation(result: ScanResponse, candidate_id: str, filename: str) -> RankedBatchResult:
    return RankedBatchResult(
        candidate_id=candidate_id,
        filename=filename,
        fit_score=result.fit_score,
        decision=result.decision,
        matched_requirements=result.matched_requirements,
        missing_requirements=result.missing_requirements,
        risk_flags=result.risk_flags,
        evidence=result.evidence,
        summary=result.summary,
        hard_filter_results=result.hard_filter_results,
        soft_score_breakdown=result.soft_score_breakdown,
        structured_jd=result.structured_jd,
        error_notes=result.error_notes,
        scorecard=result.scorecard,
        structured_department_preferences=result.structured_department_preferences,
        structured_interview_feedback=result.structured_interview_feedback,
        transferable_skills=result.transferable_skills,
        explainability=result.explainability,
        conflict_analysis=result.conflict_analysis,
    )


def build_failure_result(candidate_id: str, filename: str, error: str) -> RankedBatchResult:
    return RankedBatchResult(
        candidate_id=candidate_id,
        filename=filename,
        fit_score=0,
        decision="no",
        matched_requirements=[],
        missing_requirements=[],
        risk_flags=[],
        evidence=[],
        summary="Resume could not be processed.",
        hard_filter_results=[],
        soft_score_breakdown={
            "must_have_semantic": 0.0,
            "nice_to_have_semantic": 0.0,
            "seniority_alignment": 0.0,
            "domain_alignment": 0.0,
            "tool_stack_alignment": 0.0,
            "semantic_scoring_available": False,
        },
        structured_jd={
            "must_have": [],
            "nice_to_have": [],
            "responsibilities": [],
            "domain_keywords": [],
            "tool_keywords": [],
        },
        error_notes=[error],
        scorecard={
            "candidate_stage": "pre_interview",
            "jd_match_score": 0.0,
            "department_preference_score": 0.0,
            "interview_feedback_score": 0.0,
            "transferable_skill_score": 0.0,
        },
        structured_department_preferences={
            "preferred_backgrounds": [],
            "preferred_company_types": [],
            "preferred_company_stage": [],
            "preferred_traits": [],
            "disliked_signals": [],
            "preferred_domains": [],
            "preferred_working_style": [],
            "transferable_skill_policy": "balanced",
            "preference_weights": {},
        },
        structured_interview_feedback={
            "technical_depth": 0.0,
            "communication": 0.0,
            "domain_fit": 0.0,
            "learning_agility": 0.0,
            "ownership": 0.0,
            "collaboration": 0.0,
            "stability_confidence": 0.0,
            "interviewer_recommendation": 0.0,
            "concerns": [],
            "overall_sentiment": 0.0,
        },
        transferable_skills=[],
        explainability=ExplainabilityBlock(
            why_not_recommended=[ExplainabilityItem(label="processing_error", detail=error)],
            top_risks=[error],
            evidence_sources=[ExplainabilityEvidenceSource(source_type="resume", detail="Resume processing failed.")],
        ),
        conflict_analysis=None,
    )


def scan_response_from_ranked(result: RankedBatchResult) -> ScanResponse:
    return ScanResponse(
        fit_score=result.fit_score,
        decision=result.decision,
        matched_requirements=result.matched_requirements,
        missing_requirements=result.missing_requirements,
        risk_flags=result.risk_flags,
        evidence=result.evidence,
        summary=result.summary,
        hard_filter_results=result.hard_filter_results,
        soft_score_breakdown=result.soft_score_breakdown,
        structured_jd=result.structured_jd,
        error_notes=result.error_notes,
        scorecard=result.scorecard,
        structured_department_preferences=result.structured_department_preferences,
        structured_interview_feedback=result.structured_interview_feedback,
        transferable_skills=result.transferable_skills,
        explainability=result.explainability,
        conflict_analysis=result.conflict_analysis,
    )


def validate_request_inputs(resumes: Iterable[UploadFile], jd_text: str) -> None:
    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="JD text is required.")
    if not list(resumes):
        raise HTTPException(status_code=400, detail="At least one resume is required.")


def ranking_key(result: RankedBatchResult) -> tuple[int, int, int, str]:
    has_error = 1 if result.error_notes else 0
    hard_failures = sum(1 for item in result.hard_filter_results if not item.passed)
    return (has_error, hard_failures, -result.fit_score, result.filename.lower())


def build_shortlist(results: list[RankedBatchResult], top_n: int = 3) -> list[RankedBatchResult]:
    shortlist = [item for item in results if item.decision in {"strong_yes", "yes", "strong_hire", "proceed_to_next_round"}]
    if shortlist:
        return shortlist
    return results[:top_n]


def build_recruiter_summary(results: list[RankedBatchResult]) -> RecruiterSummary:
    decisions = Counter(item.decision for item in results)
    missing_counts = Counter(
        missing.requirement
        for item in results
        for missing in item.missing_requirements
    )
    risk_counts = Counter(
        risk.category
        for item in results
        for risk in item.risk_flags
    )
    return RecruiterSummary(
        total_screened=len(results),
        strong_yes_count=decisions.get("strong_yes", 0) + decisions.get("strong_hire", 0),
        yes_count=decisions.get("yes", 0) + decisions.get("proceed_to_next_round", 0),
        maybe_count=decisions.get("maybe", 0) + decisions.get("hold", 0),
        no_count=decisions.get("no", 0) + decisions.get("reject", 0),
        top_recurring_missing_requirements=[name for name, _ in missing_counts.most_common(5)],
        top_recurring_risk_flags=[name for name, _ in risk_counts.most_common(5)],
    )


def build_export_outputs(
    ranked_results: list[RankedBatchResult],
    recruiter_summary: RecruiterSummary,
    error_summary: list[BatchErrorItem],
    export_formats: str | None,
) -> BatchExportOutputs | None:
    formats = parse_export_formats(export_formats)
    if not formats:
        return None

    outputs = BatchExportOutputs()
    if "json" in formats:
        outputs.json_file = json.dumps(
            {
                "total_resumes": len(ranked_results),
                "ranked_results": [item.model_dump() for item in ranked_results],
                "recruiter_summary": recruiter_summary.model_dump(),
                "error_summary": [item.model_dump() for item in error_summary],
            },
            ensure_ascii=False,
            indent=2,
        )
    if "csv" in formats:
        outputs.csv_summary = build_csv_summary(ranked_results)
    return outputs


def parse_export_formats(export_formats: str | None) -> set[str]:
    if not export_formats:
        return set()
    formats = {item.strip().lower() for item in export_formats.split(",") if item.strip()}
    return {item for item in formats if item in {"json", "csv"}}


def build_csv_summary(results: list[RankedBatchResult]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "filename",
            "fit_score",
            "decision",
            "hard_filter_pass",
            "top_missing_requirements",
            "top_risk_flags",
            "summary",
        ]
    )
    for item in results:
        writer.writerow(
            [
                item.filename,
                item.fit_score,
                item.decision,
                str(all(filter_item.passed for filter_item in item.hard_filter_results)),
                "; ".join(m.requirement for m in item.missing_requirements[:3]),
                "; ".join(r.message for r in item.risk_flags[:3]),
                item.summary,
            ]
        )
    return buffer.getvalue()


def validate_candidate_stage(candidate_stage: str) -> str:
    normalized = candidate_stage.strip().lower()
    if normalized not in {"pre_interview", "post_interview"}:
        raise RuleLoadError("candidate_stage must be one of: pre_interview, post_interview")
    return normalized


def validate_workflow_stage(stage: str) -> str:
    normalized = stage.strip().lower()
    if normalized not in STAGE_ORDER:
        raise HTTPException(status_code=400, detail="Stage must be one of: initial_screen, first_round, second_round")
    return normalized


def validate_feedback_stage(stage: str) -> str:
    normalized = validate_workflow_stage(stage)
    if normalized not in {"first_round", "second_round"}:
        raise HTTPException(status_code=400, detail="Feedback is only supported for first_round and second_round.")
    return normalized


def validate_comparison_stage(stage: str) -> str:
    normalized = validate_workflow_stage(stage)
    if normalized not in {"first_round", "second_round"}:
        raise HTTPException(status_code=400, detail="Candidate comparison is only supported for first_round and second_round.")
    return normalized


def require_job(job_id: str) -> Job:
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")
    return job


def require_candidate(job_id: str, candidate_id: str) -> Candidate:
    candidate = store.get_candidate(job_id, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' was not found for job '{job_id}'.")
    return candidate


def build_job_detail(job: Job) -> JobDetail:
    return JobDetail(
        **job.model_dump(),
        candidate_count=len(store.list_candidates(job.job_id)),
        shortlist_count=len(store.list_shortlist_entries(job.job_id)),
    )


def build_candidate_detail(candidate: Candidate) -> CandidateDetail:
    evaluations = store.list_stage_evaluations(candidate.candidate_id)
    latest = evaluations[-1] if evaluations else None
    shortlist_entry = store.get_shortlist_entry(candidate.job_id, candidate.candidate_id)
    conflict = latest.conflict_analysis if latest else None
    return CandidateDetail(
        **candidate.model_dump(),
        evaluations=evaluations,
        latest_evaluation=latest,
        shortlist_entry=shortlist_entry,
        conflict_analysis=conflict,
    )


def evaluate_candidate_for_stage(
    job: Job,
    candidate: Candidate,
    stage: str,
    jd_text: str,
    department_preference_input: str | dict[str, object] | None,
    interview_notes_text: str | None,
) -> StageEvaluation:
    document = store.get_candidate_document(candidate.candidate_id)
    if document is None:
        raise HTTPException(status_code=400, detail="Candidate resume is not available for evaluation.")

    profile = load_profile(job.department_profile, job.department_rules_yaml)
    preferences = load_department_preferences(department_preference_input)
    feedback_items = store.list_feedback(candidate.candidate_id, stage)
    aggregate = aggregate_feedback(stage, feedback_items)
    combined_notes = interview_notes_text or aggregate_notes_text(feedback_items)
    response = evaluate_resume_bytes(
        resume_bytes=document["resume_bytes"],  # type: ignore[arg-type]
        jd_text=jd_text,
        profile=profile,
        department_preferences=preferences,
        interview_notes_text=combined_notes,
        candidate_stage=workflow_stage_to_candidate_stage(stage),
        ollama=OllamaClient(),
        workflow_stage=stage,
        conflict_analysis=aggregate.conflict_analysis,
    )
    response = response.model_copy(
        update={
            "decision": choose_workflow_decision(response.fit_score, response.hard_filter_results, stage),
            "conflict_analysis": aggregate.conflict_analysis,
        }
    )
    return StageEvaluation(
        candidate_id=candidate.candidate_id,
        job_id=job.job_id,
        stage=stage,
        created_at=now_iso(),
        **response.model_dump(),
    )


def workflow_stage_to_candidate_stage(stage: str) -> str:
    return "pre_interview" if stage == "initial_screen" else "post_interview"


def choose_workflow_decision(fit_score: int, hard_filter_results, stage: str) -> str:
    hard_failures = sum(1 for item in hard_filter_results if not item.passed)
    if stage == "initial_screen":
        if hard_failures >= 2 or fit_score < 35:
            return "no"
        if hard_failures >= 1 or fit_score < 55:
            return "maybe"
        if fit_score < 75:
            return "yes"
        return "strong_yes"
    if stage == "first_round":
        if hard_failures >= 2 or fit_score < 45:
            return "reject"
        if hard_failures >= 1 or fit_score < 70:
            return "hold"
        return "proceed_to_second_round"
    if hard_failures >= 2 or fit_score < 55:
        return "reject"
    if hard_failures >= 1 or fit_score < 80:
        return "hold"
    return "strong_hire"


def build_explainability(
    result: ScoreResult,
    workflow_stage: str | None,
    conflict_analysis: ConflictAnalysis | None,
) -> ExplainabilityBlock:
    why_not = [ExplainabilityItem(label="missing_requirement", detail=item.requirement) for item in result.missing_requirements[:3]]
    if conflict_analysis and conflict_analysis.has_conflict:
        why_not.append(ExplainabilityItem(label="interviewer_conflict", detail=conflict_analysis.summary))
    evidence_sources = [
        ExplainabilityEvidenceSource(source_type="resume", detail=item.evidence)
        for item in result.matched_requirements[:2]
    ]
    if any(result.structured_department_preferences.model_dump().values()):
        evidence_sources.append(
            ExplainabilityEvidenceSource(
                source_type="department_preference",
                detail="Dynamic department preferences adjusted the evaluation.",
            )
        )
    if workflow_stage in {"first_round", "second_round"} and (
        result.structured_interview_feedback.overall_sentiment > 0 or result.structured_interview_feedback.concerns
    ):
        evidence_sources.append(
            ExplainabilityEvidenceSource(
                source_type="interview_feedback",
                detail="Interview feedback influenced the stage decision.",
            )
        )
    return ExplainabilityBlock(
        why_recommended=[ExplainabilityItem(label="matched_requirement", detail=item.requirement) for item in result.matched_requirements[:3]],
        why_not_recommended=why_not,
        top_strengths=[item.requirement for item in result.matched_requirements[:3]],
        top_risks=[item.message for item in result.risk_flags[:3]],
        transferable_skill_rationale=[item.reason for item in result.transferable_skills[:3]],
        evidence_sources=evidence_sources,
    )


def build_explainability_summary(explainability: ExplainabilityBlock) -> str:
    strengths = ", ".join(explainability.top_strengths[:2]) or "No major strengths recorded"
    risks = ", ".join(explainability.top_risks[:2]) or "No major risks recorded"
    return f"Strengths: {strengths}. Risks: {risks}."


def aggregate_feedback(stage: str, items: list[InterviewFeedback]) -> AggregatedInterviewFeedback:
    if not items:
        return AggregatedInterviewFeedback(
            stage=stage,
            feedback_count=0,
            average_scores=parse_interview_notes(None),
            recommendation_distribution={},
            merged_concerns=[],
            summary="No interview feedback submitted yet.",
            conflict_analysis=None,
        )

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    average = parse_interview_notes(None)
    average.technical_depth = avg([item.structured_feedback.technical_depth for item in items])
    average.communication = avg([item.structured_feedback.communication for item in items])
    average.domain_fit = avg([item.structured_feedback.domain_fit for item in items])
    average.learning_agility = avg([item.structured_feedback.learning_agility for item in items])
    average.ownership = avg([item.structured_feedback.ownership for item in items])
    average.collaboration = avg([item.structured_feedback.collaboration for item in items])
    average.stability_confidence = avg([item.structured_feedback.stability_confidence for item in items])
    average.interviewer_recommendation = avg([item.structured_feedback.interviewer_recommendation for item in items])
    average.overall_sentiment = avg([item.structured_feedback.overall_sentiment for item in items])
    average.concerns = list(dict.fromkeys(concern for item in items for concern in item.concerns))[:6]
    conflict = analyze_feedback_conflict(items)
    return AggregatedInterviewFeedback(
        stage=stage,
        feedback_count=len(items),
        average_scores=average,
        recommendation_distribution=dict(Counter(item.recommendation for item in items)),
        merged_concerns=average.concerns,
        summary=build_feedback_summary(stage, items, average, conflict),
        conflict_analysis=conflict,
    )


def analyze_feedback_conflict(items: list[InterviewFeedback]) -> ConflictAnalysis:
    if len(items) < 2:
        return ConflictAnalysis()
    conflict_dimensions: list[str] = []
    recommendation_groups = {normalize_recommendation_group(item.recommendation) for item in items}
    if "hire" in recommendation_groups and "reject" in recommendation_groups:
        conflict_dimensions.extend(["overall_recommendation", "hire_reject_tendency"])
    elif len(recommendation_groups) > 1:
        conflict_dimensions.append("overall_recommendation")
    for label in ("technical_depth", "communication", "domain_fit"):
        values = [getattr(item.structured_feedback, label) for item in items]
        if max(values) - min(values) >= 0.45:
            conflict_dimensions.append(label)
    if not conflict_dimensions:
        return ConflictAnalysis(
            has_conflict=False,
            conflict_dimensions=[],
            summary="Interviewer feedback is broadly aligned.",
            follow_up_questions=[],
        )
    unique = list(dict.fromkeys(conflict_dimensions))
    return ConflictAnalysis(
        has_conflict=True,
        conflict_dimensions=unique,
        summary="Interviewers disagree on meaningful signals and the candidate needs recruiter review.",
        follow_up_questions=[f"Resolve disagreement in {item.replace('_', ' ')}." for item in unique[:3]],
    )


def build_feedback_summary(stage: str, items: list[InterviewFeedback], average, conflict: ConflictAnalysis | None) -> str:
    summary = (
        f"{len(items)} interviewer(s) submitted feedback for {stage}. "
        f"Average sentiment: {average.overall_sentiment:.2f}. "
        f"Top concerns: {', '.join(average.concerns[:2]) or 'none'}."
    )
    if conflict and conflict.has_conflict:
        summary += f" Conflict detected in: {', '.join(conflict.conflict_dimensions)}."
    return summary


def aggregate_notes_text(items: list[InterviewFeedback]) -> str | None:
    if not items:
        return None
    return "\n".join(item.raw_notes for item in items)


def normalize_feedback_recommendation(explicit_recommendation: str | None, raw_notes: str) -> str:
    if explicit_recommendation:
        return explicit_recommendation.strip().lower().replace(" ", "_")
    lowered = raw_notes.lower()
    if "strong hire" in lowered:
        return "strong_hire"
    if "hire" in lowered or "proceed" in lowered:
        return "hire"
    if "hold" in lowered:
        return "hold"
    if "reject" in lowered or "no hire" in lowered:
        return "reject"
    return "mixed"


def normalize_recommendation_group(recommendation: str) -> str:
    if recommendation in {"strong_hire", "hire", "proceed_to_second_round"}:
        return "hire"
    if recommendation in {"reject", "no_hire"}:
        return "reject"
    return "hold"


def latest_evaluation(candidate_id: str) -> StageEvaluation | None:
    evaluations = store.list_stage_evaluations(candidate_id)
    return evaluations[-1] if evaluations else None


def build_shortlist_entry(candidate: Candidate, evaluation: StageEvaluation, conflict: ConflictAnalysis | None) -> ShortlistEntry:
    existing = store.get_shortlist_entry(candidate.job_id, candidate.candidate_id)
    return ShortlistEntry(
        candidate_id=candidate.candidate_id,
        job_id=candidate.job_id,
        current_stage=candidate.current_stage,
        fit_score=evaluation.fit_score,
        decision=evaluation.decision,
        shortlist_priority=existing.shortlist_priority if existing else None,
        top_strengths=evaluation.explainability.top_strengths[:3],
        top_risks=evaluation.explainability.top_risks[:3],
        conflict_indicator=conflict.has_conflict if conflict else False,
        explainability_summary=build_explainability_summary(evaluation.explainability),
    )


def sorted_shortlist(job_id: str) -> list[ShortlistEntry]:
    return sort_shortlist_entries(store.list_shortlist_entries(job_id))


def sort_shortlist_entries(entries: list[ShortlistEntry]) -> list[ShortlistEntry]:
    return sorted(
        entries,
        key=lambda item: (
            1 if item.conflict_indicator else 0,
            0 if item.shortlist_priority is not None else 1,
            item.shortlist_priority if item.shortlist_priority is not None else 0,
            -STAGE_ORDER.get(item.current_stage, 0),
            SHORTLIST_DECISION_ORDER.get(item.decision, 99),
            -item.fit_score,
            item.candidate_id,
        ),
    )


def build_comparative_summary(items: list[CandidateComparisonItem]) -> list[str]:
    if not items:
        return []
    strongest_domain = max(items, key=lambda item: item.scorecard.department_preference_score)
    strongest_transferable = max(items, key=lambda item: item.scorecard.transferable_skill_score)
    lower_risk = min(items, key=lambda item: len(item.top_risks))
    summary = [
        f"{strongest_domain.name} is stronger in domain fit and preference alignment.",
        f"{strongest_transferable.name} shows the strongest transferable skill upside.",
        f"{lower_risk.name} is lower risk based on current recruiter-facing flags.",
    ]
    if len(items) >= 2:
        summary.append("Compared candidates are viable in different ways across domain depth, risk, and transferable potential.")
    return summary


def normalize_preference_input(raw_value: str | dict[str, object] | None) -> str | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, dict):
        return json.dumps(raw_value, ensure_ascii=False)
    normalized = raw_value.strip()
    return normalized or None


def normalize_rules_override(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and {"default_profile", "profiles"} <= set(payload):
        return json.dumps(payload, ensure_ascii=False)
    try:
        rules_config = load_department_rules(normalized)
    except RuleLoadError:
        return None
    return json.dumps(rules_config.model_dump(), ensure_ascii=False)


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()
