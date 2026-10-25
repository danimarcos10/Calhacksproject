# A cost plan that fits the available credits

## Model choice and example arithmetic
The official Claude model documentation checked for this plan lists claude-sonnet-5-5 at $2 per million input tokens and $10 per million output tokens. Use actual API usage for accounting; image token cost depends on input handling and resolution. Do not estimate it from video duration alone. [S09]

Illustrative assumption: one call bills 20,000 input and 2,000 output tokens. Cost = 20,000 x $2/1,000,000 + 2,000 x $10/1,000,000 = $0.06. Three such calls cost $0.18. Thirty three-call jobs cost $5.40; one complete repeat doubles that to $10.80. These are arithmetic examples, not measured SecondLook costs or guaranteed provider charges.

## Proposed weekend budget
| Item | Working allowance | Control |
| --- | --- | --- |
| Claude application experiments | $15 maximum initially | Usage ledger + app stop limit |
| Final demo / retries reserve | Keep remaining credit available | Cache exact successful inputs |
| Local CPU video processing | Existing machine | Bounded windows and disk usage |
| Paid GPU | $0 by default | Use only an approved, priced allocation |
| Jev experiment | Tiny capped trial if chosen | Text-only routing; actual usage log |
| Hosting | Local first | Approved existing account before provisioning |

The verified $50 Claude API offer should cover this illustrative application workload if approved and if measured usage is similar. Do not count it as available until it appears in the account. It is separate from Cursor usage or a Claude subscription; check the exact entitlement of any coding tool before assuming this credit funds it. [S04]

## Controls to implement
Before every paid call, check session and job budgets. Store model, input/output tokens, estimated cost, final actual cost where available, attempt number and cache status. Default to no more than three model calls per job and one active analysis. Reduce frame count or ask for a shorter window before changing to an untested model.

Jev's listed $0.042/M input price makes 20,000 billed input tokens $0.00084, excluding any other provider or hosting cost. Cheap routing does not replace vision analysis. Measure SDK-reported usage rather than assuming a textual state is billed only once across every question. [S12]

Apify, Bright Data, Mana and Azure credits are separate balances for separate services. They cannot be added into a general compute wallet or used to pay the Claude bill.

---

# Primary sponsor strategy

## Priority 1: Anthropic - Claude for Public Benefit
Current sponsor criteria emphasize a specifically named community, a real problem experienced or validated with that community, a fully working useful product, meaningful Claude use and a plan to measure impact. The verified reward is $5,000 in Claude credits, a year of Claude Max 20x for the winning team, Applied AI office hours and an invitation to Anthropic HQ. These are not a $5,000 cash prize. [S05]

For SecondLook, the strongest honest framing is a defined group of players with limited recruiting support and the coaches helping review their footage. The community hypothesis must be validated. Show the actual evidence workflow, a failure handled responsibly, and a small real review-time or usefulness measurement. Do not claim scholarships won or improved recruitment outcomes during the weekend.

Proof to save: real Claude run metadata, the named user/problem, a permitted feedback note, evidence links, correction behavior, measured review task and a short account of failure modes. This is more useful than adding a sponsor logo.

## Priority 2: Microsoft - Built for the Real World
The current sponsor post asks for a production-minded AI agent, customer understanding, measurable usefulness, a path from prototype to production, responsible design and end-to-end functionality. The grand prize lists a Surface laptop per winning team member, an FDE-team presentation and senior-FDE mentorship; the Customer Impact award lists the presentation and mentorship. [S06]

The bounded controller that validates footage, requests more frames when useful, assembles evidence and handles corrections gives you a concrete agent story. Show persistence, limits, latency/cost measurements and one customer observation. The checked sponsor wording does not explicitly require Azure; confirm any additional rules at the booth rather than assuming a forced cloud migration is necessary.

## General awards
People-First Social Impact, Technical Complexity and overall awards are plausible fits if the implementation earns them. The supplied briefing says organizers automatically consider teams for main tracks; sponsor tracks require their own criteria and opt-in. Published general rewards include Apple Watch SE 3 for People-First and NuPhy Air60 HE for technical complexity. Verify final submission options. [S03, S25]

## Submission evidence structure
For each chosen track, write: requirement; implemented feature; file/API/run proving it; demo moment; remaining limitation. If a requirement is not actually met, drop the track. This plan does not guarantee eligibility, judging preference or a prize.

## Convex: Best Use (implemented)
Requirement as read on Devpost (02:50 UTC): "Use real Convex features like live queries and components to win."

