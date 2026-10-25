# SecondLook

Review a short football clip, mark one player, and read candidate observations that seek back to the source. Observations stay unreviewed. The app does not produce ratings or odds.

## Run

From `secondlook/`, with Python 3.12 and FFmpeg on PATH:

```powershell
python -m venv services\api\.venv
services\api\.venv\Scripts\python -m pip install -r services\api\requirements.lock
copy .env.example .env
```

Put `ANTHROPIC_API_KEY` in `.env`. Do not commit that file.

```powershell
services\api\.venv\Scripts\python scripts\check_provider.py
services\api\.venv\Scripts\python -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd apps\web
npm install
npm run dev
```

Open http://localhost:3000. The page calls http://localhost:8000.

`EVIDENCE_PROVIDER=synthetic` serves a labelled fixture instead of Claude. Leave it unset for a real run. A failed Claude call does not fall back to the fixture.

## Checks

```powershell
cd services\api
.\.venv\Scripts\python -m pytest
cd ..\..\apps\web
npm test
```

Regenerate the web types after an API change:

```powershell
cd apps\web
npm run types
```

## Footage

The demo clip is local only. Licence and attribution are in `fixtures/RIGHTS_MANIFEST.json`. Do not publish the file.
