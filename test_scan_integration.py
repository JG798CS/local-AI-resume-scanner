from __future__ import annotations

from pathlib import Path

import fitz
from fastapi.testclient import TestClient

import app as app_module
from schemas import EmbeddingItem
from store import store


class FakeOllamaClient:
    def embed_texts(self, texts: list[str]) -> list[EmbeddingItem]:
        vectors: list[EmbeddingItem] = []
        for text in texts:
            lower = text.lower()
            vectors.append(
                EmbeddingItem(
                    text=text,
                    vector=[
                        1.0 if "python" in lower else 0.0,
                        1.0 if "fastapi" in lower else 0.0,
                        1.0 if "sql" in lower or "postgresql" in lower else 0.0,
                        1.0 if "english" in lower else 0.0,
                        1.0 if "recruit" in lower or "resume" in lower or "hiring" in lower else 0.0,
                        1.0 if "flask" in lower else 0.0,
                        1.0 if "ownership" in lower or "proactive" in lower else 0.0,
                    ],
                )
            )
        return vectors

    def generate_summary(self, prompt: str) -> str:
        return "Strong local match with one review item."

    def rewrite_risk_flags(self, risk_flags):
        return risk_flags


def build_sample_pdf(path: Path, include_sql: bool = True) -> None:
    skills = "Python, FastAPI, English"
    if include_sql:
        skills += ", SQL, PostgreSQL"
    experience_line = "Built FastAPI services for resume screening and recruiting workflows."
    project_line = "Created internal talent tools with FastAPI."
    if include_sql:
        experience_line = "Built FastAPI services and SQL-backed recruiting workflows."
        project_line = "Created internal talent tools with FastAPI and PostgreSQL."
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "PROFESSIONAL SUMMARY",
                "Backend engineer with 5 years of experience in hiring systems.",
                "",
                "SKILLS",
                skills,
                "",
                "EXPERIENCE",
                experience_line,
                "Owned backend APIs and Python automation for hiring operations.",
                "",
                "PROJECTS",
                project_line,
            ]
        ),
    )
    document.save(path)
    document.close()


def build_transferable_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "SUMMARY",
                "Backend engineer with strong Flask and API experience.",
                "",
                "SKILLS",
                "Python, Flask, English",
                "",
                "EXPERIENCE",
                "Built Flask services, REST APIs, and backend automation for internal teams.",
            ]
        ),
    )
    document.save(path)
    document.close()


def build_hr_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "SUMMARY",
                "HR specialist with 4 years of recruiting and employee support experience.",
                "",
                "SKILLS",
                "Recruiting, HRIS, English, communication, onboarding",
                "",
                "EXPERIENCE",
                "Supported hiring coordination and candidate communication across teams.",
                "Maintained HRIS records and improved interview scheduling workflows.",
            ]
        ),
    )
    document.save(path)
    document.close()


def backend_rules_yaml() -> str:
    return "\n".join(
        [
            "default_profile: backend_engineering",
            "profiles:",
            "  backend_engineering:",
            "    must_have_skills:",
            "      - Python",
            "      - FastAPI",
            "      - SQL",
            "    nice_to_have_skills:",
            "      - Recruiting domain",
            "    minimum_years_experience: 3",
            "    preferred_domains:",
            "      - recruiting",
            "      - resume",
            "    required_languages:",
            "      - English",
            "    required_education: []",
            "    location_constraints: []",
            "    seniority_keywords:",
            "      - backend",
            "      - engineer",
            "    tool_keywords:",
            "      - Python",
            "      - FastAPI",
            "      - SQL",
            "  product_manager:",
            "    must_have_skills:",
            "      - roadmap",
            "      - stakeholder management",
            "    nice_to_have_skills:",
            "      - experimentation",
            "    minimum_years_experience: 5",
            "    preferred_domains:",
            "      - saas",
            "    required_languages:",
            "      - English",
            "    required_education:",
            "      - Business",
            "    location_constraints: []",
            "    seniority_keywords:",
            "      - product",
            "    tool_keywords:",
            "      - analytics",
        ]
    )


