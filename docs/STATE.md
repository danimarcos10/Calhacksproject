# Current state

Status: program lists sort every Division I and Division II school in the state into good fit, possible, and reach. Fit is a league rule, not a prediction. Reach schools are not emailed. "What would it take?" returns a short plan: a local coach or volunteer, asking one club about fee help, filming from the halfway line, and a note that names the conference. Without a Claude key the plan is labelled standard steps.

The scout screen takes up to six clips of one player. Each clip is tracked on its own, and the player is clicked once per clip. Evidence confidence (0–100) comes from Convex. Rejected and stale moments count nowhere. One Claude call then writes a description, cited qualities, gaps, and an unverified ability estimate, hidden below confidence 40. The estimate is not put in the coach email.

Open http://localhost:3000/scout. A finished example is `/review/sub_05f77d9ac2d14107`. The stadium review is `/review/sub_32eb531dc1444352`.

Demo clip: `data/footage/dfl-0bfacc_0.mp4`, 30.0 seconds, 1920x1080, 25 fps. Rights are unconfirmed. `can_publish` is false. Tracks are cached by file hash.

Convex cloud dev: team daniel-bc765, project secondlook, deployment proficient-cheetah-424. Run `npx convex dev` and `npm run dev` in `apps/web`, and the API with `services\api\.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000`. The API does not reload. Restart it after a Python change.

Verified 2026-10-25: `pytest tests/test_opportunities.py` passed. `npx tsc --noEmit` in `apps/web` passed. On the finished review, high school in California listed Division II first and Stanford, Cal, and UCLA last as reach. Stanford's plan was written by Claude. Finding coaches for Biola did not include Stanford. Mail is not configured, and Biola's page printed no email, so no test send went out.

Next: set the Gmail app password and MAIL_TEST_TO, then send one good-fit email in test mode.