**Demonstrated on 2026-10-25** (browser and `scripts/check_convex.py`, local deployment):
- **Schema:** 10 tables, with indexes for windows by submission, runs by window, selection and key, and decisions by observation (`apps/web/convex/schema.ts`).
- **Live queries:** `review.get` and `review.inbox` through `useQuery`. With two tabs on one submission:
  - A reject with a reason in one tab moved the moment to History in the other, without a refresh.
  - A footage request saved in one appeared in the other and persisted after reload.
  - A correction saved on the Prepare page made the accepted moment stale in the open review tab.
  - The queue status, cost and new suggestions appeared as the worker published.
- **Mutations:** `review.ts` refuses decisions on stale moments, saves on top of a newer selection, estimates relabelled as manual, and duplicate queue entries.
- **Worker functions:** `worker.ts`, gated by the `WORKER_SECRET` environment variable. The Python worker calls them with the official `convex` client.
- **Durability:** decisions survived a refresh and a restart of the API and the Convex backend.

**Not used:** Convex Auth, and the Workflow and other components. Workflow was assessed and deferred, with the reason in `docs/DECISIONS.md`. The demo used a local deployment; a cloud dev deployment needs `npx convex login`.

**Unverified:** eligibility, the prize amount (two sources conflict), and how a solo entry is treated when the listing says "Team required: 2 to 4 members".

Devpost paragraph: *SecondLook keeps the coach review in Convex. Model observations are immutable records. Coaches' accept, reject and correction decisions are append-only and tied to the exact player selection they judged. When a coach corrects the player, a single mutation moves the window to a new selection. Every open review session sees the old evidence go stale and leave the playlist and summary at once. The local Python worker claims analysis jobs from a Convex queue with a lease, runs the video and Claude pipeline, and publishes results idempotently, so a retry never pays twice.*

---

# Optional sponsor tracks: adoption has a price

| Track | Real integration needed | Reward snapshot / recommendation |
| --- | --- | --- |
| Meta: Bringing People Closer Together with AI | A working coach-player feedback loop with essential AI; SAM alone is not the theme | Conditional Round 2 invitation, travel/accommodation and swag. Pursue only if human connection is clear. |
| Elastic: Agent Builder on Serverless | An actual Serverless Agent Builder tool/agent retrieving current evidence with citations | Quest 3S first, Bose QuietComfort second. Useful optional evidence search; not P0. |
| Apify: Best Use / Best Actor | A working public-data Actor or meaningful Actor integration | $2,000/$1,000/$800/$400/$400; separate $400 Actor award. Opportunity discovery is a separate feature: defer. |
| Bright Data: public web data app | Live public data essential to core; resilient real demo | Credits + Amazon cards. Poor fit for a private video reviewer; do not bolt on scraping. |
| Convex: Best Use | Meaningful reactive backend | Snapshot said EP-133 K.O. II + ESP32-S3 display board; the Devpost listing read 2026-10-25 says "$5,000 cash to the winning team". Unresolved; confirm with organizers. Adopted as a priority on 2026-10-25; see "Convex: Best Use (implemented)" below. |
| SpacetimeDB: Best Use | Meaningful live shared state / sync | $2,048/$1,024/$512 cash. Multi-reviewer sync is optional, not needed for this demo. |
| Mana: Best Hack Built with Mana | Honest meaningful use, accessible build pages/chats and stage evidence | Sponsor advertises $5,000. Keep Cursor as requested; do not change builder solely for this prize. |

Track facts above come from the supplied Hacker Guide/briefing and current sponsor posts where available. Meta's reward is conditional, and device quantities/fulfillment should follow final rules. [S02, S03, S18, S19, S25]

## If Elastic is already available
Index only current evidence records with player ID, role, category, source range, review state and observation ID. Expose bounded tools such as find_evidence and find_gaps through Agent Builder. Filter rejected/stale records out of current answers. Use a query like “show reviewed defending examples for these submissions,” then return playable citations. An ordinary Elasticsearch index by itself does not satisfy an Agent Builder requirement. [S16]

## If exploring opportunity discovery later
Use Apify or Bright Data for public, permitted opportunity pages with source URL, retrieved_at, deadline and verification status. Matching eligibility and scholarship amounts is a separate accuracy problem. Keep it outside the final video-review journey unless the core is complete unusually early.

Do not add both web-data providers. Bright Data's current rules disqualify login/paywall scraping, non-public personal data and mocked/hardcoded demo data. A replay fallback suitable for the core product does not satisfy that track's live-data requirement. [S18]

---

# Credits: what is actually available to claim

