import json

import pytest

from app.config import Settings
from app.db import Database, new_id, utcnow
from app.errors import AppError
from app.mailer import html_body, send
from app.opportunities import (
    FIT_RULE,
    LEAGUE_RULE,
    CoachHit,
    SearchResult,
    draft_email,
    fallback_summary,
    find_coaches,
    first_coach_url,
    fingerprint,
    list_programs,
    parse_programs,
    pick_contact,
    reach_plan,
    send_outreach,
    staff_rows,
    stats_table,
    summary_ok,
    write_summary,
    _program_for_term,
)
from app.schemas import ClipStats, OpportunityIn, ProgramsIn, ReachIn, SendIn
from tests.conftest import make_client

CALPOLY = """
| Name | Title | Phone | E-Mail |
| --- | --- | --- | --- |
| Oige Kennedy | Men's Soccer Head Coach |  | mensoccer@calpoly.edu |
| Zach Watson | Assistant Coach |  | zwatso01@calpoly.edu |
| Brandon Bautista | Assistant Coach |  | bbauti11@calpoly.edu |
"""
MAILTO = """
| Name | Title | E-Mail |
| --- | --- | --- |
| Oige Kennedy | Men's Soccer Head Coach | [mensoccer@calpoly.edu](mailto:mensoccer@calpoly.edu) |
| Pat Recruit | Recruiting Coordinator | [recruit@calpoly.edu](mailto:recruit@calpoly.edu) |
"""
D2_LIST = """
## Current programs

| School | Nickname | City | State/ Province | Conference | Note |
| --- | --- | --- | --- | --- | --- |
| Biola University | Eagles | La Mirada | California | Pacific West Conference | |
| Adams State University | Grizzlies | Alamosa | Colorado | Rocky Mountain Athletic Conference | |
| California State Polytechnic University, Pomona (Cal Poly Pomona) | Broncos | Pomona | California | California Collegiate Athletic Association | |

## Former programs

| School | Nickname | City | State | Conference |
| --- | --- | --- | --- | --- |
| Old California College | Oaks | Fresno | California | Gone |
"""
D1_LIST = """
| Institution | Nickname | Location | State | Type | Conference |
| --- | --- | --- | --- | --- | --- |
| University of California, Berkeley (California/Cal) | Golden Bears | Berkeley | California | State | Atlantic Coast Conference |
| George Washington University | Revolutionaries | Washington | D.C. | Private/Nonsectarian | Atlantic 10 Conference |
"""
STATS = ClipStats(
    tracked_s=29.5,
    receives=3,
    passes_completed=2,
    passes_attempted=2,
    carries=1,
    losses=1,
    reviewed=True,
)


def _body(**overrides) -> OpportunityIn:
    values = dict(
        player_name="Alex",
        player_email="alex@example.com",
        position="Fullback",
        grad_year=2027,
        state="California",
        league="ecnl_rl",
        clip_url="https://clips.example.com/alex",
        schools=["Biola University"],
        stats=STATS,
    )
    values.update(overrides)
    return OpportunityIn(**values)


def _seed(db: Database) -> None:
    db.put_opportunity_cache(
        "list:d2",
        json.dumps({
            "programs": [
                {
                    "school": "Biola University",
                    "short_name": "Biola",
                    "city": "La Mirada",
                    "state": "California",
                    "conference": "Pacific West Conference",
                    "division": "d2",
                },
                {
                    "school": "Adams State University",
                    "short_name": "Adams State",
                    "city": "Alamosa",
                    "state": "Colorado",
                    "conference": "Rocky Mountain Athletic Conference",
                    "division": "d2",
                },
            ],
            "run_id": "run_list",
            "retrieved_at": "2026-10-25T09:00:00.000000Z",
        }),
    )
    db.put_opportunity_cache(
        "list:d1",
        json.dumps({
            "programs": [
                {
                    "school": "Stanford University",
                    "short_name": "Stanford",
                    "city": "Stanford",
                    "state": "California",
                    "conference": "Atlantic Coast Conference",
                    "division": "d1",
                },
                {
                    "school": "Santa Clara University",
                    "short_name": "Santa Clara",
                    "city": "Santa Clara",
                    "state": "California",
                    "conference": "West Coast Conference",
                    "division": "d1",
                },
                {
                    "school": "University of Denver",
                    "short_name": "Denver",
                    "city": "Denver",
                    "state": "Colorado",
                    "conference": "The Summit League",
                    "division": "d1",
                },
            ],
            "run_id": "run_list_d1",
            "retrieved_at": "2026-10-25T09:00:00.000000Z",
        }),
    )


