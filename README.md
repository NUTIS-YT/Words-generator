# Words Generator

Cross-platform desktop application for generating unique words with an LLM through an OpenAI-compatible Chat Completions API.

> **Current status:** first development slice. Project storage, API integration, deduplication engine, background worker and basic PySide6 interface are implemented. See plan.md for the full roadmap.

## Features in the initial implementation

- Create and open local projects.
- Store accepted words in words.txt (UTF-8, one word per line).
- Connect to OpenAI-compatible chat completion endpoints.
- Fetch available models from the models endpoint.
- Configure language, part of speech, editable system prompt and sampling parameters.
- Reject malformed responses and duplicate words locally.
- Run generation in a background Qt thread with pause/resume/stop controls.
- Save a JSONL session log and a checkpoint after every accepted word.
- Keep API keys out of project files and use the operating-system credential store when available.

## Requirements

- Python 3.12+
- uv
- A reachable OpenAI-compatible API endpoint and a model that supports Chat Completions.

## Setup

    uv sync --extra dev
    uv run words-generator

Or run the module directly:

    uv run python -m words_generator

## Project format

    MyProject/
    ├── project.json
    ├── words.txt
    ├── history/
    ├── state/
    └── backups/

words.txt contains only accepted words, one per line. API credentials are stored separately through the system credential backend; they are never written to project files.

## API setup

Set the Base URL to the API root or its /v1 prefix, enter the model identifier and (when required) API key, then use Test connection. For example, both http://localhost:8080 and http://localhost:8080/v1 are accepted.

The client uses GET /models and POST /chat/completions.

## Important validation note

The local validator can reliably enforce the one-word response shape and deduplicate words (case-insensitively after Unicode normalization). Language and part-of-speech correctness are requested in the prompt but cannot be conclusively proven by a generic regular expression. Strong semantic validation requires an optional dictionary, morphology package or classifier and is tracked in plan.md.

## Development

    uv sync --extra dev
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .

## License

No open-source license has been selected yet. All rights remain with the repository owner unless a license is added.
