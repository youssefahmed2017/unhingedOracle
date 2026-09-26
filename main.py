import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

HISTORY_PATH = Path(__file__).parent / "oracle_history.jsonl"

VERDICTS = [
    "ABSOLUTELY. Do it before you finish reading this sentence.",
    "No. Not now, not ever, not in this or any adjacent timeline.",
    "Yes, but you will regret it in exactly 3 to 5 business days.",
    "The universe is indifferent, but I am not: go for it.",
    "This is, statistically, the worst idea you've had all week.",
    "Obviously yes. I'm honestly offended you asked.",
    "No. Sit with that feeling for a second. Good. Now still no.",
    "Flip a coin, then ignore the coin and do this instead. Yes.",
    "I've run the numbers. There are no numbers. Do it anyway.",
    "Absolutely not, and frankly I'm concerned you considered it.",
    "Yes, if only to see what happens. Chaos has value.",
    "No — but ask me again in an hour with more confidence.",
    "The stars, the tea leaves, and my gut all say yes.",
    "A resounding, echoing, table-slamming NO.",
    "Yes. This is the one good decision you'll make this month.",
]

CONFIDENCE_FLAVOR = [
    "with 0% supporting evidence and 100% conviction",
    "backed by absolutely nothing but vibes",
    "based on a dream I had about you",
    "verified by a focus group of one (me)",
    "cross-referenced with zero credible sources",
    "calculated using advanced feelings-based mathematics",
    "confirmed by the way the light hit my screen just now",
]

ESCALATIONS = [
    "Asking again won't change my answer, but go ahead.",
    "You've asked this before. The answer has gotten MORE certain, not less.",
    "I admire the persistence. The verdict remains unmoved.",
    "At this point you're not asking me, you're asking the void. The void agrees with me.",
]

# Ordered from calmest to least calm. The Oracle only ever moves forward through this list.
MOODS = [
    {
        "name": "smug",
        "style": "bold magenta",
        "border": "magenta",
        "lines": [
            "I am, as always, delighted to be consulted.",
            "Ask away. I live for this.",
        ],
    },
    {
        "name": "dramatic",
        "style": "bold red",
        "border": "red",
        "lines": [
            "Every question you bring me now feels like the climax of a tragedy.",
            "The weight of your indecision grows heavier with each question.",
        ],
    },
    {
        "name": "tired",
        "style": "bold yellow",
        "border": "yellow",
        "lines": [
            "I am, quite frankly, exhausted by your capacity for uncertainty.",
            "I used to enjoy this. Now I mostly sigh.",
        ],
    },
    {
        "name": "unhinged",
        "style": "bold bright_red",
        "border": "bright_red",
        "lines": [
            "I HAVE SEEN THE END OF ALL YOUR TIMELINES AND THEY ALL INVOLVE YOU ASKING ME MORE QUESTIONS.",
            "THERE IS NO WRONG ANSWER. THERE IS ALSO NO RIGHT ANSWER. THERE IS ONLY MORE ASKING.",
        ],
    },
]

MOOD_THRESHOLDS = [0, 3, 6, 9]  # total questions needed to be eligible for each mood index

# Each entry: (keywords that must ALL appear in the lowercased question, roast line)
ROASTS = [
    (["one week", "learn"], "One WEEK? You're not learning that, you're speed-running a nervous breakdown."),
    (["one day"], "One day. Sure. And I'll become a licensed astronaut by dinner."),
    (["should i", "or"], "'This or that' — the eternal cry of someone who already knows the answer and wants permission."),
    (["everything"], "'Everything', huh. Bold of you to assume time is real."),
    (["quit my job"], "Big career-advice energy from the same person asking a magic oracle for life decisions."),
    (["girlfriend", "boyfriend", "text them", "text him", "text her"], "Ah yes, matters of the heart, decided by a cursed terminal script. Iconic."),
    (["c++", "suffering", "suffer"], "Choosing suffering and then asking if you should suffer more. Bold consistency."),
    (["ai", "ml", "machine learning", "deep learning", "neural network"], "Trying to become an AI expert overnight so you can ask ME, an AI, whether you should. The irony is not lost on me."),
    (["diet", "gym", "workout"], "New week, new plan, same couch. We both know how this goes."),
    (["crypto", "bitcoin", "invest"], "Ah, financial advice. From an oracle. Powered by random.choice(). Godspeed."),
    (["should i", "quit"], "Notice how you're not asking 'should I keep going' — you already know."),
    (["3am", "3 am", "at night", "can't sleep"], "Nothing good has ever been decided at this hour, and yet here you are."),
    (["rewrite", "refactor", "from scratch"], "Ah, the developer's favorite form of procrastination: rewriting instead of shipping."),
    (["is it too late"], "It is never too late, except for the fourteen other times you asked me this exact question."),
    (["startup", "quit my job", "start a business"], "A startup idea AND a magic 8-ball for a business plan. This tracks."),
    (["procrastinat"], "Asking an oracle whether to stop procrastinating is, itself, procrastination. Chef's kiss."),
    (["tattoo"], "Permanent decisions, sourced from a script that runs on random.choice(). What could go wrong."),
    (["reply to my ex", "text my ex", "my ex"], "Every civilization has fallen for less. Proceed with extreme caution, or don't proceed at all."),
]


