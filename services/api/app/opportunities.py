"""College coaches from public staff pages, then one email the player sends."""

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import anthropic
import httpx
from pydantic import BaseModel, ConfigDict

from app.config import Settings
from app.db import Database, new_id, utcnow
from app.errors import AppError
from app.mailer import html_body
from app.mailer import send as deliver_mail
from app.schemas import (
    ClipStats,
    CoachCardOut,
    OpportunityIn,
    OpportunityOut,
    ProgramOut,
    ProgramsIn,
    ProgramsOut,
    ReachIn,
    ReachOut,
    ReachStepOut,
    SendIn,
    SendOut,
)
from app.versions import OPPORTUNITY_PROMPT_VERSION, REACH_PROMPT_VERSION

log = logging.getLogger("secondlook.opportunities")

SEARCH_ACTOR = "apify/google-search-scraper"
CRAWL_ACTOR = "apify/website-content-crawler"
APIFY_BASE = "https://api.apify.com/v2"
PROMPT = Path(__file__).parent / "prompts" / "outreach_v1.md"
REACH_PROMPT = Path(__file__).parent / "prompts" / "reach_v1.md"
REVIEW_ID = re.compile(r"^sub_[0-9a-f]{16}$")
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
CELL_NOTE = re.compile(r"\s*\[[A-Za-z0-9]{1,3}\]")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.M)
COACH_PATH = re.compile(r"(soccer|msoc).*(coach|staff)|(coach|staff).*(soccer|msoc)", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
STOP_HEADING = ("former", "defunct", "discontinued", "see also", "references", "notes", "external links")
BANNED = ("talented", "elite", "gifted", "prospect", "deserve", "world-class", "world class", "scholarship")
LEVEL_WORDS = ("d1", "d2", "d3", "division", "naia", "juco", "odds")
BLOCKED = (
    "google.com",
    "google.co.uk",
    "youtube.com",
    "youtu.be",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "reddit.com",
    "t.co",
)
AGGREGATORS = (
    "ncsasports.org",
    "ncsasports.com",
    "collegeathletepath.com",
    "fieldlevel.com",
    "wikipedia.org",
    "maxpreps.com",
    "topdrawersoccer.com",
    "soccerwire.com",
    "hudl.com",
    "rivals.com",
    "247sports.com",
    "on3.com",
)
DC = {"d.c.", "d.c", "washington, d.c.", "washington dc", "district of columbia"}
LIST_URL = {
    "d1": "https://en.wikipedia.org/wiki/List_of_NCAA_Division_I_men%27s_soccer_programs",
    "d2": "https://en.wikipedia.org/wiki/List_of_NCAA_Division_II_men%27s_soccer_programs",
}
LEAGUE_DIVISIONS = {
    "mls_next": ("d1", "d2"),
    "ecnl": ("d1", "d2"),
    "ecnl_rl": ("d2",),
    "npl": ("d2",),
    "usys": ("d2",),
    "high_school": ("d2",),
    "club": ("d2",),
}
LEAGUE_LABEL = {
    "mls_next": "MLS NEXT",
    "ecnl": "ECNL",
    "ecnl_rl": "ECNL Regional League",
    "npl": "NPL",
    "usys": "USYS National League",
    "high_school": "high school",
    "club": "club soccer",
}
LEAGUE_RULE = {
    "mls_next": "MLS NEXT is read as NCAA Division I, then Division II.",
    "ecnl": "ECNL is read as NCAA Division I, then Division II.",
    "ecnl_rl": "ECNL Regional League is read as NCAA Division II.",
    "npl": "NPL is read as NCAA Division II.",
    "usys": "USYS National League is read as NCAA Division II.",
    "high_school": "High school is read as NCAA Division II.",
    "club": "Other club is read as NCAA Division II.",
}
LEVEL_NOTE = "Division III, NAIA and junior college lists are not read yet."
DIVISION_LABEL = {"d1": "NCAA Division I", "d2": "NCAA Division II"}
BOTH_DIVISIONS = ("d1", "d2")
PLAYER_LEVEL = {
    "mls_next": 3,
    "ecnl": 2,
    "ecnl_rl": 1,
    "npl": 1,
    "usys": 1,
    "high_school": 1,
    "club": 1,
}
TOP_CONFERENCES = {
    "atlantic coast conference",
    "big ten conference",
    "big east conference",
}
FIT_ORDER = {"fit": 0, "possible": 1, "reach": 2}
FIT_RULE = "Fit comes from the league you listed, not from this clip. It is a sorting rule, not a prediction."
STANDARD_READ = "This program is a reach from the league you listed. The clip does not change that."
EMPTY_CONTACT = {"name": None, "title": None, "email": None, "phone": None}
MORE_FOOTAGE = re.compile(r"\b(upload|send|add) more (footage|clips|video)\b", re.I)
URLISH = re.compile(r"https?://|www\.", re.I)


class SummaryDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str


class ReachStepDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    detail: str
    cost: str


class ReachDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")
    read: str
    steps: list[ReachStepDraft]


@dataclass
class CoachHit:
    school: str
    url: str
    text: str


@dataclass
class SearchResult:
    hits: list[CoachHit]
    run_ids: list[str]
    actors: list[str]


def league_divisions(league: str) -> tuple[str, ...]:
    return LEAGUE_DIVISIONS[league]


def program_level(program: dict) -> int:
    if program.get("division") != "d1":
        return 1
    conference = str(program.get("conference") or "").casefold().strip()
    if conference in TOP_CONFERENCES:
        return 3
    return 2


def fit_of(league: str, program: dict) -> str:
    gap = program_level(program) - PLAYER_LEVEL[league]
    if gap <= 0:
        return "fit"
    if gap == 1:
        return "possible"
    return "reach"


def fit_reason(league: str, program: dict, tier: str) -> str:
    division = DIVISION_LABEL[program["division"]]
    conference = program["conference"]
    listed = LEAGUE_LABEL[league]
    if tier == "reach":
        return (
            f"{division}, {conference}. Players here usually come from MLS NEXT or ECNL; "
            f"you listed {listed}."
        )
    if tier == "possible":
        return f"{division}, {conference}. One step above {listed}."
    return f"{division}, {conference}. That lines up with {listed}."


def short_name(school: str) -> str:
    match = re.search(r"\(([^)]+)\)\s*$", school)
    if match:
        part = match.group(1).split("/")[-1].strip().replace('"', "")
        if len(part) >= 3 and part.casefold() not in {"state", "private"}:
            return part
    name = re.sub(r"\s*\([^)]*\)", "", school).strip()
    for suffix in (" University", " College"):
        if name.endswith(suffix) and len(name) > len(suffix) + 3:
            return name[: -len(suffix)].strip()
    return name


def canonical_state(value: str) -> str | None:
    from app.schemas import STATES

    cleaned = " ".join(value.split())
    if cleaned in STATES:
        return cleaned
    folded = cleaned.casefold().replace("ʻ", "'")
    if folded in DC:
        return "District of Columbia"
    if folded in {"hawaii", "hawai'i"}:
        return "Hawaii"
    return None


def parse_programs(markdown: str, division: str) -> list[dict]:
    piped = _parse_pipe_tables(markdown, division)
    if piped:
        return piped
    return _parse_loose_list(markdown, division)


def _parse_pipe_tables(markdown: str, division: str) -> list[dict]:
    cut = len(markdown)
    for match in HEADING.finditer(markdown):
        title = match.group(1).casefold()
        if any(word in title for word in STOP_HEADING):
            cut = match.start()
            break
    programs: list[dict] = []
    seen: set[str] = set()
    columns: dict[str, int] | None = None
    for line in markdown[:cut].splitlines():
        if not line.strip().startswith("|"):
            columns = None
            continue
        cells = [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if not cells or all(not cell or set(cell) <= set("-: ") for cell in cells):
            continue
        folded = [cell.casefold() for cell in cells]
        if _program_header(folded):
            columns = _program_columns(folded)
            continue
        if columns is None:
            continue
        school = _cell(cells, columns["school"])
        state = canonical_state(_cell(cells, columns["state"]))
        if not school or state is None or school.casefold() in seen:
            continue
        seen.add(school.casefold())
        programs.append({
            "school": school,
            "short_name": short_name(school),
            "city": _cell(cells, columns["city"]),
            "state": state,
            "conference": _cell(cells, columns["conference"]),
            "division": division,
        })
    return programs


def _parse_loose_list(markdown: str, division: str) -> list[dict]:
    cells = _loose_cells(markdown)
    conference_at = 2 if division == "d1" else 1
    programs: list[dict] = []
    seen: set[str] = set()
    for index, cell in enumerate(cells):
        if index < 3 or index + conference_at >= len(cells) or not _state_anchor(cells, index):
            continue
        school = cells[index - 3]
        if not _school_name(school) and index >= 4 and _school_name(cells[index - 4]):
            school = cells[index - 4]
            if cells[index - 3].startswith("("):
                school = f"{school} {cells[index - 3]}"
        state = canonical_state(cell)
        if not school or state is None or school.casefold() in seen or not _school_name(school):
            continue
        seen.add(school.casefold())
        programs.append({
            "school": school,
            "short_name": short_name(school),
            "city": cells[index - 1],
            "state": state,
            "conference": cells[index + conference_at],
            "division": division,
        })
    return programs


def _loose_cells(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    start = next((index for index, line in enumerate(lines) if line.strip() in {"School", "Institution"}), None)
    if start is None:
        return []
    cells: list[str] = []
    started = False
    for line in lines[start + 1:]:
        if line.startswith("#") and any(word in line.casefold() for word in STOP_HEADING):
            break
        cleaned = _clean_cell(line)
        if not cleaned:
            continue
        if not started:
            if any(word in cleaned.casefold() for word in ("university", "college", "institute", "academy", "seminary")):
                started = True
            else:
                continue
        cells.append(cleaned)
    return cells


def _school_name(value: str) -> bool:
    folded = value.casefold()
    return any(word in folded for word in ("university", "college", "institute", "academy", "seminary"))


def _state_anchor(cells: list[str], index: int) -> bool:
    if canonical_state(cells[index]) is None:
        return False
    return index + 1 >= len(cells) or canonical_state(cells[index + 1]) is None


def first_coach_url(results: list) -> str | None:
    for row in results:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        if not url.startswith("https://"):
            continue
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        if _blocked(host) or _aggregator(host):
            continue
        if COACH_PATH.search(unquote(urlsplit(url).path)):
            return url
    return None


def staff_rows(markdown: str) -> list[dict]:
    table = _table_rows(markdown)
    if any(row["email"] for row in table):
        return table
    blocks = _block_rows(markdown)
    return blocks or table


def pick_contact(rows: list[dict], page_text: str) -> dict:
    folded = page_text.casefold()
    ranked = sorted(enumerate(rows), key=lambda item: (_rank(item[1].get("title") or ""), item[0]))
    for _, row in ranked:
        email = str(row.get("email") or "")
        if email and email.casefold() in folded:
            return {"name": row.get("name") or None, "title": row.get("title") or None, "email": email, "phone": None}
    for row in rows:
        phone = str(row.get("phone") or "")
        if phone and phone in page_text:
            return {"name": row.get("name") or None, "title": row.get("title") or None, "email": None, "phone": phone}
    return dict(EMPTY_CONTACT)


def stats_table(stats: ClipStats) -> str:
    rate = "0" if stats.tracked_s <= 0 else fmt_num(_per_minute(stats))
    rows = [
        ("Seconds tracked", fmt_num(stats.tracked_s)),
        ("Receives", str(stats.receives)),
        ("Passes", f"{stats.passes_completed} completed of {stats.passes_attempted}"),
        ("Carries", str(stats.carries)),
        ("Ball losses", str(stats.losses)),
        ("Actions a tracked minute", rate),
        ("Clips analysed", str(stats.clips)),
        ("Evidence confidence", str(stats.confidence)),
    ]
    return "\n".join(f"{label}: {value}" for label, value in rows)


def fallback_summary(stats: ClipStats) -> str:
    if stats.tracked_s <= 0:
        return "The clip has no tracked time yet, so there are no actions to count."
    receive = "receive" if stats.receives == 1 else "receives"
    passed = "completed pass" if stats.passes_completed == 1 else "completed passes"
    carry = "carry" if stats.carries == 1 else "carries"
    loss = "ball loss" if stats.losses == 1 else "ball losses"
    first = (
        f"In {fmt_num(stats.tracked_s)} seconds the clip shows {stats.receives} {receive}, "
        f"{stats.passes_completed} {passed} out of {stats.passes_attempted}, "
        f"{stats.carries} {carry} and {stats.losses} {loss}."
    )
    return f"{first} That is {fmt_num(_per_minute(stats))} actions a tracked minute."


def summary_ok(text: str, table: str) -> bool:
    cleaned = " ".join(text.split())
    if not cleaned or _banned(cleaned):
        return False
    sentences = [part for part in re.split(r"(?<!\d)[.!?](?!\d)", cleaned) if part.strip()]
    if not 1 <= len(sentences) <= 2:
        return False
    known = {float(token) for token in NUMBER.findall(table)}
    return all(float(token) in known for token in NUMBER.findall(cleaned))


def draft_email(body: OpportunityIn, coach_name: str | None, table: str, summary: str) -> tuple[str, str]:
    subject = f"{body.grad_year} {body.position.strip()} from {body.state}, {LEAGUE_LABEL[body.league]}: clip stats"
    last = _last_name(coach_name)
    greeting = f"Coach {last}," if last else "Hello,"
    player = body.player_name.strip()
    who = player or "a player"
    intro = (
        f"I am {who}, a {body.position.strip()} in the class of {body.grad_year} "
        f"from {body.state}, playing in {LEAGUE_LABEL[body.league]}."
        if player
        else f"I am a {body.position.strip()} in the class of {body.grad_year} from {body.state}, playing in {LEAGUE_LABEL[body.league]}."
    )
    sign_off = player or "this player"
    lines = [greeting, "", intro, "", table, "", summary]
    profile = body.profile.strip()
    if profile and summary_ok(profile, table):
        lines.extend(["", profile])
    if body.clip_url.strip():
        lines.extend(["", f"Clip: {body.clip_url.strip()}"])
    lines.extend(["", *([player] if player else []), body.player_email.strip(), "", f"Sent through SecondLook for {sign_off}. Replies go to {body.player_email.strip()}."])
    return subject, "\n".join(lines)


def fingerprint(body: OpportunityIn) -> str:
    payload = {
        "v": OPPORTUNITY_PROMPT_VERSION,
        "name": body.player_name.strip(),
        "email": body.player_email.strip().casefold(),
        "position": body.position.strip(),
        "year": body.grad_year,
        "state": body.state,
        "league": body.league,
        "clip": body.clip_url.strip(),
        "schools": body.schools,
        "stats": body.stats.model_dump(),
        "profile": body.profile.strip(),
        "fit": "league-v1",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def list_programs(db: Database, settings: Settings, review_id: str, body: ProgramsIn) -> ProgramsOut:
    if not REVIEW_ID.fullmatch(review_id):
        raise AppError("not_found", "That review was not found.", 404)
    divisions = BOTH_DIVISIONS
    stored, run_ids, actors, status = ensure_lists(db, settings, divisions)
    programs = _programs_for(stored, body.state, divisions)
    programs.sort(key=lambda program: (
        FIT_ORDER[fit_of(body.league, program)],
        0 if program.get("division") == "d2" else 1,
        program["school"],
    ))
    missing = [division for division in divisions if division not in stored]
    message = None
    if missing and not programs:
        message = "The program list could not be read. Try again."
    elif not programs:
        message = f"No men's soccer programs were listed in {body.state} for that level."
    elif missing:
        message = "One division list could not be read. The programs below are the ones that came back."
    times = [str(stored[division].get("retrieved_at") or "") for division in divisions if division in stored]
    retrieved = max(times) if status == "cached" and any(times) else utcnow()
    return ProgramsOut(
        programs=[_program_out(program, body.league) for program in programs],
        divisions=list(divisions),
        rule=FIT_RULE,
        note=LEVEL_NOTE,
        run_ids=run_ids,
        actors=actors,
        cache_status=status,
        retrieved_at=retrieved,
        message=message,
    )


def find_coaches(
    db: Database,
    settings: Settings,
    review_id: str,
    body: OpportunityIn,
    search_fn=None,
    summary_fn=None,
) -> OpportunityOut:
    if not REVIEW_ID.fullmatch(review_id):
        raise AppError("not_found", "That review was not found.", 404)
    digest = fingerprint(body)
    cached = db.get_opportunity_cache(digest)
    if cached:
        stored = OpportunityOut.model_validate_json(cached)
        return stored.model_copy(update={"cache_status": "cached"})
    if search_fn is None and not settings.apify_token.strip():
        raise AppError("apify_not_configured", "Apify is not connected on this server. Add APIFY_TOKEN.", 503)
    divisions = BOTH_DIVISIONS
    stored, list_runs, list_actors, _status = ensure_lists(db, settings, divisions)
    chosen = _chosen(stored, body)
    retrieved_at = utcnow()
    if not chosen:
        result = _empty_result(review_id, body, retrieved_at, _empty_choice_message(stored, body))
        return result
    searched = (search_fn or search_coaches)(settings, chosen)
    table = stats_table(body.stats)
    summary = (summary_fn or write_summary)(settings, body.stats, table)
    hits = {hit.school: hit for hit in searched.hits}
    cards = [_card(body, program, hits.get(program["school"]), table, summary) for program in chosen]
    found = sum(1 for card in cards if card.email)
    message = None if found else "No public coach email was printed on the pages that came back."
    result = OpportunityOut(
        result_id=new_id("out"),
        review_id=review_id,
        player_email=body.player_email.strip(),
        cards=cards,
        summary=summary,
        stats_table=table,
        rule=FIT_RULE,
        run_ids=[*list_runs, *searched.run_ids],
        actors=[*list_actors, *searched.actors],
        cache_status="live",
        retrieved_at=retrieved_at,
        message=message,
    )
    payload = result.model_dump_json()
    db.put_opportunity_cache(digest, payload)
    db.put_opportunity_cache(f"result:{result.result_id}", payload)
    return result


def send_outreach(db: Database, settings: Settings, review_id: str, body: SendIn, send_fn=None) -> SendOut:
    if not REVIEW_ID.fullmatch(review_id):
        raise AppError("not_found", "That review was not found.", 404)
    raw = db.get_opportunity_cache(f"result:{body.result_id}")
    if not raw:
        raise AppError("not_found", "That coach list was not found. Find coaches again.", 404)
    stored = OpportunityOut.model_validate_json(raw)
    if stored.review_id != review_id:
        raise AppError("not_found", "That coach list was not found. Find coaches again.", 404)
    coach = body.email.casefold()
    allowed = {card.email.casefold() for card in stored.cards if card.email}
    if coach not in allowed:
        raise AppError("unknown_recipient", "That address is not a coach email from this search.", 400)
    if body.reply_to.casefold() != stored.player_email.casefold():
        raise AppError("reply_mismatch", "Replies have to go to the email on this search.", 400)
    if _already_sent(db, review_id, coach):
        raise AppError("already_sent", "This coach already has an email from this review.", 409)
    live = bool(settings.mail_live)
    if live and _live_count(db, review_id) >= settings.outreach_live_cap:
        raise AppError("send_cap", "This review already sent the limit of live emails.", 409)
    delivered = (send_fn or deliver_mail)(settings, body.email, body.subject, body.body, html_body(body.body), body.reply_to)
    try:
        db.execute(
            """
            INSERT INTO outreach_sends
              (id, review_id, result_id, coach_email, delivered_to, subject, test_mode, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (new_id("mail"), review_id, body.result_id, coach, delivered, body.subject, 0 if live else 1, utcnow()),
        )
    except sqlite3.IntegrityError:
        raise AppError("already_sent", "This coach already has an email from this review.", 409) from None
    if live:
        return SendOut(sent_to=delivered, test_mode=False, message="Sent.")
    return SendOut(sent_to=delivered, test_mode=True, message="Sent to your test inbox.")


def write_summary(settings: Settings, stats: ClipStats, table: str) -> str:
    fallback = fallback_summary(stats)
    if stats.tracked_s <= 0 or not settings.anthropic_api_key.strip():
        return fallback
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.provider_timeout_seconds,
        max_retries=0,
    )
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=300,
            system=PROMPT.read_text(encoding="utf-8"),
            messages=[{"role": "user", "content": table}],
            output_format=SummaryDraft,
        )
    except Exception:
        log.warning("outreach summary failed")
        return fallback
    usage = getattr(response, "usage", None)
    log.info(
        "outreach summary input=%s output=%s",
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
    )
    parsed = response.parsed_output
    if parsed is None or not summary_ok(parsed.text, table):
        return fallback
    return " ".join(parsed.text.split())


def reach_fingerprint(body: ReachIn) -> str:
    payload = {
        "v": REACH_PROMPT_VERSION,
        "position": body.position.strip(),
        "year": body.grad_year,
        "state": body.state,
        "league": body.league,
        "school": body.school.strip(),
        "stats": body.stats.model_dump(),
        "profile": body.profile.strip(),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def reach_plan(db: Database, settings: Settings, review_id: str, body: ReachIn) -> ReachOut:
    if not REVIEW_ID.fullmatch(review_id):
        raise AppError("not_found", "That review was not found.", 404)
    digest = f"reach:{reach_fingerprint(body)}"
    cached = db.get_opportunity_cache(digest)
    if cached:
        return ReachOut.model_validate_json(cached)
    stored, _run_ids, _actors, _status = ensure_lists(db, settings, BOTH_DIVISIONS)
    program = next(
        (item for item in _programs_for(stored, body.state, BOTH_DIVISIONS) if item["school"] == body.school),
        None,
    )
    if program is None:
        raise AppError("not_found", "That school is not on the list for that state.", 404)
    table = stats_table(body.stats)
    reason = fit_reason(body.league, program, fit_of(body.league, program))
    drafted = write_reach(settings, body, program, table)
    if drafted is None:
        result = standard_reach(program, reason, body.position)
        if not settings.anthropic_api_key.strip():
            db.put_opportunity_cache(digest, result.model_dump_json())
        return result
    read, steps = drafted
    result = ReachOut(
        school=program["school"],
        division=program["division"],
        conference=program["conference"],
        reason=reason,
        read=read,
        steps=steps,
        source="claude",
    )
    db.put_opportunity_cache(digest, result.model_dump_json())
    return result


def standard_reach(program: dict, reason: str, position: str) -> ReachOut:
    conference = program["conference"]
    role = position.strip() or "your position"
    return ReachOut(
        school=program["school"],
        division=program["division"],
        conference=conference,
        reason=reason,
        read=STANDARD_READ,
        steps=[
            ReachStepOut(
                title="Ask a local coach to watch you",
                detail="Ask a high school coach, a rec coach, or a volunteer to watch one practice and name one thing to work on.",
                cost="free",
            ),
            ReachStepOut(
                title="Ask one club about fee help",
                detail="Write to one club that plays above your league and ask if they offer aid or a guest spot. Do not pay a showcase fee.",
                cost="free",
            ),
            ReachStepOut(
                title="Film from the halfway line",
                detail="Set the phone on a tripod or a clamp around chest height at midfield, so you stay in frame.",
                cost="low cost",
            ),
            ReachStepOut(
                title=f"Name {conference} in your note",
                detail=(
                    f"Say you play {role} and that you are writing because of {conference}. "
                    "Keep every number inside the stats you already have."
                ),
                cost="free",
            ),
        ],
        source="standard",
    )


def write_reach(
    settings: Settings,
    body: ReachIn,
    program: dict,
    table: str,
) -> tuple[str, list[ReachStepOut]] | None:
    if not settings.anthropic_api_key.strip():
        return None
    level = "NCAA I" if program["division"] == "d1" else "NCAA II"
    user = "\n".join([
        f"School: {program['school']}",
        f"Level: {level}",
        f"Conference: {program['conference']}",
        f"League listed: {LEAGUE_LABEL[body.league]}",
        f"Position: {body.position.strip()}",
        "",
        "Stats:",
        table,
        "",
        "Profile:",
        body.profile.strip() or "(none)",
    ])
    client = anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=settings.provider_timeout_seconds,
        max_retries=0,
    )
    try:
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2000,
            system=REACH_PROMPT.read_text(encoding="utf-8"),
            messages=[{"role": "user", "content": user}],
            output_format=ReachDraft,
        )
    except Exception as exc:
        log.warning("reach plan failed: %s", type(exc).__name__)
        return None
    usage = getattr(response, "usage", None)
    log.info(
        "reach plan input=%s output=%s",
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
    )
    parsed = response.parsed_output
    if parsed is None or not reach_ok(parsed.read, parsed.steps, table):
        log.warning("reach plan rejected stop=%s", getattr(response, "stop_reason", None))
        return None
    steps = [
        ReachStepOut(
            title=" ".join(step.title.split()),
            detail=" ".join(step.detail.split()),
            cost=step.cost,
        )
        for step in parsed.steps
    ]
    return " ".join(parsed.read.split()), steps


def reach_ok(read: str, steps: list[ReachStepDraft], table: str) -> bool:
    cleaned = " ".join(read.split())
    if not summary_ok(cleaned, table) or URLISH.search(cleaned) or MORE_FOOTAGE.search(cleaned):
        return False
    if not 3 <= len(steps) <= 4:
        return False
    known = {float(token) for token in NUMBER.findall(table)}
    blobs = [cleaned]
    for step in steps:
        title = " ".join(str(step.title).split())
        detail = " ".join(str(step.detail).split())
        if not title or len(title) > 90 or not detail or len(detail) > 480:
            return False
        if str(step.cost) not in {"free", "low cost"}:
            return False
        if _banned(title) or _banned(detail) or URLISH.search(title) or URLISH.search(detail):
            return False
        if MORE_FOOTAGE.search(title) or MORE_FOOTAGE.search(detail):
            return False
        blobs.append(f"{title} {detail}")
    return all(float(token) in known for token in NUMBER.findall(" ".join(blobs)))


def ensure_lists(db: Database, settings: Settings, divisions: tuple[str, ...]) -> tuple[dict, list[str], list[str], str]:
    stored: dict = {}
    missing: list[str] = []
    for division in divisions:
        raw = db.get_opportunity_cache(f"list:{division}")
        if raw:
            stored[division] = json.loads(raw)
        else:
            missing.append(division)
    if not missing:
        return stored, [], [], "cached"
    if not settings.apify_token.strip():
        raise AppError("apify_not_configured", "Apify is not connected on this server. Add APIFY_TOKEN.", 503)
    wait = max(40, int(settings.apify_timeout_seconds * 0.7))
    with httpx.Client(timeout=httpx.Timeout(wait + 20)) as client:
        run_id, items = _run_actor(
            client,
            settings.apify_token,
            CRAWL_ACTOR,
            _crawl_payload([LIST_URL[division] for division in missing]),
            wait,
        )
    for division in missing:
        text = _text_for_division(items, division)
        programs = parse_programs(text, division) if text else []
        if not programs:
            log.warning("program list empty division=%s", division)
            continue
        stored[division] = {"programs": programs, "run_id": run_id, "retrieved_at": utcnow()}
        db.put_opportunity_cache(f"list:{division}", json.dumps(stored[division]))
    return stored, [run_id], [CRAWL_ACTOR], "live"


def search_coaches(settings: Settings, programs: list[dict]) -> SearchResult:
    search_wait = max(60, int(settings.apify_timeout_seconds))
    crawl_wait = max(40, int(settings.apify_timeout_seconds * 0.7))
    actors = [SEARCH_ACTOR]
    with httpx.Client(timeout=httpx.Timeout(search_wait + 25)) as client:
        search_id, items = _run_actor(
            client,
            settings.apify_token,
            SEARCH_ACTOR,
            {
                "queries": "\n".join(f'"{program["short_name"]}" men\'s soccer coaches' for program in programs),
                "maxPagesPerQuery": 1,
                "resultsPerPage": 5,
                "countryCode": "us",
                "languageCode": "en",
            },
            search_wait,
        )
        run_ids = [search_id]
        pages = _assign_urls(items, programs)
        if not pages:
            return SearchResult(hits=[], run_ids=run_ids, actors=actors)
        crawl_id, crawl_items = _run_actor(
            client,
            settings.apify_token,
            CRAWL_ACTOR,
            _crawl_payload([url for _school, url in pages.values()]),
            crawl_wait,
        )
        actors.append(CRAWL_ACTOR)
        run_ids.append(crawl_id)
        texts = _index_text(crawl_items)
        hits = []
        for key, (school, url) in pages.items():
            text = texts.get(key, "")
            if len(text.strip()) < 40:
                continue
            hits.append(CoachHit(school=school, url=url, text=text[:20000]))
        return SearchResult(hits=hits, run_ids=run_ids, actors=actors)


def _assign_urls(items: list, programs: list[dict]) -> dict[str, tuple[str, str]]:
    usable = [item for item in items if isinstance(item, dict)]
    if usable and not any(_term(item) for item in usable):
        return _assign_untitled(usable, programs)
    found: dict[str, tuple[str, str]] = {}
    claimed: set[str] = set()
    for item in usable:
        program = _program_for_term(_term(item), programs)
        if program is None or program["school"] in claimed:
            continue
        url = first_coach_url(item.get("organicResults") or [])
        if not url or norm_url(url) in found:
            continue
        found[norm_url(url)] = (program["school"], url)
        claimed.add(program["school"])
    return found


def _assign_untitled(items: list[dict], programs: list[dict]) -> dict[str, tuple[str, str]]:
    results: list[dict] = []
    for item in items:
        results.extend(row for row in (item.get("organicResults") or []) if isinstance(row, dict))
    found: dict[str, tuple[str, str]] = {}
    ordered = sorted(programs, key=lambda program: len(program["short_name"]), reverse=True)
    for program in ordered:
        short = program["short_name"].casefold()
        matching = [
            row for row in results
            if _contains_name(short, f"{row.get('title') or ''} {row.get('url') or ''}".casefold())
        ]
        url = first_coach_url(matching)
        if not url or norm_url(url) in found:
            continue
        found[norm_url(url)] = (program["school"], url)
    return found


def _program_for_term(term: str, programs: list[dict]) -> dict | None:
    ordered = sorted(programs, key=lambda program: len(program["short_name"]), reverse=True)
    for program in ordered:
        if _contains_name(program["short_name"].casefold(), term.casefold()):
            return program
    return None


def _contains_name(short: str, text: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){re.escape(short)}([^a-z0-9]|$)", text) is not None


def _term(item: dict) -> str:
    query = item.get("searchQuery")
    if isinstance(query, dict):
        return str(query.get("term") or "")
    if isinstance(query, str):
        return query
    return str(item.get("query") or item.get("term") or "")


def _text_for_division(items: list, division: str) -> str:
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        urls = [str(item.get("url") or "")]
        crawl = item.get("crawl")
        if isinstance(crawl, dict):
            urls.append(str(crawl.get("loadedUrl") or ""))
        if any(_division_from_url(url) == division for url in urls):
            parts.append(str(item.get("markdown") or item.get("text") or ""))
    return "\n".join(parts)[:200000]


def _division_from_url(url: str) -> str | None:
    path = unquote(urlsplit(url).path).casefold().replace(" ", "_")
    if "division_ii" in path:
        return "d2"
    if "division_i" in path:
        return "d1"
    return None


def _index_text(items: list) -> dict[str, str]:
    found: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("markdown") or item.get("text") or "").strip()
        if len(text) < 40:
            continue
        urls = [str(item.get("url") or "")]
        crawl = item.get("crawl")
        if isinstance(crawl, dict):
            urls.append(str(crawl.get("loadedUrl") or ""))
        for url in urls:
            if url.startswith("https://"):
                found[norm_url(url)] = text[:20000]
    return found


def _crawl_payload(urls: list[str]) -> dict:
    return {
        "startUrls": [{"url": url} for url in urls],
        "maxCrawlPages": len(urls),
        "maxCrawlDepth": 0,
        "crawlerType": "cheerio",
        "saveMarkdown": True,
        "useSitemaps": False,
        "respectRobotsTxtFile": True,
        "blockMedia": True,
        "proxyConfiguration": {"useApifyProxy": True},
    }


def _programs_for(stored: dict, state: str, divisions: tuple[str, ...]) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()
    for division in divisions:
        for program in stored.get(division, {}).get("programs", []):
            if program.get("state") != state or program["school"].casefold() in seen:
                continue
            seen.add(program["school"].casefold())
            found.append(program)
    return found


def _chosen(stored: dict, body: OpportunityIn) -> list[dict]:
    by_name = {program["school"]: program for program in _programs_for(stored, body.state, BOTH_DIVISIONS)}
    chosen: list[dict] = []
    for name in body.schools:
        program = by_name.get(name)
        if program is None or fit_of(body.league, program) == "reach":
            continue
        chosen.append(program)
    return chosen


def _empty_choice_message(stored: dict, body: OpportunityIn) -> str:
    by_name = {program["school"]: program for program in _programs_for(stored, body.state, BOTH_DIVISIONS)}
    listed = [by_name[name] for name in body.schools if name in by_name]
    if listed and all(fit_of(body.league, program) == "reach" for program in listed):
        return "Those schools are a reach from this league, so they are not emailed."
    return "Those schools are not on the list for that state."


def _card(body: OpportunityIn, program: dict, hit: CoachHit | None, table: str, summary: str) -> CoachCardOut:
    contact = pick_contact(staff_rows(hit.text), hit.text) if hit else dict(EMPTY_CONTACT)
    subject, draft = draft_email(body, contact["name"], table, summary)
    return CoachCardOut(
        school=program["school"],
        division=program["division"],
        conference=program["conference"],
        coach_name=contact["name"],
        title=contact["title"],
        email=contact["email"],
        phone=contact["phone"],
        url=hit.url if hit else None,
        subject=subject,
        draft=draft,
    )


def _empty_result(review_id: str, body: OpportunityIn, retrieved_at: str, message: str) -> OpportunityOut:
    return OpportunityOut(
        result_id=new_id("out"),
        review_id=review_id,
        player_email=body.player_email.strip(),
        cards=[],
        summary="",
        stats_table=stats_table(body.stats),
        rule=FIT_RULE,
        run_ids=[],
        actors=[],
        cache_status="live",
        retrieved_at=retrieved_at,
        message=message,
    )


def _program_out(program: dict, league: str) -> ProgramOut:
    tier = fit_of(league, program)
    return ProgramOut(
        school=program["school"],
        short_name=program["short_name"],
        city=program["city"],
        state=program["state"],
        conference=program["conference"],
        division=program["division"],
        fit=tier,
        fit_reason=fit_reason(league, program, tier),
    )


def _already_sent(db: Database, review_id: str, coach_email: str) -> bool:
    row = db.query_one(
        "SELECT id FROM outreach_sends WHERE review_id=? AND coach_email=?",
        (review_id, coach_email),
    )
    return row is not None


def _live_count(db: Database, review_id: str) -> int:
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM outreach_sends WHERE review_id=? AND test_mode=0",
        (review_id,),
    )
    return int(row["n"]) if row else 0


def _table_rows(markdown: str) -> list[dict]:
    rows: list[dict] = []
    header = False
    name_i = title_i = email_i = phone_i = None
    for line in markdown.splitlines():
        if not line.strip().startswith("|"):
            header = False
            continue
        raw = [cell.strip() for cell in line.strip().strip("|").split("|")]
        cells = [_clean_cell(cell) for cell in raw]
        if not cells or all(not cell or set(cell) <= set("-: ") for cell in cells):
            continue
        folded = [cell.casefold() for cell in cells]
        if _staff_header(folded):
            name_i = _index(folded, ("name", "coach"))
            title_i = _index(folded, ("title", "position"))
            email_i = _index_contains(folded, ("email", "e-mail", "e mail"))
            phone_i = _index_contains(folded, ("phone", "tel"))
            header = True
            continue
        if not header:
            continue
        name = _at(cells, name_i)
        title = _at(cells, title_i)
        email = _first_email(_at(raw, email_i) or " ".join(raw))
        phone = _first_phone(_at(cells, phone_i))
        if name or email:
            rows.append({"name": name, "title": title, "email": email, "phone": phone})
    return rows


def _block_rows(markdown: str) -> list[dict]:
    rows: list[dict] = []
    for block in re.split(r"\n(?=#{1,4} )", markdown):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("#"):
            continue
        name = _clean_cell(lines[0].lstrip("#"))
        if not name or len(name) > 80:
            continue
        title = ""
        email = None
        phone = None
        for line in lines[1:6]:
            if email is None:
                email = _first_email(line)
            if phone is None:
                phone = _first_phone(line)
            if not title and email is None and "http" not in line.casefold() and not line.startswith("["):
                title = _clean_cell(line)
        if email or any(word in title.casefold() for word in ("coach", "recruit")):
            rows.append({"name": name, "title": title, "email": email, "phone": phone})
    return rows


def _run_actor(client: httpx.Client, token: str, actor: str, payload: dict, wait_seconds: int) -> tuple[str, list]:
    actor_id = actor.replace("/", "~")
    try:
        started = client.post(
            f"{APIFY_BASE}/actors/{actor_id}/runs",
            params={"waitForFinish": wait_seconds, "timeout": wait_seconds, "maxTotalChargeUsd": 1},
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    except httpx.TimeoutException as exc:
        raise AppError("apify_timeout", "Public pages took too long to read. Try again.", 504, retryable=True) from exc
    except httpx.HTTPError:
        log.warning("apify connection failed")
        raise AppError("apify_unavailable", "The page read could not be reached. Try again.", 502, retryable=True) from None
    if started.status_code in {401, 403}:
        raise AppError("apify_auth", "The Apify token was rejected. Check APIFY_TOKEN on the server.", 503)
    if started.status_code >= 400:
        log.warning("apify run rejected status=%s actor=%s", started.status_code, actor)
        raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
    body = started.json()
    run = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
    if not isinstance(run, dict):
        raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
    status = str(run.get("status") or "")
    dataset_id = run.get("defaultDatasetId")
    run_id = str(run.get("id") or "")
    if status != "SUCCEEDED":
        log.warning("apify run status=%s actor=%s", status, actor)
        if status not in {"RUNNING", "READY", "TIMING-OUT", "TIMED-OUT"}:
            raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
        if not dataset_id or not run_id:
            raise AppError("apify_timeout", "Public pages took too long to read. Try again.", 504, retryable=True)
        data = _dataset_items(client, token, str(dataset_id))
        if data:
            return run_id, data
        raise AppError("apify_timeout", "Public pages took too long to read. Try again.", 504, retryable=True)
    if not dataset_id or not run_id:
        raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
    return run_id, _dataset_items(client, token, str(dataset_id))


def _dataset_items(client: httpx.Client, token: str, dataset_id: str) -> list:
    try:
        items = client.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            params={"clean": "true", "limit": 20},
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError:
        log.warning("apify dataset failed")
        raise AppError("apify_unavailable", "The page read could not be reached. Try again.", 502, retryable=True) from None
    if items.status_code >= 400:
        raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
    data = items.json()
    if not isinstance(data, list):
        raise AppError("apify_failed", "The page read did not finish. Try again.", 502, retryable=True)
    return data


def norm_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{host}{path}"


def _blocked(host: str) -> bool:
    host = host.lower().removeprefix("www.")
    return any(host == name or host.endswith("." + name) for name in BLOCKED)


def _aggregator(host: str) -> bool:
    return any(host == name or host.endswith("." + name) for name in AGGREGATORS)


def _clean_cell(value: str) -> str:
    text = value.strip()
    if text.startswith("[") and "](" in text:
        text = text[1:text.index("](")]
    else:
        text = LINK.sub(r"\1", text)
    text = text.replace("**", "").replace("__", "")
    text = CELL_NOTE.sub("", text)
    return " ".join(text.split())


def _program_header(folded: list[str]) -> bool:
    has_school = any(cell in {"school", "institution"} for cell in folded)
    has_city = any(cell in {"city", "location"} for cell in folded)
    has_state = any(cell.startswith("state") for cell in folded)
    return has_school and has_city and has_state and "conference" in folded


def _program_columns(folded: list[str]) -> dict[str, int]:
    return {
        "school": _index(folded, ("school", "institution")),
        "city": next(index for index, cell in enumerate(folded) if cell in {"city", "location"}),
        "state": next(index for index, cell in enumerate(folded) if cell.startswith("state")),
        "conference": folded.index("conference"),
    }


def _staff_header(folded: list[str]) -> bool:
    if any(cell in {"school", "institution"} for cell in folded):
        return False
    has_name = any(cell in {"name", "coach"} or cell.startswith("name") for cell in folded)
    has_role = any("title" in cell or "position" in cell or "email" in cell or "e-mail" in cell for cell in folded)
    return has_name and has_role


def _index(folded: list[str], names: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(folded):
        if cell in names or any(cell.startswith(name) for name in names):
            return index
    return None


def _index_contains(folded: list[str], names: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(folded):
        if any(name in cell for name in names):
            return index
    return None


def _cell(cells: list[str], index: int) -> str:
    return cells[index] if index < len(cells) else ""


def _at(cells: list[str], index: int | None) -> str:
    if index is None or index >= len(cells):
        return ""
    return cells[index]


def _first_email(value: str) -> str | None:
    match = EMAIL.search(value or "")
    return match.group(0) if match else None


def _first_phone(value: str) -> str | None:
    match = PHONE.search(value or "")
    return match.group(0) if match else None


def _rank(title: str) -> int:
    folded = title.casefold()
    if "recruit" in folded:
        return 0
    if "assistant" in folded or "associate" in folded:
        return 1
    if "head" in folded:
        return 2
    return 3


def _last_name(name: str | None) -> str | None:
    if not name:
        return None
    parts = name.replace(",", " ").split()
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"}
    while parts and parts[-1].casefold() in suffixes:
        parts.pop()
    return parts[-1] if parts else None


def fmt_num(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def _per_minute(stats: ClipStats) -> float:
    actions = stats.receives + stats.passes_attempted + stats.carries + stats.losses
    return actions / (stats.tracked_s / 60)


def _banned(text: str) -> bool:
    folded = text.casefold()
    if any(word in folded for word in BANNED):
        return True
    return any(re.search(rf"\b{re.escape(word)}\b", folded) for word in LEVEL_WORDS)
