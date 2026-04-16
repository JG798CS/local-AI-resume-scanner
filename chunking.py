from __future__ import annotations

from schemas import ResumeChunk

SECTION_ALIASES = {
    "summary": "summary",
    "professional summary": "summary",
    "experience": "experience",
    "work experience": "experience",
    "work history": "experience",
    "projects": "projects",
    "project experience": "projects",
    "education": "education",
    "skills": "skills",
    "technical skills": "skills",
    "certifications": "certifications",
}


def chunk_resume_text(text: str, max_chunk_chars: int = 900) -> list[ResumeChunk]:
    lines = [line.strip() for line in text.splitlines()]
    chunks: list[ResumeChunk] = []
    current_title = "general"
    current_section = "general"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(
                ResumeChunk(
                    title=current_title,
                    section_label=current_section,
                    content=body,
                )
            )
        buffer.clear()

    for line in lines:
        if not line:
            continue
        normalized = normalize_heading(line)
        if normalized in SECTION_ALIASES:
            flush()
            current_title = line.strip(":")
            current_section = SECTION_ALIASES[normalized]
            continue

        candidate = "\n".join(buffer + [line])
        if len(candidate) > max_chunk_chars:
            flush()
        buffer.append(line)

    flush()
    if not chunks:
        return [ResumeChunk(title="general", section_label="general", content=text.strip())]
    return chunks


def normalize_heading(line: str) -> str:
    return " ".join(line.lower().strip(":").split())
