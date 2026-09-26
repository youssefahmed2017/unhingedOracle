import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import readline  # enables Up/Down arrow-key history for input(), Unix/macOS
except ImportError:
    readline = None  # not available on stock Windows; input still works, just no arrow history

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

HISTORY_PATH = Path(__file__).parent / "oracle_history.jsonl"
INPUT_HISTORY_PATH = Path(__file__).parent / ".oracle_input_history"
INPUT_HISTORY_MAX_LINES = 1000


def load_input_history() -> None:
    """Load previously typed questions into readline so Up/Down arrows work
    across sessions too, the same way bash remembers your shell history."""
    if readline is None:
        return
    try:
        readline.read_history_file(INPUT_HISTORY_PATH)
    except FileNotFoundError:
        pass
    readline.set_history_length(INPUT_HISTORY_MAX_LINES)


def save_input_history() -> None:
    if readline is None:
        return
    try:
        readline.write_history_file(INPUT_HISTORY_PATH)
    except OSError:
        pass

# Each entry: (verdict text, lean) where lean is +1 (yes-leaning), -1 (no-leaning),
# or 0 (wildcard/chaotic — works either way, favored when the question itself is chaotic).
VERDICTS = [
    ("ABSOLUTELY. Do it before you finish reading this sentence.", 1),
    ("No. Not now, not ever, not in this or any adjacent timeline.", -1),
    ("Yes, but you will regret it in exactly 3 to 5 business days.", 1),
    ("The universe is indifferent, but I am not: go for it.", 1),
    ("This is, statistically, the worst idea you've had all week.", -1),
    ("Obviously yes. I'm honestly offended you asked.", 1),
    ("No. Sit with that feeling for a second. Good. Now still no.", -1),
    ("Flip a coin, then ignore the coin and do this instead. Yes.", 0),
    ("I've run the numbers. There are no numbers. Do it anyway.", 0),
    ("Absolutely not, and frankly I'm concerned you considered it.", -1),
    ("Yes, if only to see what happens. Chaos has value.", 0),
    ("No — but ask me again in an hour with more confidence.", -1),
    ("The stars, the tea leaves, and my gut all say yes.", 1),
    ("A resounding, echoing, table-slamming NO.", -1),
    ("Yes. This is the one good decision you'll make this month.", 1),
]

# Words that nudge the Oracle's internal "opinion" toward yes or no.
POSITIVE_CUES = ["should i", "can i", "finally", "ready", "want to", "dream", "excited", "worth it", "always wanted"]
NEGATIVE_CUES = ["shouldn't", "bad idea", "stupid", "regret", "scared", "afraid", "risky", "warned", "in debt", "no money", "worried"]

# Topics the Oracle considers volatile — they push it toward wildcard/chaotic verdicts.
RISK_CUES = ["tattoo", "crypto", "bitcoin", "invest", "quit my job", "rent", "loan", "gamble", "bet",
             "my ex", "surgery", "startup", "move to", "elope", "propose", "resign"]

# Words that signal "I need an answer RIGHT NOW" — the Oracle reads that as high-stakes.
URGENCY_CUES = ["now", "today", "tonight", "asap", "immediately", "right now", "3am", "3 am", "this second"]

# Mood multiplies each lean's weight differently — e.g. a tired Oracle leans harsher/more negative.
MOOD_LEAN_BIAS = {
    "smug": {1: 1.0, -1: 1.0, 0: 1.0},
    "dramatic": {1: 1.3, -1: 1.3, 0: 0.8},
    "tired": {1: 0.7, -1: 1.4, 0: 0.9},
    "unhinged": {1: 1.0, -1: 1.0, 0: 1.8},
}

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

