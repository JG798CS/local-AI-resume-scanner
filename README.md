# Local Resume Scanner

Simple FastAPI scaffold for a local-AI resume scanner that uses Ollama on `http://localhost:11434`.

## What It Does

- Accepts a resume PDF upload
- Accepts JD text input
- Accepts a department profile name plus optional department-rules YAML and dynamic `department_preference_input`
- Accepts optional interview notes and candidate stage
- Extracts text with PyMuPDF
- Chunks resume content into labeled sections such as summary, experience, projects, education, and skills
- Parses the JD into must-have, nice-to-have, responsibilities, domain keywords, and tool keywords
- Scores JD items against resume chunks with local embeddings
- Applies department rules as separate hard filters and weighted soft scoring
- Supports job-centric workflow management with in-memory jobs, candidates, stage evaluations, shortlist entries, interview feedback, and candidate comparison
- Uses the local chat model only for the final summary and concise risk wording
- Returns structured JSON only

## Workflow Model

The backend now supports two layers:

- Evaluation endpoints:
  - `POST /scan`
  - `POST /scan-batch`
- Workflow endpoints:
  - `POST /jobs`
  - `GET /jobs`
  - `GET /jobs/{job_id}`
  - `POST /jobs/{job_id}/candidates`
  - `GET /jobs/{job_id}/candidates`
  - `GET /jobs/{job_id}/candidates/{candidate_id}`
  - `POST /jobs/{job_id}/candidates/{candidate_id}/evaluate`
  - `POST /jobs/{job_id}/candidates/{candidate_id}/stage`
  - `POST /jobs/{job_id}/candidates/{candidate_id}/feedback`
  - `GET /jobs/{job_id}/candidates/{candidate_id}/feedback`
  - `GET /jobs/{job_id}/shortlist`
  - `POST /jobs/{job_id}/shortlist/generate`
  - `POST /jobs/{job_id}/shortlist/{candidate_id}`
  - `DELETE /jobs/{job_id}/shortlist/{candidate_id}`
  - `POST /jobs/{job_id}/compare`

Core entities:

- `Job`
- `Candidate`
- `StageEvaluation`
- `InterviewFeedback`
- `ShortlistEntry`

This phase uses local in-memory persistence only, so workflow data resets when the app restarts.

## Project Files

- `app.py`: FastAPI app and `/scan` endpoint
- `parser.py`: PDF text extraction
- `chunking.py`: resume chunking logic
- `rules.py`: YAML rule loading
- `llm.py`: direct local Ollama HTTP client
- `scoring.py`: hard-filter and soft-score flow
- `schemas.py`: typed request and response models
- `prompts.py`: summary prompt builder
- `department_rules.yaml`: sample department rules
- `tests/test_smoke.py`: basic scaffold smoke test
- `test_scan_integration.py`: endpoint-level local integration tests
- `store.py`: lightweight in-memory workflow store

## How To Run Locally

1. Create and activate a Python environment.
2. Install dependencies from `requirements.txt`.
3. Start the server:

```bash
uvicorn app:app --reload
```

4. Send a `POST` request to `/scan`.
5. Use `POST /scan-batch` to rank multiple resumes for the same JD.
6. Optionally request lightweight batch exports with `export_formats=json`, `export_formats=csv`, or `export_formats=json,csv`.
7. Use the workflow endpoints when you want job-level hiring operations instead of ad hoc one-off scans.

## Example Request

```powershell
$jd = @"
- Build FastAPI services in Python
- Use SQL in production systems
- 3+ years of backend engineering experience
"@

$rules = Get-Content -Raw .\department_rules.yaml

curl.exe -X POST "http://127.0.0.1:8000/scan" `
  -F "resume=@sample_resume.pdf;type=application/pdf" `
  -F "jd_text=$jd" `
  -F "department_profile=backend_engineering" `
  -F "department_rules_yaml=$rules" `
  -F "department_preference_input=preferred_domains:`n  - recruiting`npreferred_traits:`n  - ownership`npreferred_company_types:`n  - internal tools" `
  -F "interview_notes_text=Strong hire. Clear communication. Strong technically." `
  -F "candidate_stage=post_interview"
