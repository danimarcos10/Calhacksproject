# Synthetic fixture

This folder is not football footage and not a football analysis.

`coloured-boxes.mp4` is a generated clip of flat colour and a red box. Pytest builds its own timestamp clips under a temp directory. The API uses these pictures only when `EVIDENCE_PROVIDER=synthetic`. That mode is for plumbing tests. The review page keeps a banner up: "SYNTHETIC FIXTURE, not football analysis."

A real provider failure never falls back to this fixture.