# --- The roast cascade ---
# Each entry: (terms, roast line). A "term" is either a single required keyword,
# or a tuple of alternatives — any ONE of which satisfies that term (an "or" group,
# same idea as a CSS selector list). ALL terms in a rule must be satisfied to match.
#
# When more than one rule matches the same question, the rule with the MOST terms
# wins (more terms = more specific = higher priority), exactly like CSS specificity:
# a rule that requires two conditions beats one that only requires one, even though
# both technically match. Ties are broken randomly.
ROASTS = [
    (["one week", "learn"], "One WEEK? You're not learning that, you're speed-running a nervous breakdown."),
    (["one day"], "One day. Sure. And I'll become a licensed astronaut by dinner."),
    (["should i", "or"], "'This or that' — the eternal cry of someone who already knows the answer and wants permission."),
    (["everything"], "'Everything', huh. Bold of you to assume time is real."),
    (["quit my job"], "Big career-advice energy from the same person asking a magic oracle for life decisions."),
    ([("girlfriend", "boyfriend", "text them", "text him", "text her")], "Ah yes, matters of the heart, decided by a cursed terminal script. Iconic."),
    (["c++", ("suffering", "suffer")], "Choosing suffering and then asking if you should suffer more. Bold consistency."),
    ([("ai", "ml", "machine learning", "deep learning", "neural network")], "Trying to become an AI expert overnight so you can ask ME, an AI, whether you should. The irony is not lost on me."),
    ([("diet", "gym", "workout")], "New week, new plan, same couch. We both know how this goes."),
    ([("crypto", "bitcoin", "invest")], "Ah, financial advice. From an oracle. Powered by random.choice(). Godspeed."),
    (["crypto", ("now", "today", "tonight", "asap")], "You want to ape into crypto RIGHT NOW? At least the panic-selling will be quick."),
    (["should i", "quit"], "Notice how you're not asking 'should I keep going' — you already know."),
    ([("3am", "3 am", "at night", "can't sleep")], "Nothing good has ever been decided at this hour, and yet here you are."),
    ([("rewrite", "refactor", "from scratch")], "Ah, the developer's favorite form of procrastination: rewriting instead of shipping."),
    (["is it too late"], "It is never too late, except for the fourteen other times you asked me this exact question."),
    ([("startup", "start a business")], "A startup idea AND a magic 8-ball for a business plan. This tracks."),
    (["procrastinat"], "Asking an oracle whether to stop procrastinating is, itself, procrastination. Chef's kiss."),
    (["tattoo"], "Permanent decisions, sourced from a script that runs on random.choice(). What could go wrong."),
    (["tattoo", ("now", "tonight", "asap")], "Getting a tattoo RIGHT NOW is peak 'I'll regret this by Tuesday' energy."),
    ([("reply to my ex", "text my ex", "my ex")], "Every civilization has fallen for less. Proceed with extreme caution, or don't proceed at all."),
]


def _contains_keyword(text: str, keyword: str) -> bool:
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _term_matches(question: str, term) -> bool:
    if isinstance(term, tuple):
        return any(_contains_keyword(question, alt) for alt in term)
    return _contains_keyword(question, term)


def _count_cues(text: str, cues: list[str]) -> int:
    return sum(len(re.findall(rf"\b{re.escape(cue)}\b", text)) for cue in cues)


def analyze_question(question: str) -> dict[str, int]:
    """Extract simple rule-based signals from the question — no ML, just word counting."""
    q = question.lower()
    positive = _count_cues(q, POSITIVE_CUES)
    negative = _count_cues(q, NEGATIVE_CUES)
    return {
        "polarity": positive - negative,
        "risk": _count_cues(q, RISK_CUES),
        "urgency": _count_cues(q, URGENCY_CUES),
    }