```

Built-in sample profiles in `department_rules.yaml`:
- `backend_engineering`
- `ai_platform`
- `product_manager`
- `hr_tech_operations`

## Example Response

```json
{
  "fit_score": 84,
  "decision": "strong_yes",
  "matched_requirements": [
    {
      "requirement": "Python",
      "score": 0.94,
      "evidence": "skills: \"Python, FastAPI, SQL, PostgreSQL, English\""
    }
  ],
  "missing_requirements": [
    {
      "requirement": "Kubernetes",
      "reason": "Nice-to-have item had only weak resume evidence in section 'projects' (0.31)."
    }
  ],
  "risk_flags": [
    {
      "category": "weak_tool_match",
      "message": "Tool stack overlap is acceptable but still leaves some gaps."
    }
  ],
  "evidence": [
    {
      "matched_jd_item": "Build resume screening services",
      "matched_resume_snippet": "\"Built FastAPI services for resume screening and recruiting workflows.\"",
      "section_label": "experience",
      "similarity_score": 0.91
    }
  ],
  "summary": "Strong match across must-have backend requirements with relevant hiring domain evidence.",
  "scorecard": {
    "candidate_stage": "post_interview",
    "jd_match_score": 0.9,
    "department_preference_score": 0.8,
    "interview_feedback_score": 0.88,
    "transferable_skill_score": 0.2
  },
  "hard_filter_results": [
    {
      "name": "required_skill:Python",
      "passed": true,
      "details": "Found in resume text."
    }
  ],
  "soft_score_breakdown": {
    "must_have_semantic": 0.9,
    "nice_to_have_semantic": 0.55,
    "seniority_alignment": 1.0,
    "domain_alignment": 1.0,
    "tool_stack_alignment": 1.0,
    "semantic_scoring_available": true
  },
  "structured_jd": {
    "must_have": ["Python", "FastAPI", "SQL"],
    "nice_to_have": ["Kubernetes"],
    "responsibilities": ["Build resume screening services"],
    "domain_keywords": ["recruiting", "resume"],
    "tool_keywords": ["fastapi", "python", "sql"]
  },
  "error_notes": [],
  "structured_department_preferences": {
    "preferred_backgrounds": [],
    "preferred_company_types": ["internal tools"],
    "preferred_company_stage": [],
    "preferred_traits": ["ownership"],
    "disliked_signals": [],
    "preferred_domains": ["recruiting"],
    "preferred_working_style": [],
    "transferable_skill_policy": "balanced",
    "preference_weights": {}
  },
  "structured_interview_feedback": {
    "technical_depth": 0.6,
    "communication": 0.3,
    "domain_fit": 0.0,
    "learning_agility": 0.0,
    "ownership": 0.0,
    "collaboration": 0.0,
    "stability_confidence": 0.0,
    "interviewer_recommendation": 1.0,
    "concerns": [],
    "overall_sentiment": 0.68
  },
  "transferable_skills": [
    {
      "jd_skill": "FastAPI",
      "candidate_skill": "flask",
      "relationship": "similar_skill",
      "score": 0.7,
      "reason": "Resume shows flask, which is relevant to FastAPI."
    }
  ]
}
```

If `department_rules_yaml` is provided, its profiles override the built-in file for that request. If `department_profile` is missing or unknown, the API returns a clear `400` error listing the available profile names. `department_preference_input` is optional and interpreted dynamically at runtime; if it is omitted, the system uses a neutral preference posture instead of failing.

## Workflow Stages

Workflow endpoints use explicit candidate stages:

- `initial_screen`
- `first_round`
- `second_round`

Stage-specific decisions:

- `initial_screen`: `strong_yes`, `yes`, `maybe`, `no`
- `first_round`: `proceed_to_second_round`, `hold`, `reject`
- `second_round`: `strong_hire`, `hold`, `reject`

The older `/scan` endpoint remains backward-compatible with:

- `pre_interview`
- `post_interview`

## Batch Request Example

```powershell
$jd = @"
- Python
- FastAPI
- SQL
"@

curl.exe -X POST "http://127.0.0.1:8000/scan-batch" `
  -F "resumes=@candidate_a.pdf;type=application/pdf" `
  -F "resumes=@candidate_b.pdf;type=application/pdf" `
  -F "jd_text=$jd" `
  -F "department_profile=backend_engineering" `
  -F "export_formats=json,csv"
```

## Batch Response Example

