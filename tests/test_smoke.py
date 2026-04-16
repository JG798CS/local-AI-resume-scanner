from __future__ import annotations

from pathlib import Path


def test_scaffold_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    required = [
        "app.py",
        "parser.py",
        "chunking.py",
        "rules.py",
        "llm.py",
        "scoring.py",
        "schemas.py",
        "prompts.py",
        "department_rules.yaml",
        "requirements.txt",
        "README.md",
    ]
    for file_name in required:
        assert (root / file_name).exists()
