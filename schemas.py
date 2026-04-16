from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeChunk(BaseModel):
    title: str
    section_label: str
    content: str


class EmbeddingItem(BaseModel):
    text: str
    vector: list[float]


class ProfileScoringWeights(BaseModel):
    must_have_semantic: float = 0.45
    nice_to_have_semantic: float = 0.15
    seniority_alignment: float = 0.15
    domain_alignment: float = 0.15
    tool_stack_alignment: float = 0.10


class DepartmentProfile(BaseModel):
    must_have_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    minimum_years_experience: int | None = None
    preferred_domains: list[str] = Field(default_factory=list)
    required_languages: list[str] = Field(default_factory=list)
    required_education: list[str] = Field(default_factory=list)
    location_constraints: list[str] = Field(default_factory=list)
    work_authorization: str | None = None
    seniority_keywords: list[str] = Field(default_factory=list)
    tool_keywords: list[str] = Field(default_factory=list)
    scoring_weights: ProfileScoringWeights = Field(default_factory=ProfileScoringWeights)


class DepartmentRulesConfig(BaseModel):
    default_profile: str
    profiles: dict[str, DepartmentProfile]


class DepartmentPreferences(BaseModel):
    preferred_backgrounds: list[str] = Field(default_factory=list)
    preferred_company_types: list[str] = Field(default_factory=list)
    preferred_company_stage: list[str] = Field(default_factory=list)
    preferred_traits: list[str] = Field(default_factory=list)
    disliked_signals: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    preferred_working_style: list[str] = Field(default_factory=list)
    transferable_skill_policy: str = "balanced"
    preference_weights: dict[str, float] = Field(default_factory=dict)


class StructuredJD(BaseModel):
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    tool_keywords: list[str] = Field(default_factory=list)


class StructuredInterviewFeedback(BaseModel):
    technical_depth: float = 0.0
    communication: float = 0.0
    domain_fit: float = 0.0
    learning_agility: float = 0.0
    ownership: float = 0.0
    collaboration: float = 0.0
    stability_confidence: float = 0.0
    interviewer_recommendation: float = 0.0
    concerns: list[str] = Field(default_factory=list)
    overall_sentiment: float = 0.0


class TransferableSkill(BaseModel):
    jd_skill: str
    candidate_skill: str
    relationship: str
    score: float
    reason: str


class Scorecard(BaseModel):
    candidate_stage: str
    jd_match_score: float
    department_preference_score: float
    interview_feedback_score: float
    transferable_skill_score: float


class RequirementMatch(BaseModel):
    requirement: str
    score: float
    evidence: str


class MissingRequirement(BaseModel):
    requirement: str
    reason: str


class MatchEvidence(BaseModel):
    matched_jd_item: str
    matched_resume_snippet: str
    section_label: str
    similarity_score: float


class RiskFlag(BaseModel):
    category: str
    message: str


class HardFilterResult(BaseModel):
    name: str
    passed: bool
    details: str


class SoftScoreBreakdown(BaseModel):
    must_have_semantic: float
    nice_to_have_semantic: float
    seniority_alignment: float
    domain_alignment: float
    tool_stack_alignment: float
    semantic_scoring_available: bool


class ExplainabilityItem(BaseModel):
    label: str
    detail: str


class ExplainabilityEvidenceSource(BaseModel):
    source_type: str
    detail: str


class ExplainabilityBlock(BaseModel):
    why_recommended: list[ExplainabilityItem] = Field(default_factory=list)
    why_not_recommended: list[ExplainabilityItem] = Field(default_factory=list)
    top_strengths: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    transferable_skill_rationale: list[str] = Field(default_factory=list)
    evidence_sources: list[ExplainabilityEvidenceSource] = Field(default_factory=list)


class ConflictAnalysis(BaseModel):
    has_conflict: bool = False
    conflict_dimensions: list[str] = Field(default_factory=list)
    summary: str = ""
    follow_up_questions: list[str] = Field(default_factory=list)


class ScanResponse(BaseModel):
    fit_score: int
    decision: str
    matched_requirements: list[RequirementMatch]
    missing_requirements: list[MissingRequirement]
    risk_flags: list[RiskFlag]
    evidence: list[MatchEvidence]
    summary: str
    hard_filter_results: list[HardFilterResult]
    soft_score_breakdown: SoftScoreBreakdown
    structured_jd: StructuredJD
    error_notes: list[str]
    scorecard: Scorecard
    structured_department_preferences: DepartmentPreferences
    structured_interview_feedback: StructuredInterviewFeedback
    transferable_skills: list[TransferableSkill]
    explainability: ExplainabilityBlock = Field(default_factory=ExplainabilityBlock)
    conflict_analysis: ConflictAnalysis | None = None


class RankedBatchResult(ScanResponse):
    candidate_id: str
    filename: str


class BatchErrorItem(BaseModel):
    candidate_id: str
    filename: str
    error: str


class RecruiterSummary(BaseModel):
    total_screened: int
    strong_yes_count: int
    yes_count: int
    maybe_count: int
    no_count: int
    top_recurring_missing_requirements: list[str]
    top_recurring_risk_flags: list[str]


class BatchExportOutputs(BaseModel):
    json_file: str | None = None
    csv_summary: str | None = None


class BatchScanResponse(BaseModel):
    total_resumes: int
    ranked_results: list[RankedBatchResult]
    shortlist: list[RankedBatchResult]
    error_summary: list[BatchErrorItem]
    recruiter_summary: RecruiterSummary
    export_outputs: BatchExportOutputs | None = None


