# Unhinged Oracle

A terminal oracle for over-thought questions. Ask it anything and it gives you a
dramatically overconfident, made-up-confidence-percentage verdict — no real
advice, no real logic, just vibes.

It also:
- roasts you if your question hits certain keyword patterns (crypto, tattoos, your ex, learning ML in a week, etc.)
- gets progressively more unhinged the longer you keep asking it things in one session
- remembers what you asked in past sessions and will call you out for asking again

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python main.py
```

Type your question and hit enter. Type `quit` (or `exit`/`q`) to leave.

Your question/verdict history is logged to `oracle_history.jsonl` in the
project folder so the Oracle can reference past sessions.