LOOSE_LIST = """
School

Nickname

City

State/  
Province

Conference

Note

[Adams State University](https://en.wikipedia.org/wiki/Adams_State_University "Adams State University")

Grizzlies

[Alamosa](https://en.wikipedia.org/wiki/Alamosa,_Colorado "Alamosa")

[Colorado](https://en.wikipedia.org/wiki/Colorado "Colorado")

[Rocky Mountain Athletic Conference](https://en.wikipedia.org/wiki/Rocky_Mountain_Athletic_Conference "RMAC")

[Chaminade University of Honolulu](https://example.edu/chaminade)

Silverswords

Honolulu

[Hawai'i](https://en.wikipedia.org/wiki/Hawaii "Hawaii")

Pacific West Conference

[University of the District of Columbia](https://example.edu/udc)

Firebirds

Washington

[District of Columbia](https://example.edu/dc "District of Columbia")

East Coast Conference
"""


def test_crawler_lines_keep_hawaii_and_do_not_call_washington_dc_a_state():
    rows = parse_programs(LOOSE_LIST, "d2")
    assert [(row["school"], row["state"]) for row in rows] == [
        ("Adams State University", "Colorado"),
        ("Chaminade University of Honolulu", "Hawaii"),
        ("University of the District of Columbia", "District of Columbia"),
    ]
    assert rows[2]["city"] == "Washington"
    assert rows[2]["conference"] == "East Coast Conference"


def test_split_short_name_stays_with_the_school():
    rows = parse_programs(
        """
Institution

Nickname

Location

State

Type

Conference

University of California, Berkeley

(California/Cal)

Golden Bears

Berkeley

California

State

Atlantic Coast Conference
""",
        "d1",
    )
    assert len(rows) == 1
    assert rows[0]["short_name"] == "Cal"
    assert rows[0]["city"] == "Berkeley"
    assert rows[0]["conference"] == "Atlantic Coast Conference"
    assert rows[0]["state"] == "California"


def test_programs_in_california_skip_the_former_table():
    rows = parse_programs(D2_LIST, "d2")
    assert [row["school"] for row in rows if row["state"] == "California"] == [
        "Biola University",
        "California State Polytechnic University, Pomona (Cal Poly Pomona)",
    ]
    assert all(row["state"] != "California" or "Old" not in row["school"] for row in rows)
    assert rows[-1]["short_name"] == "Cal Poly Pomona"
    d1 = parse_programs(D1_LIST, "d1")
    assert d1[0]["short_name"] == "Cal"
    assert d1[1]["state"] == "District of Columbia"