class ScoreResult(BaseModel):
    fit_score: int
    decision: str
    matched_requirements: list[RequirementMatch]
    missing_requirements: list[MissingRequirement]
    risk_flags: list[RiskFlag]
    evidence: list[MatchEvidence]
    hard_filter_results: list[HardFilterResult]
    soft_score_breakdown: SoftScoreBreakdown
    structured_jd: StructuredJD
    error_notes: list[str]
    scorecard: Scorecard
    structured_department_preferences: DepartmentPreferences
    structured_interview_feedback: StructuredInterviewFeedback
    transferable_skills: list[TransferableSkill]

    def to_response(
        self,
        summary: str,
        explainability: ExplainabilityBlock | None = None,
        conflict_analysis: ConflictAnalysis | None = None,
    ) -> ScanResponse:
        return ScanResponse(
            fit_score=self.fit_score,
            decision=self.decision,
            matched_requirements=self.matched_requirements,
            missing_requirements=self.missing_requirements,
            risk_flags=self.risk_flags,
            evidence=self.evidence,
            summary=summary,
            hard_filter_results=self.hard_filter_results,
            soft_score_breakdown=self.soft_score_breakdown,
            structured_jd=self.structured_jd,
            error_notes=self.error_notes,
            scorecard=self.scorecard,
            structured_department_preferences=self.structured_department_preferences,
            structured_interview_feedback=self.structured_interview_feedback,
            transferable_skills=self.transferable_skills,
            explainability=explainability or ExplainabilityBlock(),
            conflict_analysis=conflict_analysis,
        )


WORKFLOW_STAGES = ("initial_screen", "first_round", "second_round")


class JobCreateRequest(BaseModel):
    title: str
    department: str
    jd_text: str
    department_profile: str | None = None
    department_rules_yaml: str | None = None
    default_department_preference_input: str | dict[str, object] | None = None
    status: str = "open"


class Job(BaseModel):
    job_id: str
    title: str
    department: str
    jd_text: str
    department_profile: str | None = None
    department_rules_yaml: str | None = None
    default_department_preference_input: str | None = None
    created_at: str
    status: str = "open"


class JobDetail(Job):
    candidate_count: int = 0
    shortlist_count: int = 0


class Candidate(BaseModel):
    candidate_id: str
    job_id: str
    name: str
    filename: str
    current_stage: str
    source: str | None = None
    created_at: str
    shortlist_status: bool = False


class StageEvaluation(ScanResponse):
    candidate_id: str
    job_id: str
    stage: str
    created_at: str


class CandidateDetail(Candidate):
    evaluations: list[StageEvaluation] = Field(default_factory=list)
    latest_evaluation: StageEvaluation | None = None
    shortlist_entry: "ShortlistEntry | None" = None
    conflict_analysis: ConflictAnalysis | None = None


class CandidateListResponse(BaseModel):
    items: list[Candidate]


class StageMoveRequest(BaseModel):
    target_stage: str


class CandidateEvaluationRequest(BaseModel):
    stage: str | None = None
    jd_text: str | None = None
    department_preference_input: str | dict[str, object] | None = None
    interview_notes_text: str | None = None


class InterviewFeedbackCreateRequest(BaseModel):
    stage: str
    interviewer_name: str
    raw_notes: str
    recommendation: str | None = None


class InterviewFeedback(BaseModel):
    feedback_id: str
    candidate_id: str
    stage: str
    interviewer_name: str
    submitted_at: str
    raw_notes: str
    structured_feedback: StructuredInterviewFeedback
    recommendation: str
    concerns: list[str] = Field(default_factory=list)


class AggregatedInterviewFeedback(BaseModel):
    stage: str
    feedback_count: int
    average_scores: StructuredInterviewFeedback
    recommendation_distribution: dict[str, int] = Field(default_factory=dict)
    merged_concerns: list[str] = Field(default_factory=list)
    summary: str = ""
    conflict_analysis: ConflictAnalysis | None = None


class CandidateFeedbackResponse(BaseModel):
    items: list[InterviewFeedback]
    aggregates: list[AggregatedInterviewFeedback]


class ShortlistEntry(BaseModel):
    candidate_id: str
    job_id: str
    current_stage: str
    fit_score: int
    decision: str
    shortlist_priority: int | None = None
    top_strengths: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    conflict_indicator: bool = False
    explainability_summary: str = ""


class ShortlistPriorityRequest(BaseModel):
    shortlist_priority: int | None = None


class ShortlistResponse(BaseModel):
    items: list[ShortlistEntry]


class CandidateComparisonRequest(BaseModel):
    candidate_ids: list[str]
    stage: str


class CandidateComparisonItem(BaseModel):
    candidate_id: str
    name: str
    filename: str
    current_stage: str
    fit_score: int
    decision: str
    scorecard: Scorecard
    hard_filter_results: list[HardFilterResult]
    top_matched_requirements: list[RequirementMatch]
    top_missing_requirements: list[MissingRequirement]
    top_risks: list[RiskFlag]
    transferable_skill_highlights: list[TransferableSkill]
    interview_feedback_summary: str
    conflict_indicator: bool
    explainability_summary: str


class CandidateComparisonResponse(BaseModel):
    job_id: str
    stage: str
    comparisons: list[CandidateComparisonItem]
    comparative_summary: list[str] = Field(default_factory=list)
