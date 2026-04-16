from __future__ import annotations

from collections import defaultdict

from schemas import Candidate, InterviewFeedback, Job, ShortlistEntry, StageEvaluation


class InMemoryWorkflowStore:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.candidates: dict[tuple[str, str], Candidate] = {}
        self.candidate_documents: dict[str, dict[str, str | bytes]] = {}
        self.stage_evaluations: dict[tuple[str, str], StageEvaluation] = {}
        self.interview_feedback: dict[tuple[str, str, str], InterviewFeedback] = {}
        self.shortlist_entries: dict[tuple[str, str], ShortlistEntry] = {}

    def reset(self) -> None:
        self.jobs.clear()
        self.candidates.clear()
        self.candidate_documents.clear()
        self.stage_evaluations.clear()
        self.interview_feedback.clear()
        self.shortlist_entries.clear()

    def add_job(self, job: Job) -> Job:
        self.jobs[job.job_id] = job
        return job

    def list_jobs(self) -> list[Job]:
        return list(self.jobs.values())

    def get_job(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def add_candidate(self, candidate: Candidate) -> Candidate:
        self.candidates[(candidate.job_id, candidate.candidate_id)] = candidate
        return candidate

    def update_candidate(self, candidate: Candidate) -> Candidate:
        self.candidates[(candidate.job_id, candidate.candidate_id)] = candidate
        return candidate

    def get_candidate(self, job_id: str, candidate_id: str) -> Candidate | None:
        return self.candidates.get((job_id, candidate_id))

    def list_candidates(self, job_id: str) -> list[Candidate]:
        return [candidate for (candidate_job_id, _), candidate in self.candidates.items() if candidate_job_id == job_id]

    def save_candidate_document(self, candidate_id: str, filename: str, resume_bytes: bytes, resume_text: str) -> None:
        self.candidate_documents[candidate_id] = {
            "filename": filename,
            "resume_bytes": resume_bytes,
            "resume_text": resume_text,
        }

    def get_candidate_document(self, candidate_id: str) -> dict[str, str | bytes] | None:
        return self.candidate_documents.get(candidate_id)

    def add_stage_evaluation(self, evaluation: StageEvaluation) -> StageEvaluation:
        self.stage_evaluations[(evaluation.candidate_id, evaluation.stage)] = evaluation
        return evaluation

    def get_stage_evaluation(self, candidate_id: str, stage: str) -> StageEvaluation | None:
        return self.stage_evaluations.get((candidate_id, stage))

    def list_stage_evaluations(self, candidate_id: str) -> list[StageEvaluation]:
        evaluations = [item for (stored_candidate_id, _), item in self.stage_evaluations.items() if stored_candidate_id == candidate_id]
        return sorted(evaluations, key=lambda item: item.created_at)

    def add_feedback(self, feedback: InterviewFeedback) -> InterviewFeedback:
        self.interview_feedback[(feedback.candidate_id, feedback.stage, feedback.feedback_id)] = feedback
        return feedback

    def list_feedback(self, candidate_id: str, stage: str | None = None) -> list[InterviewFeedback]:
        output = [
            item
            for (stored_candidate_id, stored_stage, _), item in self.interview_feedback.items()
            if stored_candidate_id == candidate_id and (stage is None or stored_stage == stage)
        ]
        return sorted(output, key=lambda item: item.submitted_at)

    def list_feedback_by_stage(self, candidate_id: str) -> dict[str, list[InterviewFeedback]]:
        grouped: dict[str, list[InterviewFeedback]] = defaultdict(list)
        for item in self.list_feedback(candidate_id):
            grouped[item.stage].append(item)
        return dict(grouped)

    def upsert_shortlist_entry(self, entry: ShortlistEntry) -> ShortlistEntry:
        self.shortlist_entries[(entry.job_id, entry.candidate_id)] = entry
        return entry

    def get_shortlist_entry(self, job_id: str, candidate_id: str) -> ShortlistEntry | None:
        return self.shortlist_entries.get((job_id, candidate_id))

    def delete_shortlist_entry(self, job_id: str, candidate_id: str) -> None:
        self.shortlist_entries.pop((job_id, candidate_id), None)

    def list_shortlist_entries(self, job_id: str) -> list[ShortlistEntry]:
        entries = [item for (stored_job_id, _), item in self.shortlist_entries.items() if stored_job_id == job_id]
        return sorted(entries, key=lambda item: ((item.shortlist_priority is None), item.shortlist_priority or 0, item.candidate_id))


store = InMemoryWorkflowStore()