```json
{
  "total_resumes": 2,
  "ranked_results": [
    {
      "candidate_id": "candidate_1",
      "filename": "candidate_a.pdf",
      "fit_score": 84,
      "decision": "strong_yes",
      "matched_requirements": [],
      "missing_requirements": [],
      "risk_flags": [],
      "evidence": [],
      "summary": "Strong local match with one review item.",
      "hard_filter_results": [],
      "soft_score_breakdown": {
        "must_have_semantic": 0.9,
        "nice_to_have_semantic": 0.6,
        "seniority_alignment": 1.0,
        "domain_alignment": 1.0,
        "tool_stack_alignment": 1.0,
        "semantic_scoring_available": true
      },
      "structured_jd": {
        "must_have": ["Python", "FastAPI", "SQL"],
        "nice_to_have": [],
        "responsibilities": [],
        "domain_keywords": [],
        "tool_keywords": ["fastapi", "python", "sql"]
      },
      "error_notes": []
    }
  ],
  "shortlist": [
    {
      "candidate_id": "candidate_1",
      "filename": "candidate_a.pdf",
      "fit_score": 84,
      "decision": "strong_yes",
      "matched_requirements": [],
      "missing_requirements": [],
      "risk_flags": [],
      "evidence": [],
      "summary": "Strong local match with one review item.",
      "hard_filter_results": [],
      "soft_score_breakdown": {
        "must_have_semantic": 0.9,
        "nice_to_have_semantic": 0.6,
        "seniority_alignment": 1.0,
        "domain_alignment": 1.0,
        "tool_stack_alignment": 1.0,
        "semantic_scoring_available": true
      },
      "structured_jd": {
        "must_have": ["Python", "FastAPI", "SQL"],
        "nice_to_have": [],
        "responsibilities": [],
        "domain_keywords": [],
        "tool_keywords": ["fastapi", "python", "sql"]
      },
      "error_notes": []
    }
  ],
  "recruiter_summary": {
    "total_screened": 2,
    "strong_yes_count": 1,
    "yes_count": 0,
    "maybe_count": 0,
    "no_count": 1,
    "top_recurring_missing_requirements": ["SQL"],
    "top_recurring_risk_flags": ["missing_must_have"]
  },
  "export_outputs": {
    "json_file": "{\n  \"total_resumes\": 2,\n  ...\n}",
    "csv_summary": "filename,fit_score,decision,hard_filter_pass,top_missing_requirements,top_risk_flags,summary\r\ncandidate_a.pdf,84,strong_yes,True,,,...\r\n"
  },
  "error_summary": [
    {
      "candidate_id": "candidate_2",
      "filename": "broken.pdf",
      "error": "Failed to parse resume PDF."
    }
  ]
}
```

`csv_summary` includes:
- `filename`
- `fit_score`
- `decision`
- `hard_filter_pass`
- `top_missing_requirements`
- `top_risk_flags`
- `summary`

## Scoring Breakdown

- Hard filters are evaluated separately and reported in `hard_filter_results`.
- Department profiles can tune required skills, education, locations, domains, and scoring weights independently.
- Department preferences add a separate recruiter-style signal for backgrounds, company stage, traits, dislikes, domains, and working style.
- Interview notes are parsed into structured signals for technical depth, communication, domain fit, learning agility, ownership, collaboration, stability confidence, interviewer recommendation, concerns, and overall sentiment.
- Transferable skills help near-fit candidates by classifying unmatched JD skills as `direct_match`, `similar_skill`, `transferable_skill`, `weak_relation`, or `no_relation`.
- Soft scoring combines weighted components:
  - `must_have_semantic`: 45%
  - `nice_to_have_semantic`: 15%
  - `seniority_alignment`: 15%
  - `domain_alignment`: 15%
  - `tool_stack_alignment`: 10%
- Final `fit_score` uses stage-based weighting:
  - `pre_interview`: `0.60 jd_match + 0.25 department_preference + 0.15 transferable_skill`
  - `post_interview`: `0.35 jd_match + 0.20 department_preference + 0.30 interview_feedback + 0.15 transferable_skill`
- Final decisions use both the normalized `fit_score` and hard-filter pass/fail results:
  - `strong_yes`
  - `yes`
  - `maybe`
  - `no`
  - `strong_hire`
  - `proceed_to_next_round`
  - `hold`
  - `reject`
- Batch ranking sorts resumes by hard-filter failures first, then by `fit_score` descending, then by filename.
- Batch `shortlist` includes all `strong_yes` and `yes` candidates, or falls back to the top 3 ranked resumes if none qualify.

## Workflow Scoring And Explainability

Workflow stage evaluations reuse the same local scoring engine and add recruiter-facing structures:

- `explainability`
  - `why_recommended`
  - `why_not_recommended`
  - `top_strengths`
  - `top_risks`
  - `transferable_skill_rationale`
  - `evidence_sources`
- `conflict_analysis`
  - `has_conflict`
  - `conflict_dimensions`
  - `summary`
  - `follow_up_questions`

Evidence sources distinguish:

- `resume`
- `department_preference`
- `interview_feedback`

## Job Workflow Examples

Create a job:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/jobs" `
  -H "Content-Type: application/json" `
  -d "{\"title\":\"Backend Engineer\",\"department\":\"Engineering\",\"jd_text\":\"Requirements:\n- Python\n- FastAPI\n- SQL\",\"department_profile\":\"backend_engineering\"}"
```