def pick_verdict(signals: dict[str, int], mood_name: str) -> str:
    """Weighted choice, not uniform: the Oracle's 'opinion' leans toward what the
    question's wording suggests, and its current mood skews which lean it favors."""
    bias = MOOD_LEAN_BIAS[mood_name]
    polarity = signals["polarity"]
    weights = []
    texts = []
    for text, lean in VERDICTS:
        if lean == 0:
            weight = 1.0 + signals["risk"] * 1.2
        elif polarity != 0 and (lean > 0) == (polarity > 0):
            weight = 1.0 + min(abs(polarity), 4) * 1.5
        elif polarity != 0:
            weight = 0.4  # opposes the question's apparent lean — rarer, not impossible
        else:
            weight = 1.0
        weights.append(weight * bias[lean])
        texts.append(text)
    return random.choices(texts, weights=weights, k=1)[0]


def pick_confidence(signals: dict[str, int]) -> int:
    """Confidence scales with how much 'signal' the question gave the Oracle to
    work with — a question loaded with cues gets a louder (not more accurate) answer."""
    signal_strength = abs(signals["polarity"]) * 50 + signals["risk"] * 40 + signals["urgency"] * 70
    confidence = 200 + signal_strength + random.randint(-40, 60)
    return max(101, min(confidence, 999))


# --- Question-type templates: "how"/"when"/"who"/"what" questions don't fit a
# yes/no answer, so each gets its own response shape instead of being forced
# through the yes/no engine. ---

HOW_TOPIC_TEMPLATES = [
    "One does not simply '{topic}'. One suffers, then figures it out by accident.",
    "You '{topic}' the same way you do everything: badly at first, then out of spite.",
    "Carefully. Or don't. '{topic}' has a way of happening whether you plan it or not.",
]
HOW_GENERIC = [
    "Step 1: don't. Step 2: there is no step 2.",
    "You Google it at 2am, panic, then do the first Stack Overflow answer verbatim.",
    "The same way you do everything: by overthinking it first and winging it after.",
]

WHEN_RESPONSES = [
    "Right now. You've been stalling long enough.",
    "Never. Let it go.",
    "When Mercury is no longer in retrograde, which is to say, eventually, probably.",
    "In exactly 3 to 5 business days. The Oracle's calendar is inflexible.",
    "The moment you stop asking oracles and just decide.",
]

WHO_RESPONSES = [
    "Whoever said yes first. Availability beats suitability every time.",
    "Not the person you're thinking of. You know exactly who I mean.",
    "Yourself. It's always been yourself.",
    "The one person you haven't considered, out of spite.",
    "Ask three people, ignore all three, and go with your gut anyway.",
]

WHAT_RESPONSES = [
    "Something. Anything. The specifics were never really the point.",
    "Whatever you were already leaning toward before you asked me.",
    "Nothing, for now. Sit in the discomfort a little longer.",
    "The thing you're avoiding. You know the one.",
    "Consult a Markov chain built from your own indecision. Oh wait — you did.",
]

_FILLER_PREFIX = re.compile(r"^(ok(ay)?[,]?\s+|so[,]?\s+|um[,]?\s+|uh[,]?\s+|like[,]?\s+)+", re.IGNORECASE)

_HOW_TOPIC_PATTERNS = [
    re.compile(r"how (?:do|does|did|should|can|could) i\s+(.*)", re.IGNORECASE),
    re.compile(r"how to\s+(.*)", re.IGNORECASE),
]


def _starts_with(word: str):
    def matcher(question: str) -> bool:
        return _FILLER_PREFIX.sub("", question.strip().lower()).startswith(word)
    return matcher


# --- The question-type cascade ---
# Each entry: (type name, specificity, matcher). Every rule whose matcher returns
# True is a candidate; the highest-specificity candidate wins. "or" outranks the
# shape detectors because a real "X or Y" question is a stronger, more specific
# signal than a leading word — and "yesno" (specificity 0) always matches, so it
# only ever wins when nothing more specific fired. Adding a new question shape
# later just means adding one more (name, specificity, matcher) row here.
QUESTION_TYPE_RULES = [
    ("or", 100, lambda q: extract_or_choice(q) is not None),
    ("how", 50, _starts_with("how")),
    ("when", 50, _starts_with("when")),
    ("who", 50, _starts_with("who")),
    ("what", 50, _starts_with("what")),
    ("yesno", 0, lambda q: True),
]