def test_saved_list_filters_by_state(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    _seed(db)
    found = list_programs(db, Settings(apify_token=""), new_id("sub"), ProgramsIn(state="California", league="ecnl_rl"))
    assert [item.school for item in found.programs] == [
        "Biola University",
        "Santa Clara University",
        "Stanford University",
    ]
    assert found.cache_status == "cached"
    assert found.divisions == ["d1", "d2"]
    assert found.rule == FIT_RULE
    assert "not read yet" in found.note


def test_high_school_puts_top_conferences_at_the_bottom(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    _seed(db)
    found = list_programs(db, Settings(apify_token=""), new_id("sub"), ProgramsIn(state="California", league="high_school"))
    assert [(item.school, item.fit) for item in found.programs] == [
        ("Biola University", "fit"),
        ("Santa Clara University", "possible"),
        ("Stanford University", "reach"),
    ]
    assert "Atlantic Coast Conference" in found.programs[-1].fit_reason
    assert "you listed high school." in found.programs[-1].fit_reason
    mls = list_programs(db, Settings(apify_token=""), new_id("sub"), ProgramsIn(state="California", league="mls_next"))
    assert {item.fit for item in mls.programs} == {"fit"}


def _reach(school: str = "Stanford University", league: str = "high_school") -> ReachIn:
    return ReachIn(
        position="Fullback",
        grad_year=2027,
        state="California",
        league=league,
        school=school,
        stats=STATS,
    )


def test_reach_school_is_not_emailed(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    _seed(db)
    calls = {"search": 0}

    def search(settings, programs):
        calls["search"] += 1
        return SearchResult(hits=[], run_ids=[], actors=[])

    result = find_coaches(
        db,
        Settings(apify_token="test-token", anthropic_api_key=""),
        new_id("sub"),
        _body(league="high_school", schools=["Stanford University"]),
        search_fn=search,
        summary_fn=lambda settings, stats, table: fallback_summary(stats),
    )
    assert calls["search"] == 0
    assert result.cards == []
    assert "reach" in (result.message or "").casefold()


def test_reach_plan_uses_standard_steps_without_a_key(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    _seed(db)
    settings = Settings(anthropic_api_key="")
    review_id = new_id("sub")
    first = reach_plan(db, settings, review_id, _reach())
    second = reach_plan(db, settings, review_id, _reach())
    assert first.source == "standard"
    assert first.division == "d1"
    assert first.conference == "Atlantic Coast Conference"
    assert "you listed high school." in first.reason
    assert len(first.steps) == 4
    assert {step.cost for step in first.steps} <= {"free", "low cost"}
    assert any(step.cost == "low cost" for step in first.steps)
    text = first.model_dump_json().casefold()
    assert "http" not in text
    assert "upload more" not in text
    assert second.read == first.read
    with pytest.raises(AppError) as missing:
        reach_plan(db, settings, review_id, _reach("Nowhere University"))
    assert missing.value.status_code == 404


def test_coach_url_skips_aggregators_and_roster_pages():
    results = [
        {"title": "NCSA", "url": "https://www.ncsasports.org/mens-soccer/coaches"},
        {"title": "Wiki", "url": "https://en.wikipedia.org/wiki/Cal_Poly_Mustangs"},
        {"title": "Roster", "url": "https://gopoly.com/sports/mens-soccer"},
        {"title": "Staff", "url": "https://gopoly.com/sports/mens-soccer/coaches"},
    ]
    assert first_coach_url(results) == "https://gopoly.com/sports/mens-soccer/coaches"


def test_cal_does_not_take_the_cal_state_query():
    programs = [
        {"school": "California", "short_name": "Cal"},
        {"school": "Fullerton", "short_name": "Cal State Fullerton"},
    ]
    assert _program_for_term('"Cal State Fullerton" men\'s soccer coaches', programs)["short_name"] == "Cal State Fullerton"
    assert _program_for_term('"Cal" men\'s soccer coaches', programs)["short_name"] == "Cal"


def test_contact_pick_uses_the_assistant_printed_on_the_page():
    contact = pick_contact(staff_rows(CALPOLY), CALPOLY)
    assert contact["name"] == "Zach Watson"
    assert contact["email"] == "zwatso01@calpoly.edu"
    assert contact["title"] == "Assistant Coach"


def test_recruiting_contact_wins_and_mailto_counts():
    contact = pick_contact(staff_rows(MAILTO), MAILTO)
    assert contact["name"] == "Pat Recruit"
    assert contact["email"] == "recruit@calpoly.edu"


def test_email_not_printed_on_the_page_is_dropped():
    rows = [{"name": "A Coach", "title": "Assistant Coach", "email": "nope@x.edu", "phone": "805-756-2096"}]
    contact = pick_contact(rows, "The desk phone is 805-756-2096.")
    assert contact["email"] is None
    assert contact["phone"] == "805-756-2096"
    assert pick_contact(rows, "No contact is printed.")["email"] is None


def test_heading_block_is_a_staff_row():
    page = "## Pat Recruit\nRecruiting Coordinator\nrecruit@calpoly.edu\n"
    contact = pick_contact(staff_rows(page), page)
    assert contact["name"] == "Pat Recruit"
    assert contact["email"] == "recruit@calpoly.edu"


def test_email_keeps_clip_count_confidence_and_a_grounded_profile():
    stats = STATS.model_copy(update={"clips": 3, "confidence": 37})
    table = stats_table(stats)
    grounded = "These 3 clips back an evidence confidence of 37."
    ability = "The ability estimate is 80."
    assert summary_ok(grounded, table)
    assert not summary_ok(ability, table)
    _subject, draft = draft_email(_body(stats=stats, profile=grounded), "Zach Watson", table, fallback_summary(stats))
    assert "Clips analysed: 3" in draft
    assert "Evidence confidence: 37" in draft
    assert grounded in draft
    _subject, without_ability = draft_email(_body(stats=stats, profile=ability), "Zach Watson", table, fallback_summary(stats))
    assert "80" not in without_ability
    rendered = html_body(draft)
    table_html = rendered[rendered.index("<table>"):rendered.index("</table>")]
    assert rendered.count("<table>") == 1
    assert "Seconds tracked" in table_html
    assert "Clips analysed" in table_html
    assert "Evidence confidence" in table_html


def test_summary_numbers_must_come_from_the_table():
    table = stats_table(STATS)
    fallback = fallback_summary(STATS)
    assert summary_ok(fallback, table)
    assert not summary_ok("The clip shows 15 receives.", table)
    assert not summary_ok("This is a Division I player with 3 receives.", table)
    assert not summary_ok(fallback + " A third sentence adds nothing.", table)


def test_summary_falls_back_when_the_model_adds_a_number(monkeypatch):
    class FakeMessages:
        def parse(self, **kwargs):
            class Response:
                parsed_output = type("Draft", (), {"text": "The clip shows 15 receives and 3 carries."})()
                usage = None
            return Response()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    monkeypatch.setattr("app.opportunities.anthropic.Anthropic", FakeAnthropic)
    text = write_summary(Settings(anthropic_api_key="test-key"), STATS, stats_table(STATS))
    assert text == fallback_summary(STATS)
    assert "15" not in text


def test_coach_search_is_cached_and_names_the_printed_coach(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    _seed(db)
    settings = Settings(apify_token="test-token", anthropic_api_key="")
    calls = {"search": 0}

    def search(settings, programs):
        calls["search"] += 1
        assert [program["school"] for program in programs] == ["Biola University"]
        return SearchResult(
            hits=[CoachHit(school="Biola University", url="https://athletics.example.edu/sports/mens-soccer/coaches", text=CALPOLY)],
            run_ids=["run_search", "run_crawl"],
            actors=["apify/google-search-scraper", "apify/website-content-crawler"],
        )

    review_id = new_id("sub")
    first = find_coaches(db, settings, review_id, _body(), search_fn=search, summary_fn=lambda settings, stats, table: fallback_summary(stats))
    second = find_coaches(db, settings, review_id, _body(), search_fn=search, summary_fn=lambda settings, stats, table: fallback_summary(stats))
    assert calls["search"] == 1
    assert first.cache_status == "live"
    assert second.cache_status == "cached"
    assert second.result_id == first.result_id
    card = first.cards[0]
    assert card.email == "zwatso01@calpoly.edu"
    assert card.coach_name == "Zach Watson"
    assert "Coach Watson," in card.draft
    assert "29.5" in card.draft
    assert "0:" not in card.draft
    assert card.division == "d2"


def test_fingerprint_changes_when_the_stats_change():
    changed = STATS.model_copy(update={"receives": 4})
    assert fingerprint(_body()) != fingerprint(_body(stats=changed))


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, user, password):
        assert password

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def test_test_mode_reroutes_the_email(monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr("app.mailer.smtplib.SMTP_SSL", FakeSMTP)
    settings = Settings(
        smtp_user="app@gmail.com",
        smtp_app_password="secret",
        mail_test_to="me@example.com",
        mail_live=False,
    )
    delivered = send(
        settings,
        "coach@school.edu",
        "2027 Fullback from California, ECNL Regional League: clip stats",
        "Seconds tracked: 29.5\nReceives: 3\n",
        "<p>Hi</p>",
        "alex@example.com",
    )
    assert delivered == "me@example.com"
    message = FakeSMTP.sent[-1]
    assert message["To"] == "me@example.com"
    assert message["Subject"].startswith("[Test for coach@school.edu]")
    assert message["Reply-To"] == "alex@example.com"


def _stored(db: Database, review_id: str, emails: list[str]):
    from app.schemas import CoachCardOut, OpportunityOut

    result = OpportunityOut(
        result_id=new_id("out"),
        review_id=review_id,
        player_email="alex@example.com",
        cards=[
            CoachCardOut(
                school=f"School {index}",
                division="d2",
                conference="Pacific West Conference",
                coach_name="A Coach",
                title="Assistant Coach",
                email=email,
                phone=None,
                url="https://athletics.example.edu/sports/mens-soccer/coaches",
                subject="2027 Fullback from California, ECNL Regional League: clip stats",
                draft="Coach Coach,\n\nSeconds tracked: 29.5",
            )
            for index, email in enumerate(emails)
        ],
        summary=fallback_summary(STATS),
        stats_table=stats_table(STATS),
        rule=LEAGUE_RULE["ecnl_rl"],
        run_ids=[],
        actors=[],
        cache_status="live",
        retrieved_at=utcnow(),
        message=None,
    )
    db.put_opportunity_cache(f"result:{result.result_id}", result.model_dump_json())
    return result


def _send(result, email: str) -> SendIn:
    return SendIn(
        result_id=result.result_id,
        email=email,
        subject=result.cards[0].subject,
        body="Seconds tracked: 29.5\nReceives: 3",
        reply_to="alex@example.com",
    )


def test_unknown_email_is_rejected_and_the_live_cap_holds(tmp_path):
    db = Database(tmp_path / "secondlook.db")
    review_id = new_id("sub")
    result = _stored(db, review_id, ["a@coach.edu", "b@coach.edu", "c@coach.edu"])
    settings = Settings(mail_live=False, outreach_live_cap=1)
    sent: list[str] = []

    def fake_send(settings, to, subject, text, html, reply_to):
        sent.append(to)
        return to

    with pytest.raises(AppError) as unknown:
        send_outreach(db, settings, review_id, _send(result, "stranger@example.com"), send_fn=fake_send)
    assert unknown.value.code == "unknown_recipient"
    assert sent == []

    send_outreach(db, settings, review_id, _send(result, "a@coach.edu"), send_fn=fake_send)
    with pytest.raises(AppError) as duplicate:
        send_outreach(db, settings, review_id, _send(result, "a@coach.edu"), send_fn=fake_send)
    assert duplicate.value.code == "already_sent"
    assert sent == ["a@coach.edu"]

    settings.mail_live = True
    send_outreach(db, settings, review_id, _send(result, "b@coach.edu"), send_fn=fake_send)
    with pytest.raises(AppError) as capped:
        send_outreach(db, settings, review_id, _send(result, "c@coach.edu"), send_fn=fake_send)
    assert capped.value.code == "send_cap"
    assert sent == ["a@coach.edu", "b@coach.edu"]


def test_missing_token_is_a_clear_error(tmp_path):
    client, _application = make_client(tmp_path / "no-apify", apify_token="", anthropic_api_key="")
    with client:
        response = client.post(
            f"/api/reviews/{new_id('sub')}/programs",
            json={"state": "California", "league": "ecnl_rl"},
        )
    assert response.status_code == 503
    assert "APIFY_TOKEN" in response.json()["user_message"]
