# Choose a buyer, a beneficiary, and a single job

## Working customer hypothesis
Start with a college assistant coach or community football coach reviewing player-submitted video. Narrow the initial role to an outfield fullback. The beneficiary hypothesis is a public-school player without access to expensive recruiting support. Validate this framing with an actual affected player or coach before presenting it as evidence of impact.

The job is: help me decide which moments deserve a closer look and what additional footage I need. Do not build admissions, financial aid, eligibility determination, coach outreach, or a university marketplace during this hackathon. Recruiting practices vary; the premise that every US university uses an identical video workflow is too broad.

## The final demo journey
1. A submission has an alias, role, two short clips, and athlete-entered context. A coach opens it from a review inbox.
2. The coach selects a target player and short windows. The system produces observations with clickable evidence and stated limits.
3. One observation is disputed: wrong player, obscured ball, or inference stronger than the visible action. The coach corrects the anchor or rejects the observation.
4. The affected analysis becomes stale; recomputation updates the evidence summary and leaves a revision history.
5. The coach compares the available evidence with another submission and creates an in-app request for a missing type of footage.

## Position-specific observation categories
Use first touch, passing action, carrying action, defending action, and off-ball movement as organizational tags. A clip may support a concrete action within one category. It usually cannot support a durable ability score. For example, “visible pass toward a teammate at 00:23-00:25” is narrower than “elite passing.” A recovery movement is not proof of defensive awareness.

## Keep and cut
| Keep in the committed journey | Cut for this event |
| --- | --- |
| Video review and source intervals | Full 90-minute automatic analysis |
| Explicit player selection | Automatic identity across different matches |
| Evidence coverage by category | Global talent score / scholarship probability |
| Human correction and revision | Injury, personality, work ethic inference |
| Two or three clips per player | Public player marketplace or payments |
| Two or three demo submissions | Emailing coaches or scraping private profiles |

Competition already includes video, player profiles, clips, search, and AI summaries. Position the distinct demo around evidence provenance, visible gaps, and corrections on ordinary submissions. Do not claim to have invented AI scouting or to outperform incumbent systems without a comparison. [S20]

---

# Multi-clip profiles without misleading ratings

## Aggregate evidence, not talent
For each player and category, show accepted observable actions, distinct declared matches, reviewed window duration, unresolved candidates and gaps. Display the total source video duration separately from the union of analyzed windows and the union of human-reviewed windows. Never label 20 seconds of sampled analysis as a full match review.

Use interval unions so overlapping windows are not counted twice. Deduplicate exact files by hash and allow repeated highlights of the same incident to be grouped. A second crop of one event is not independent evidence. A second file is not necessarily a second match.

## Deterministic evidence tiers
| Tier | Rule for this demo | UI wording |
| --- | --- | --- |
| No reviewed evidence | Zero current accepted observable actions | Not yet evidenced |
| One example | One distinct accepted incident | One reviewed example |
| Several examples | Two or more distinct accepted incidents, one match | Several examples in one match |
| Across matches | Accepted incidents from >=2 declared matches | Examples across submitted matches |

These are product labels for coverage, not validated statistical thresholds. More clips can increase evidence breadth without proving greater ability. A poor camera angle must reduce observability, not silently lower a player score.

## Profile content
Header: alias, self-declared position and submission status. Evidence summary: short text with observation links. Category sections: coverage tier and specific reviewed incidents. Limits: unseen situations, uncertain identity and sampling constraints. Revision history: what changed after correction. Next footage request: a concrete missing scenario, phrased as a request for evidence rather than a judgment.

Example request: “Please add a continuous clip showing the buildup and outcome of a defensive one-on-one; the current window ends before the outcome.” This is more actionable than “improve defending.” Do not prescribe health, training load, or injury advice from the video.

## Comparison view
Compare two or three submissions side by side using the same categories. Each cell links to source evidence and states coverage. Do not sort candidates by a hidden overall score. Start with user-chosen order or submission time. Show different sample sizes and camera quality prominently enough that the comparison cannot be mistaken for equal-condition testing.

If a coach wants recruitment decisions, the product's answer is an evidence packet they can inspect. Selection remains their task. No scholarship prediction, automatic rejection or outreach is part of this implementation.

---

# Interface design that makes the hard part visible

## Three screens are enough
| Screen | Essential controls | Visible value |
| --- | --- | --- |
| Inbox | Submission list, role filter, review state | Find the next submission needing attention |
| Review workspace | Video, interval, target anchors, evidence cards | Verify and correct a claim without leaving footage |
| Profile / compare | Category coverage, linked moments, gaps | See what is supported and what to request next |

Use a restrained dark-navy or neutral surface, one green accent for accepted evidence, amber for uncertainty and gray for unavailable information. Never rely on color alone. Keep readable text, explicit buttons and keyboard focus. Spend design time on the video workspace before the landing page.

## Reviewer layout
On a wide screen, give approximately two-thirds of the width to the player and timeline, one-third to evidence cards. Under the video, show target identity status and the currently selected interval. Evidence cards contain a short action, source time, review state and one limitation. Selecting a card seeks the video and highlights its interval.

The “Correct player” action should be easy to find. It pauses playback, opens the anchor editor, shows the new revision, and explains which results will be recomputed. Disable acceptance of stale claims. After rerun, show what changed rather than replacing the old text with no explanation.

## Honest loading and empty states
- No video: explain the accepted format and short demo duration.
- No provider key: upload and selection still work; analysis says setup required.
- Ambiguous footage: show the limitation and a specific next action.
- API failure: preserve the upload and anchors; offer retry without re-upload.
- Cached result: show analyzed time and model version; do not animate a fake live run.
- Replay mode: show a persistent “Recorded result / replay” label.

## Features worth leaving out
No elaborate marketing site, onboarding carousel, accounts, notification center, payment page, social feed, 3D avatar, radar chart of invented ratings, or general chat box. A chat interface is useful only if it retrieves existing observations with citations. A role/category filter is faster to build and easier to trust for this demo.

Give the coach a small processing summary: source length, analyzed windows, accepted observations and known gaps. These operational facts are more credible than arbitrary numerical attributes.