def resolve_question_type(question: str) -> str:
    """Rule-based intent detection — no model, just picking the most specific
    matching rule from the cascade above."""
    matches = [(name, spec) for name, spec, matcher in QUESTION_TYPE_RULES if matcher(question)]
    top_specificity = max(spec for _, spec in matches)
    winners = [name for name, spec in matches if spec == top_specificity]
    return winners[0] if len(winners) == 1 else random.choice(winners)


def extract_topic(question: str) -> str | None:
    for pattern in _HOW_TOPIC_PATTERNS:
        match = pattern.search(question)
        if match:
            topic = match.group(1).strip(" ?.!")
            if topic:
                return topic
    return None


def pick_typed_verdict(qtype: str, question: str) -> str:
    if qtype == "how":
        topic = extract_topic(question)
        if topic:
            return random.choice(HOW_TOPIC_TEMPLATES).format(topic=topic)
        return random.choice(HOW_GENERIC)
    if qtype == "when":
        return random.choice(WHEN_RESPONSES)
    if qtype == "who":
        return random.choice(WHO_RESPONSES)
    return random.choice(WHAT_RESPONSES)


# --- Markov chain: builds new sentences word-by-word from the Oracle's own
# existing lines, so output isn't limited to picking a fixed line verbatim. ---

def _build_markov_chain(sentences: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    transitions: dict[str, list[str]] = {}
    starters: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) < 3:
            continue
        starters.append(words[0])
        for current_word, next_word in zip(words, words[1:]):
            transitions.setdefault(current_word, []).append(next_word)
    return transitions, starters


def _generate_markov_line(transitions: dict[str, list[str]], starters: list[str], max_words: int = 18) -> str:
    if not starters:
        return ""
    word = random.choice(starters)
    words = [word]
    for _ in range(max_words - 1):
        options = transitions.get(word)
        if not options:
            break
        word = random.choice(options)
        words.append(word)
        if word.endswith((".", "!", "?")) and len(words) > 4:
            break
    text = " ".join(words)
    text = text[0].upper() + text[1:]
    if not text.endswith((".", "!", "?")):
        text += "."
    return text


_MARKOV_CORPUS = (
    [text for text, _ in VERDICTS]
    + HOW_GENERIC + WHEN_RESPONSES + WHO_RESPONSES + WHAT_RESPONSES
    + ESCALATIONS
    + [roast for _, roast in ROASTS]
    + [line for mood in MOODS for line in mood["lines"]]
)

_MARKOV_TRANSITIONS, _MARKOV_STARTERS = _build_markov_chain(_MARKOV_CORPUS)


def generate_markov_line() -> str:
    return _generate_markov_line(_MARKOV_TRANSITIONS, _MARKOV_STARTERS)

_OR_STOPWORDS = {"not", "nah", "what", "something", "else", "this", "that", "it", "anything"}

BETWEEN_REASONS = [
    "{loser} was never really in the running.",
    "I don't know why you're pretending this was a real dilemma.",
    "the void whispered its name first.",
    "{loser} can wait for a version of you with more free time.",
    "I flipped a coin that only has '{winner}' written on both sides.",
    "the math is the math. I don't make the rules, I just invented them.",
]


def extract_or_choice(question: str) -> tuple[str, str] | None:
    """Detect a genuine 'X or Y' question and pull out the two options being weighed —
    these need an actual pick between them, not a yes/no verdict."""
    match = re.search(r"\bor\b", question, flags=re.IGNORECASE)
    if not match:
        return None

    left_words = re.findall(r"[A-Za-z0-9+#.]+", question[:match.start()])
    right_words = re.findall(r"[A-Za-z0-9+#.]+", question[match.end():])
    if not left_words or not right_words:
        return None

    option_a, option_b = left_words[-1], right_words[0]
    if option_a.lower() in _OR_STOPWORDS or option_b.lower() in _OR_STOPWORDS:
        return None
    if option_a.lower() == option_b.lower():
        return None
    return option_a, option_b


