# SecondLook: start building

1. Extract this entire folder, including its .agents and .cursor directories. Open it in Cursor. You may rename the folder secondlook.
2. Paste the contents of CURSOR_START_PROMPT.md into a new Agent conversation. It will create the app directories and build M0; this kit itself contains planning/context assets, not an implemented app.
3. Provide one permissioned football clip and put your Claude API key in your local environment. Never paste the key into chat or commit it.
4. Show the rough real loop to a mentor around the 90-minute checkpoint. Continue using docs/10_CURSOR_PROMPTS.md and the milestone plan.

The complete PDF is in reference/. The same content is split under docs/ so Cursor can read selectively. Start with AGENTS.md, HACK.md and docs/STATE.md. Document reads still consume tokens; the files reduce repeated explanations, not context cost to zero.

George Kalangi's six original hackathon skills and support files are already in .agents/skills/. Their MIT license and exact source commit are under third_party/calhacks-kit/. Restart the Cursor agent session if skills do not appear, or explicitly ask it to read a named SKILL.md. Do not install the same skills again into a second directory.

The bundled event preset is older than the checked event rules. HACK.md and docs/08_SPONSORS_AND_COSTS.md preserve the current deadline and track guidance. Sponsor accounts, credits, GPU access, footage and model performance have not been verified on your machine.

No footage, API keys, live model results, fabricated athlete profiles or prebuilt application code are included. sources/ contains the user-provided event briefing; it is reference material, not an always-read context file.