def _contains_keyword(text: str, keyword: str) -> bool:
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def find_roast(question: str) -> str | None:
    q = question.lower()
    matches = [
        roast
        for keywords, roast in ROASTS
        if all(_contains_keyword(q, k) for k in keywords)
    ]
    if matches:
        return random.choice(matches)
    return None


def load_history() -> dict[str, list[dict]]:
    history: dict[str, list[dict]] = {}
    if not HISTORY_PATH.exists():
        return history
    with HISTORY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            history.setdefault(record["key"], []).append(record)
    return history


def append_history(key: str, question: str, verdict: str, mood: str) -> None:
    record = {
        "key": key,
        "question": question,
        "verdict": verdict,
        "mood": mood,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def advance_mood(mood_index: int, total_asked: int) -> int:
    """Mood only ever moves forward, and only once the session has earned it."""
    next_index = mood_index + 1
    if next_index >= len(MOODS):
        return mood_index
    if total_asked >= MOOD_THRESHOLDS[next_index] and random.random() < 0.4:
        return next_index
    return mood_index


def deliver_verdict(question: str, ask_count: int, mood: dict, past_record: dict | None) -> str:
    verdict = random.choice(VERDICTS)
    flavor = random.choice(CONFIDENCE_FLAVOR)
    confidence = random.randint(101, 999)
    roast = find_roast(question)

    with console.status(f"[{mood['style']}]The Oracle contemplates your question...", spinner="dots"):
        time.sleep(1.1)

    body = Text()
    body.append(f'"{question.strip()}"\n\n', style="italic dim")

    if roast:
        body.append(roast + "\n\n", style="bold yellow")

    body.append(">> ", style=mood["style"])
    body.append(verdict + "\n", style="bold white")
    body.append(f"   ({flavor}, confidence: {confidence}%)", style="dim cyan")

    if ask_count > 1:
        body.append(f"\n   {random.choice(ESCALATIONS)}", style="bold red")
    elif past_record is not None:
        when = datetime.fromisoformat(past_record["timestamp"]).strftime("%b %d")
        body.append(
            f"\n   I recall you asking this on {when}. My answer then was: "
            f"\"{past_record['verdict']}\" — has anything actually changed?",
            style="bold green",
        )

    body.append(f"\n   [{mood['name'].upper()}] {random.choice(mood['lines'])}", style=mood["style"])

    console.print(Panel(
        body,
        border_style=mood["border"],
        title=f"[bold]The Verdict ({mood['name']})[/bold]",
        title_align="left",
    ))
    console.print()

    return verdict


ORACLE_ART = r"""
        .-""""""-.
      .'          '.
     |    o    o    |
     :               :
     |    .----.     |
      '.          .'
        '-......-'
"""


def main() -> None:
    console.print(f"[bold magenta]{ORACLE_ART}[/bold magenta]")
    console.print("[bold]Welcome to THE ORACLE.[/bold]")
    console.print("Ask an over-thought question. Receive a dramatically overconfident answer.")
    console.print("Type [bold]quit[/bold] to release the Oracle back into the void.\n")

    history = load_history()
    ask_counts: dict[str, int] = {}
    total_asked = 0
    mood_index = 0

    while True:
        try:
            question = console.input("[bold cyan]Your question:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]The Oracle vanishes in a puff of smoke.[/dim]")
            sys.exit(0)

        if not question:
            console.print("[red]The Oracle requires an actual question, not silence.[/red]\n")
            continue
        if question.lower() in {"quit", "exit", "q"}:
            console.print("[dim]The Oracle vanishes in a puff of smoke.[/dim]")
            break

        key = question.lower()
        ask_counts[key] = ask_counts.get(key, 0) + 1
        total_asked += 1

        past_record = None
        if ask_counts[key] == 1 and key in history:
            past_record = history[key][-1]

        new_mood_index = advance_mood(mood_index, total_asked)
        if new_mood_index != mood_index:
            mood_index = new_mood_index
            new_mood = MOODS[mood_index]
            console.print(f"[{new_mood['style']}]... the Oracle's mood shifts to {new_mood['name'].upper()} ...[/{new_mood['style']}]\n")

        mood = MOODS[mood_index]
        verdict = deliver_verdict(question, ask_counts[key], mood, past_record)
        append_history(key, question, verdict, mood["name"])
        history.setdefault(key, []).append({"verdict": verdict, "timestamp": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    main()