def _word_weight(word: str) -> int:
    """A deterministic 'quality' score for a word — pure arithmetic on its letters,
    not randomness — so the same option always starts from the same footing."""
    return sum(ord(c) - ord("a") + 1 for c in word.lower() if c.isalpha()) or len(word)


def pick_between(option_a: str, option_b: str) -> tuple[str, str, str, int]:
    score_a = _word_weight(option_a) + random.randint(-6, 6)
    score_b = _word_weight(option_b) + random.randint(-6, 6)
    winner, loser = (option_a, option_b) if score_a >= score_b else (option_b, option_a)
    reason = random.choice(BETWEEN_REASONS).format(winner=winner, loser=loser)
    return winner, loser, reason, abs(score_a - score_b)


def find_roast(question: str) -> str | None:
    """Every ROASTS rule that fully matches is a candidate; the most specific
    (most terms) one wins the cascade. Ties among equally specific rules are
    broken randomly."""
    q = question.lower()
    matches = [
        (len(terms), roast)
        for terms, roast in ROASTS
        if all(_term_matches(q, term) for term in terms)
    ]
    if not matches:
        return None
    top_specificity = max(specificity for specificity, _ in matches)
    winners = [roast for specificity, roast in matches if specificity == top_specificity]
    return random.choice(winners)


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
    signals = analyze_question(question)
    roast = find_roast(question)
    qtype = resolve_question_type(question)

    if qtype == "or":
        winner, loser, reason, margin = pick_between(*extract_or_choice(question))
        verdict = f"{winner[0].upper()}{winner[1:]}."
        extra_line = f"({reason})"
        confidence = max(101, min(200 + margin * 15 + random.randint(-30, 40), 999))
    elif qtype in ("how", "when", "who", "what"):
        verdict = pick_typed_verdict(qtype, question)
        extra_line = None
        confidence = pick_confidence(signals)
    else:
        verdict = pick_verdict(signals, mood["name"])
        extra_line = None
        confidence = pick_confidence(signals)

    # The unhinged Oracle increasingly answers in freshly generated nonsense
    # instead of its usual lines — occasionally elsewhere too, for flavor.
    markov_chance = 0.6 if mood["name"] == "unhinged" else 0.12
    markov_line = generate_markov_line() if random.random() < markov_chance else ""

    flavor = random.choice(CONFIDENCE_FLAVOR)

    with console.status(f"[{mood['style']}]The Oracle contemplates your question...", spinner="dots"):
        time.sleep(1.1)

    body = Text()
    body.append(f'"{question.strip()}"\n\n', style="italic dim")

    if roast:
        body.append(roast + "\n\n", style="bold yellow")

    body.append(">> ", style=mood["style"])
    body.append(verdict + "\n", style="bold white")
    if extra_line:
        body.append(f"   {extra_line}\n", style="italic dim")
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

    if markov_line:
        body.append(f"\n   the Oracle mutters: \"{markov_line}\"", style="italic bold blue")

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
    console.print("Ask an over-thought question/a decision. Receive a dramatically overconfident answer.")
    console.print("Type [bold]quit[/bold] to release the Oracle back into the void.\n")

    load_input_history()

    history = load_history()
    ask_counts: dict[str, int] = {}
    total_asked = 0
    mood_index = 0

    while True:
        try:
            question = console.input("[bold cyan]Your question:[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]The Oracle vanishes in a puff of smoke.[/dim]")
            save_input_history()
            sys.exit(0)

        if not question:
            console.print("[red]The Oracle requires an actual question, not silence.[/red]\n")
            continue
        if question.lower() in {"quit", "exit", "q"}:
            console.print("[dim]The Oracle vanishes in a puff of smoke.[/dim]")
            save_input_history()
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