def build_client(monkeypatch, client_cls) -> TestClient:
    store.reset()
    monkeypatch.setattr(app_module, "OllamaClient", client_cls)
    return TestClient(app_module.app)


def preference_yaml() -> str:
    return "\n".join(
        [
            "preferred_backgrounds:",
            "  - backend engineer",
            "preferred_company_types:",
            "  - internal tools",
            "preferred_company_stage:",
            "  - internal tools",
            "preferred_traits:",
            "  - ownership",
            "disliked_signals:",
            "  - job hopping",
            "preferred_domains:",
            "  - recruiting",
            "preferred_working_style:",
            "  - proactive",
            "transferable_skill_policy: aggressive",
            "preference_weights:",
            "  preferred_traits: 1.0",
        ]
    )


def test_scan_endpoint_strong_match_case(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "sample_resume.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("sample_resume.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "\n".join(
                [
                    "Requirements:",
                    "- Python",
                    "- FastAPI",
                    "- SQL",
                    "Nice to have:",
                    "- Recruiting domain",
                    "Responsibilities:",
                    "- Build resume screening services",
                ]
            ),
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] in {"yes", "strong_yes"}
    assert payload["fit_score"] >= 55
    assert payload["structured_jd"]["must_have"] == ["Python", "FastAPI", "SQL"]
    assert payload["soft_score_breakdown"]["semantic_scoring_available"] is True
    assert "scorecard" in payload
    assert "structured_department_preferences" in payload
    assert "structured_interview_feedback" in payload
    assert "transferable_skills" in payload
    assert any(item["section_label"] in {"skills", "experience", "projects"} for item in payload["evidence"])
    assert any(item["similarity_score"] >= 0.55 for item in payload["evidence"])