Add a candidate to a job:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/jobs/{job_id}/candidates" `
  -F "resume=@sample_resume.pdf;type=application/pdf" `
  -F "name=Jane Candidate" `
  -F "current_stage=initial_screen"
```

Evaluate a candidate at first round:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/jobs/{job_id}/candidates/{candidate_id}/evaluate" `
  -H "Content-Type: application/json" `
  -d "{\"stage\":\"first_round\",\"interview_notes_text\":\"Hire. Clear communication. Strong technically.\"}"
```

Submit interviewer feedback:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/jobs/{job_id}/candidates/{candidate_id}/feedback" `
  -H "Content-Type: application/json" `
  -d "{\"stage\":\"first_round\",\"interviewer_name\":\"Interviewer 1\",\"raw_notes\":\"Strong hire. Clear communication. Strong technically.\"}"
```

Compare same-stage candidates:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/jobs/{job_id}/compare" `
  -H "Content-Type: application/json" `
  -d "{\"candidate_ids\":[\"candidate_a\",\"candidate_b\"],\"stage\":\"first_round\"}"
```

## Workflow Response Notes

`StageEvaluation` stores:

- stage
- fit_score
- decision
- scorecard
- hard_filter_results
- soft_score_breakdown
- structured_jd
- structured_department_preferences
- structured_interview_feedback
- transferable_skills
- matched_requirements
- missing_requirements
- risk_flags
- evidence
- summary
- error_notes
- explainability
- conflict_analysis
- created_at

Shortlist behavior:

- Generated shortlist entries use the candidate's latest stage evaluation.
- Ranking prefers conflict-free candidates first, then later stages, then manual priority, then stronger decisions and higher fit score.
- Manual shortlist updates can raise or lower a candidate with `shortlist_priority`.

Conflict detection behavior:

- Activated when a candidate has at least two feedback entries for the same stage.
- Detects disagreement in recommendation, technical depth, communication, domain fit, and hire or reject tendency.
- Sets a recruiter-visible conflict flag on stage evaluations, candidate detail, shortlist entries, and comparisons.

Comparison behavior:

- Only supported for `first_round` and `second_round`.
- All compared candidates must belong to the same job and be in the same stage.
- Returns per-candidate summaries plus a concise comparative summary.

## Notes

- Ollama endpoint: `http://localhost:11434`
- Chat model: `qwen3:4b`
- Embedding model: `qwen3-embedding:0.6b`
- No cloud LLM APIs are used
- If the summary model call fails, the API still returns the scoring JSON with a rule-based fallback summary.
- If embedding calls fail after one retry, the API does not crash. It returns `semantic_scoring_available: false` and an `error_notes` entry explaining that semantic scoring was unavailable.
- If `department_profile` is omitted, the configured `default_profile` is used.
- `candidate_stage` supports `pre_interview` and `post_interview`. Interview feedback only affects scoring in `post_interview`.
- If `candidate_stage=post_interview` but `interview_notes_text` is missing, the API still works and records the missing signal in `error_notes`.
- Workflow data is stored in memory only for this phase and will reset on process restart.

## Frontend MVP

A recruiter-facing web UI is now served directly by FastAPI at `/ui`.

Frontend stack:

- plain HTML
- one small vanilla JavaScript module
- one local stylesheet
- no frontend build step

Implemented pages and views:

- Jobs list and job creation page
- Job detail pipeline page with stage columns for `initial_screen`, `first_round`, and `second_round`
- Shortlist section inside the job detail page
- Candidate detail page with scorecard, requirements, risks, transferable skills, evidence, explainability, and feedback
- Candidate comparison page for same-job candidates in `first_round` or `second_round`

Key recruiter actions in the UI:

- create a job
- add a candidate PDF to a job
- move a candidate between stages
- generate shortlist
- add or remove shortlist entries
- update shortlist priority
- submit interview feedback
- run stage evaluations
- compare candidates in the same stage

How to run locally with the frontend:

1. Start the FastAPI app:

```bash
uvicorn app:app --reload
```

2. Open the UI in your browser:

- [http://127.0.0.1:8000/ui](http://127.0.0.1:8000/ui)

Small backend compatibility change for the frontend:

- FastAPI now serves the static frontend files and returns the frontend shell for `/ui` routes.

Current frontend limitations:

- The MVP uses hash-based routing and a single JavaScript module instead of a component framework.
- Candidate cards load through existing backend endpoints and favor simplicity over aggressive caching.
- There is no auth or multi-user state yet.
- The UI is intentionally local-first and does not include file persistence beyond the backend's current in-memory workflow state.