No credits were redeemed while preparing this package. “Verified offer” means a source advertises it, not that your account has been approved or credited. Claim the services you need first and confirm the visible balance and expiry.

| Provider | Offer | Claim route and practical use |
| --- | --- | --- |
| Claude API | $50 per hacker for the weekend | Event offer link [S04]. Highest priority: core visual analysis. Contact Arinze in the credit thread for approval problems. |
| Apify | $200 credits | Coupon APIFY_CAL_HACKS; signup link [S17]. Existing accounts: Billing > Subscription > Promo Code. Only useful if you build public-data work. |
| Bright Data | $300 credits | Event signup URL [S18]. Core product does not need it; avoid spending setup time solely to collect it. |
| Mana | $150 credits per hacker | Starter pack [S19], access code advertised as CALHACKS. Separate builder/platform balance, not Cursor credit. |
| Azure for Students | $100 for eligible students | Standard student offer [S15], not an additional event grant. Use only after eligibility and service access are verified. |
| Figma Education | Education features after verification | Student signup and education verification [S03]. Useful if already familiar; not a cash/API grant. |
| Notability | One month Pro | CALHACKS in the supplied briefing. Separate from the one-year winner reward. |

## Five-minute redemption checklist
Open the official/event link, check account eligibility, apply the code if needed, inspect the credited balance and expiration, and set a spending limit where supported. Save only the entitlement status and date in a private team note; never commit a key, billing screenshot with personal data, or redemption token.

## What not to count as available cash
The four explicit event balances for Claude, Apify, Bright Data and Mana total $700 nominally, but they are separately usable services. Only $50 of that total directly funds the recommended Claude application calls. Azure adds a conditional student balance. Winner credits are not funds you can spend before judging.

## Recommended action order
Claim Claude now. If deployment is actually needed and you qualify, confirm Azure access while the core builds. Skip new signups for web scraping, voice, finance and additional databases unless an accepted milestone genuinely needs them. Do not pool keys or work around provider account restrictions to combine allocations.

The supplied briefing records some other benefits whose amounts are not confirmed. Those are listed on the next page so Cursor does not invent a number or treat a prize as a participant grant.

---

# Unverified amounts, conflicts, and tracks to skip

## Benefits that need confirmation before budgeting
| Provider | What the supplied briefing establishes |
| --- | --- |
| Cartesia | Code CARTESIACALHACKS for first-time users/orders; amount unspecified. Voice would need to be central for its track. |
| Factory | Participant inference/agent/compute access announced, amount unspecified. $200/member is a winner reward, not a universal grant. |
| Bitdeer | Participant API credit request exists; allocation unspecified. $500/$200 figures are winner credits. |
| CREAO / Context.dev | Starter/event credits mentioned; amount not verified. Confirm with sponsor before depending on them. |
| Runpod / AWS | No universal event GPU or AWS grant verified in the supplied research. Do not assume a free GPU exists. |
| SpacetimeDB | Up to $50,000 startup program is conditional, not attendee credit. |
| MongoDB / MLH | $50 student offer or free tier, eligibility applies. Another database is unnecessary here. |
| DigitalOcean / Vultr / other MLH offers | Credit/promo access mentioned; exact local entitlement requires confirmation. |
| SpaceXSI | Booth code for a one-month bundle; exact Cursor/Grok entitlement needs redemption verification. Not established as a universal Cursor API budget. |
| Jev / Elastic | No quantified Cal Hacks participant credit verified for this plan. |

## Conflicts worth preserving, not guessing through
Fetch.ai's latest sponsor post in the supplied briefing lists $1,250/$750/$500 plus two $250 recognitions; older Hive/Devpost figures differ. Figma's detailed sponsor brief and Devpost disagree on category mapping while totaling $5,000. SpaceXSI's Grok requirement varies between the guide and sponsor pack. Confirm at the relevant booth if pursuing one of these tracks. [S03]

## Poor fits for this product
Hyphenate finance automation, Visa shopping, Coinbase payments/trading, Capital One banking, CRS credit/identity, Atlassian workplace apps, and space-themed challenges would require a different core product. Factory requires Droid doing real work inside the running application; merely using it to write code is insufficient. Fetch.ai requires Agentverse/Agent Chat Protocol/ASI:One discoverability. CREAO requires a core CREAO agent and submission evidence. Do not add them as cosmetic dependencies.

## A sponsor decision rule
Keep a new integration only if you can identify the exact user-visible improvement, the requirement it satisfies, and a working demo within a strict timebox. With fewer than six hours left, the only defensible additions are fixes required to finish the committed journey. Prize totals are not expected winnings and should not determine architecture by themselves.