def test_scan_endpoint_missing_must_have_skill(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "missing_sql.pdf"
    build_sample_pdf(pdf_path, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("missing_sql.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["requirement"] == "SQL" for item in payload["missing_requirements"])
    assert any(item["category"] == "missing_must_have" for item in payload["risk_flags"])
    assert any(item["name"] == "required_skill:SQL" and item["passed"] is False for item in payload["hard_filter_results"])


def test_scan_endpoint_uses_fallback_summary_when_llm_fails(monkeypatch, tmp_path) -> None:
    class FailingSummaryClient(FakeOllamaClient):
        def generate_summary(self, prompt: str) -> str:
            raise app_module.OllamaError("summary unavailable")

    pdf_path = tmp_path / "fallback_resume.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FailingSummaryClient)

    response = client.post(
        "/scan",
        files={"resume": ("fallback_resume.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"].startswith("Decision:")


def test_scan_endpoint_handles_embedding_failure(monkeypatch, tmp_path) -> None:
    class FailingEmbeddingClient(FakeOllamaClient):
        def embed_texts(self, texts: list[str]) -> list[EmbeddingItem]:
            raise app_module.OllamaError("embedding unavailable after retry")

    pdf_path = tmp_path / "embedding_failure.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FailingEmbeddingClient)

    response = client.post(
        "/scan",
        files={"resume": ("embedding_failure.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["soft_score_breakdown"]["semantic_scoring_available"] is False
    assert payload["error_notes"]
    assert any("Semantic scoring unavailable" in item for item in payload["error_notes"])


def test_department_preference_affects_score(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "preference.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    base_response = client.post(
        "/scan",
        files={"resume": ("preference.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )
    preferred_response = client.post(
        "/scan",
        files={"resume": ("preference.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
            "department_preference_input": preference_yaml(),
        },
    )

    assert preferred_response.status_code == 200
    assert base_response.status_code == 200
    assert preferred_response.json()["scorecard"]["department_preference_score"] > base_response.json()["scorecard"]["department_preference_score"]
    assert preferred_response.json()["fit_score"] >= base_response.json()["fit_score"]


def test_missing_interview_notes_do_not_break_post_interview(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "missing_notes.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("missing_notes.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "candidate_stage": "post_interview",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scorecard"]["interview_feedback_score"] == 0.0
    assert any("Interview notes were not provided" in item for item in payload["error_notes"])


def test_missing_department_preference_input_does_not_break_scoring(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "neutral_pref.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("neutral_pref.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    assert response.json()["scorecard"]["department_preference_score"] >= 0.0


def test_interview_notes_affect_post_interview_only(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "interview.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)
    notes = (
        "Strong hire. Clear communication. Strong technically. "
        "Shows ownership and collaboration. No major concern."
    )

    pre_response = client.post(
        "/scan",
        files={"resume": ("interview.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
            "interview_notes_text": notes,
            "candidate_stage": "pre_interview",
        },
    )
    post_response = client.post(
        "/scan",
        files={"resume": ("interview.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
            "interview_notes_text": notes,
            "candidate_stage": "post_interview",
        },
    )

    assert pre_response.status_code == 200
    assert post_response.status_code == 200
    assert pre_response.json()["scorecard"]["interview_feedback_score"] == 0.0
    assert post_response.json()["scorecard"]["interview_feedback_score"] > 0.0
    assert post_response.json()["decision"] in {"strong_hire", "proceed_to_next_round", "hold", "reject"}


def test_transferable_skills_improve_near_fit_candidates(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "transferable.pdf"
    build_transferable_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)
    custom_rules = "\n".join(
        [
            "default_profile: backend_engineering",
            "profiles:",
            "  backend_engineering:",
            "    must_have_skills:",
            "      - Python",
            "    nice_to_have_skills: []",
            "    minimum_years_experience: 1",
            "    preferred_domains: []",
            "    required_languages:",
            "      - English",
            "    required_education: []",
            "    location_constraints: []",
            "    seniority_keywords: []",
            "    tool_keywords:",
            "      - FastAPI",
        ]
    )

    response = client.post(
        "/scan",
        files={"resume": ("transferable.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "department_profile": "backend_engineering",
            "department_rules_yaml": custom_rules,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["transferable_skills"]
    assert any(item["relationship"] in {"direct_match", "similar_skill", "transferable_skill", "weak_relation", "no_relation"} for item in payload["transferable_skills"])
    assert payload["scorecard"]["transferable_skill_score"] > 0.0


def test_decision_policy_differs_by_stage(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "stage_decision.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)
    notes = "Strong hire. Clear communication. Strong technically."

    pre = client.post(
        "/scan",
        files={"resume": ("stage_decision.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "candidate_stage": "pre_interview",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )
    post = client.post(
        "/scan",
        files={"resume": ("stage_decision.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI",
            "candidate_stage": "post_interview",
            "interview_notes_text": notes,
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert pre.status_code == 200
    assert post.status_code == 200
    assert pre.json()["decision"] in {"strong_yes", "yes", "maybe", "no"}
    assert post.json()["decision"] in {"strong_hire", "proceed_to_next_round", "hold", "reject"}


def test_scan_endpoint_supports_multiple_department_profiles(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "pm_profile.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("pm_profile.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- roadmap\n- stakeholder management",
            "department_profile": "product_manager",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(item["name"] == "education:Business" for item in payload["hard_filter_results"])
    assert any(item["category"] == "missing_must_have" for item in payload["risk_flags"])


def test_scan_endpoint_rejects_unknown_department_profile(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "unknown_profile.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan",
        files={"resume": ("unknown_profile.pdf", pdf_path.read_bytes(), "application/pdf")},
        data={
            "jd_text": "Requirements:\n- Python",
            "department_profile": "finance_ops",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 400
    assert "Department profile 'finance_ops' was not found" in response.json()["detail"]


def test_scan_batch_ranks_multiple_resumes(monkeypatch, tmp_path) -> None:
    strong_pdf = tmp_path / "strong.pdf"
    weaker_pdf = tmp_path / "weaker.pdf"
    build_sample_pdf(strong_pdf, include_sql=True)
    build_sample_pdf(weaker_pdf, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan-batch",
        files=[
            ("resumes", ("strong.pdf", strong_pdf.read_bytes(), "application/pdf")),
            ("resumes", ("weaker.pdf", weaker_pdf.read_bytes(), "application/pdf")),
        ],
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_resumes"] == 2
    assert payload["ranked_results"][0]["filename"] == "strong.pdf"
    assert payload["ranked_results"][0]["fit_score"] >= payload["ranked_results"][1]["fit_score"]


def test_scan_batch_isolates_broken_pdf(monkeypatch, tmp_path) -> None:
    valid_pdf = tmp_path / "valid.pdf"
    build_sample_pdf(valid_pdf)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan-batch",
        files=[
            ("resumes", ("valid.pdf", valid_pdf.read_bytes(), "application/pdf")),
            ("resumes", ("broken.pdf", b"not-a-real-pdf", "application/pdf")),
        ],
        data={
            "jd_text": "Requirements:\n- Python",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_resumes"] == 2
    assert len(payload["error_summary"]) == 1
    assert payload["error_summary"][0]["filename"] == "broken.pdf"
    broken_result = next(item for item in payload["ranked_results"] if item["filename"] == "broken.pdf")
    assert broken_result["error_notes"]


def test_scan_batch_generates_shortlist(monkeypatch, tmp_path) -> None:
    strong_pdf = tmp_path / "strong.pdf"
    okay_pdf = tmp_path / "okay.pdf"
    weak_pdf = tmp_path / "weak.pdf"
    build_sample_pdf(strong_pdf, include_sql=True)
    build_sample_pdf(okay_pdf, include_sql=True)
    build_sample_pdf(weak_pdf, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan-batch",
        files=[
            ("resumes", ("strong.pdf", strong_pdf.read_bytes(), "application/pdf")),
            ("resumes", ("okay.pdf", okay_pdf.read_bytes(), "application/pdf")),
            ("resumes", ("weak.pdf", weak_pdf.read_bytes(), "application/pdf")),
        ],
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["shortlist"]
    assert all(item["decision"] in {"strong_yes", "yes"} for item in payload["shortlist"])


def test_scan_batch_generates_exports(monkeypatch, tmp_path) -> None:
    strong_pdf = tmp_path / "strong.pdf"
    build_sample_pdf(strong_pdf, include_sql=True)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan-batch",
        files=[("resumes", ("strong.pdf", strong_pdf.read_bytes(), "application/pdf"))],
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
            "export_formats": "json,csv",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["export_outputs"]["json_file"]
    assert "\"ranked_results\"" in payload["export_outputs"]["json_file"]
    assert payload["export_outputs"]["csv_summary"]
    assert "filename,fit_score,decision,hard_filter_pass,top_missing_requirements,top_risk_flags,summary" in payload["export_outputs"]["csv_summary"]


def test_scan_batch_includes_recruiter_summary(monkeypatch, tmp_path) -> None:
    strong_pdf = tmp_path / "strong.pdf"
    weak_pdf = tmp_path / "weak.pdf"
    build_sample_pdf(strong_pdf, include_sql=True)
    build_sample_pdf(weak_pdf, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/scan-batch",
        files=[
            ("resumes", ("strong.pdf", strong_pdf.read_bytes(), "application/pdf")),
            ("resumes", ("weak.pdf", weak_pdf.read_bytes(), "application/pdf")),
        ],
        data={
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert response.status_code == 200
    summary = response.json()["recruiter_summary"]
    assert summary["total_screened"] == 2
    assert summary["strong_yes_count"] + summary["yes_count"] + summary["maybe_count"] + summary["no_count"] == 2
    assert isinstance(summary["top_recurring_missing_requirements"], list)
    assert isinstance(summary["top_recurring_risk_flags"], list)


def create_job_and_candidate(client: TestClient, pdf_path: Path) -> tuple[str, str]:
    job_response = client.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "department": "Engineering",
            "jd_text": "Requirements:\n- Python\n- FastAPI\n- SQL",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
            "default_department_preference_input": {
                "preferred_domains": ["recruiting"],
                "preferred_traits": ["ownership"],
            },
        },
    )
    assert job_response.status_code == 200
    job_id = job_response.json()["job_id"]

    candidate_response = client.post(
        f"/jobs/{job_id}/candidates",
        files={"resume": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
        data={"name": "Candidate A"},
    )
    assert candidate_response.status_code == 200
    return job_id, candidate_response.json()["candidate_id"]


def test_job_creation_and_listing(monkeypatch) -> None:
    client = build_client(monkeypatch, FakeOllamaClient)

    create_response = client.post(
        "/jobs",
        json={
            "title": "AI Platform Engineer",
            "department": "Platform",
            "jd_text": "Requirements:\n- Python",
            "department_profile": "backend_engineering",
            "department_rules_yaml": backend_rules_yaml(),
        },
    )

    assert create_response.status_code == 200
    list_response = client.get("/jobs")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "AI Platform Engineer"
    assert payload[0]["candidate_count"] == 0


def test_job_creation_accepts_plain_text_optional_preference_fields(monkeypatch) -> None:
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/jobs",
        json={
            "title": "HRA",
            "department": "HR",
            "jd_text": "Strong communication and employee support experience.",
            "default_department_preference_input": "偏好有招聘经验、沟通强、稳定性好",
            "department_rules_yaml": "1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "HRA"
    assert payload["default_department_preference_input"] == "偏好有招聘经验、沟通强、稳定性好"
    assert payload["department_rules_yaml"] is None


def test_job_creation_ignores_unknown_department_profile_text(monkeypatch) -> None:
    client = build_client(monkeypatch, FakeOllamaClient)

    response = client.post(
        "/jobs",
        json={
            "title": "HRA",
            "department": "HR",
            "department_profile": "负责招聘",
            "jd_text": "Excellent communication and interpersonal skills",
        },
    )

    assert response.status_code == 200
    assert response.json()["department_profile"] is None


def test_candidate_evaluation_without_department_profile_uses_neutral_rules(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "hr_candidate.pdf"
    build_hr_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)

    job_response = client.post(
        "/jobs",
        json={
            "title": "HRA",
            "department": "HR",
            "jd_text": "Excellent communication and interpersonal skills.\nExperience with HRIS systems is a plus.",
        },
    )
    assert job_response.status_code == 200
    job_id = job_response.json()["job_id"]

    candidate_response = client.post(
        f"/jobs/{job_id}/candidates",
        files={"resume": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
        data={"name": "HR Candidate"},
    )
    assert candidate_response.status_code == 200
    latest = candidate_response.json()["latest_evaluation"]
    assert latest is not None
    assert not any(item["name"] == "required_skill:FastAPI" for item in latest["hard_filter_results"])
    assert not any("FastAPI" in item["message"] for item in latest["risk_flags"])


def test_candidate_creation_stage_transition_and_evaluation_storage(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "workflow_candidate.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_id, candidate_id = create_job_and_candidate(client, pdf_path)

    candidate_detail = client.get(f"/jobs/{job_id}/candidates/{candidate_id}")
    assert candidate_detail.status_code == 200
    assert candidate_detail.json()["latest_evaluation"] is not None
    assert candidate_detail.json()["latest_evaluation"]["stage"] == "initial_screen"

    move_response = client.post(
        f"/jobs/{job_id}/candidates/{candidate_id}/stage",
        json={"target_stage": "first_round"},
    )
    assert move_response.status_code == 200
    assert move_response.json()["current_stage"] == "first_round"

    eval_response = client.post(
        f"/jobs/{job_id}/candidates/{candidate_id}/evaluate",
        json={"stage": "first_round", "interview_notes_text": "Hire. Clear communication. Strong technically."},
    )
    assert eval_response.status_code == 200
    payload = eval_response.json()
    assert payload["stage"] == "first_round"
    assert payload["decision"] in {"proceed_to_second_round", "hold", "reject"}
    assert "explainability" in payload
    assert "conflict_analysis" in payload

    detail_response = client.get(f"/jobs/{job_id}/candidates/{candidate_id}")
    assert detail_response.status_code == 200
    assert len(detail_response.json()["evaluations"]) == 2


def test_feedback_aggregation_and_conflict_detection(monkeypatch, tmp_path) -> None:
    pdf_path = tmp_path / "conflict_candidate.pdf"
    build_sample_pdf(pdf_path)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_id, candidate_id = create_job_and_candidate(client, pdf_path)

    client.post(f"/jobs/{job_id}/candidates/{candidate_id}/stage", json={"target_stage": "first_round"})
    first = client.post(
        f"/jobs/{job_id}/candidates/{candidate_id}/feedback",
        json={
            "stage": "first_round",
            "interviewer_name": "Interviewer 1",
            "raw_notes": "Strong hire. Clear communication. Strong technically.",
        },
    )
    second = client.post(
        f"/jobs/{job_id}/candidates/{candidate_id}/feedback",
        json={
            "stage": "first_round",
            "interviewer_name": "Interviewer 2",
            "raw_notes": "Reject. Weak technically. Unclear communication. Concern about domain fit.",
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200

    feedback_response = client.get(f"/jobs/{job_id}/candidates/{candidate_id}/feedback")
    assert feedback_response.status_code == 200
    aggregates = feedback_response.json()["aggregates"]
    assert aggregates[0]["feedback_count"] == 2
    assert aggregates[0]["conflict_analysis"]["has_conflict"] is True

    eval_response = client.post(
        f"/jobs/{job_id}/candidates/{candidate_id}/evaluate",
        json={"stage": "first_round"},
    )
    assert eval_response.status_code == 200
    assert eval_response.json()["conflict_analysis"]["has_conflict"] is True


def test_shortlist_generation_and_manual_priority(monkeypatch, tmp_path) -> None:
    strong_pdf = tmp_path / "strong_workflow.pdf"
    weak_pdf = tmp_path / "weak_workflow.pdf"
    build_sample_pdf(strong_pdf, include_sql=True)
    build_sample_pdf(weak_pdf, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_id, strong_id = create_job_and_candidate(client, strong_pdf)

    weak_response = client.post(
        f"/jobs/{job_id}/candidates",
        files={"resume": (weak_pdf.name, weak_pdf.read_bytes(), "application/pdf")},
        data={"name": "Candidate B"},
    )
    weak_id = weak_response.json()["candidate_id"]

    client.post(f"/jobs/{job_id}/candidates/{strong_id}/evaluate", json={"stage": "initial_screen"})
    client.post(f"/jobs/{job_id}/candidates/{weak_id}/evaluate", json={"stage": "initial_screen"})

    generated = client.post(f"/jobs/{job_id}/shortlist/generate")
    assert generated.status_code == 200
    assert generated.json()["items"]

    prioritized = client.post(
        f"/jobs/{job_id}/shortlist/{weak_id}",
        json={"shortlist_priority": 1},
    )
    assert prioritized.status_code == 200
    assert prioritized.json()["items"][0]["candidate_id"] == weak_id

    removed = client.delete(f"/jobs/{job_id}/shortlist/{weak_id}")
    assert removed.status_code == 200
    assert all(item["candidate_id"] != weak_id for item in removed.json()["items"])


def test_candidate_comparison_and_invalid_stage(monkeypatch, tmp_path) -> None:
    pdf_a = tmp_path / "compare_a.pdf"
    pdf_b = tmp_path / "compare_b.pdf"
    build_sample_pdf(pdf_a, include_sql=True)
    build_sample_pdf(pdf_b, include_sql=False)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_id, candidate_a = create_job_and_candidate(client, pdf_a)
    second_candidate = client.post(
        f"/jobs/{job_id}/candidates",
        files={"resume": (pdf_b.name, pdf_b.read_bytes(), "application/pdf")},
        data={"name": "Candidate B", "current_stage": "first_round"},
    )
    candidate_b = second_candidate.json()["candidate_id"]

    client.post(f"/jobs/{job_id}/candidates/{candidate_a}/stage", json={"target_stage": "first_round"})
    client.post(
        f"/jobs/{job_id}/candidates/{candidate_a}/feedback",
        json={"stage": "first_round", "interviewer_name": "One", "raw_notes": "Hire. Strong technically."},
    )
    client.post(
        f"/jobs/{job_id}/candidates/{candidate_b}/feedback",
        json={"stage": "first_round", "interviewer_name": "Two", "raw_notes": "Hold. Clear communication but concern on SQL."},
    )
    client.post(f"/jobs/{job_id}/candidates/{candidate_a}/evaluate", json={"stage": "first_round"})
    client.post(f"/jobs/{job_id}/candidates/{candidate_b}/evaluate", json={"stage": "first_round"})

    compare = client.post(
        f"/jobs/{job_id}/compare",
        json={"candidate_ids": [candidate_a, candidate_b], "stage": "first_round"},
    )
    assert compare.status_code == 200
    payload = compare.json()
    assert len(payload["comparisons"]) == 2
    assert payload["comparative_summary"]
    assert "explainability_summary" in payload["comparisons"][0]

    invalid = client.post(
        f"/jobs/{job_id}/compare",
        json={"candidate_ids": [candidate_a, candidate_b], "stage": "initial_screen"},
    )
    assert invalid.status_code == 400


def test_stage_move_creates_evaluation_for_compare(monkeypatch, tmp_path) -> None:
    pdf_a = tmp_path / "move_compare_a.pdf"
    pdf_b = tmp_path / "move_compare_b.pdf"
    build_sample_pdf(pdf_a, include_sql=True)
    build_sample_pdf(pdf_b, include_sql=True)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_id, candidate_a = create_job_and_candidate(client, pdf_a)
    second_candidate = client.post(
        f"/jobs/{job_id}/candidates",
        files={"resume": (pdf_b.name, pdf_b.read_bytes(), "application/pdf")},
        data={"name": "Candidate B"},
    )
    candidate_b = second_candidate.json()["candidate_id"]

    move_a = client.post(f"/jobs/{job_id}/candidates/{candidate_a}/stage", json={"target_stage": "first_round"})
    move_b = client.post(f"/jobs/{job_id}/candidates/{candidate_b}/stage", json={"target_stage": "first_round"})
    assert move_a.status_code == 200
    assert move_b.status_code == 200
    assert move_a.json()["latest_evaluation"]["stage"] == "first_round"
    assert move_b.json()["latest_evaluation"]["stage"] == "first_round"

    compare = client.post(
        f"/jobs/{job_id}/compare",
        json={"candidate_ids": [candidate_a, candidate_b], "stage": "first_round"},
    )
    assert compare.status_code == 200
    assert len(compare.json()["comparisons"]) == 2


def test_cross_job_comparison_is_rejected_cleanly(monkeypatch, tmp_path) -> None:
    pdf_a = tmp_path / "job1.pdf"
    pdf_b = tmp_path / "job2.pdf"
    build_sample_pdf(pdf_a)
    build_sample_pdf(pdf_b)
    client = build_client(monkeypatch, FakeOllamaClient)
    job_one, candidate_one = create_job_and_candidate(client, pdf_a)
    job_two, candidate_two = create_job_and_candidate(client, pdf_b)

    client.post(f"/jobs/{job_one}/candidates/{candidate_one}/stage", json={"target_stage": "first_round"})
    client.post(f"/jobs/{job_one}/candidates/{candidate_one}/evaluate", json={"stage": "first_round", "interview_notes_text": "Hire. Strong technically."})

    response = client.post(
        f"/jobs/{job_one}/compare",
        json={"candidate_ids": [candidate_one, candidate_two], "stage": "first_round"},
    )

    assert response.status_code in {400, 404}
