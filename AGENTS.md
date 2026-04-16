# Resume Scanner project rules

## Goal
Build a local-AI resume scanner in Python.

## Runtime
- OS: Windows
- Python 3.11
- Local Ollama API: http://localhost:11434
- Chat model: qwen3:4b
- Embedding model: qwen3-embedding:0.6b

## Architecture
- Build a FastAPI service
- Parse resume PDFs with PyMuPDF
- Split resume text into chunks
- Compare JD bullets against resume chunks with embeddings
- Apply department rules from a YAML file
- Use the local LLM only for explanation, risk flags, and final summary
- Return structured JSON only

## Output schema
- fit_score
- decision
- matched_requirements
- missing_requirements
- risk_flags
- evidence
- summary

## Working style
- Prefer minimal, reviewable changes
- Before adding a dependency, explain why
- After each phase, run the smallest relevant verification command
- Never use cloud LLM APIs
- Keep comments brief and useful
