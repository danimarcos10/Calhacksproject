# What happens after the hackathon

## First week: test the customer hypothesis
Interview a small set of college/community coaches and players about their actual submission and review workflow. Ask for examples of decisions, not feature wish lists. Identify whether the most valuable product is coach triage, athlete evidence preparation, or both. Test the product against the existing tools those people already use.

Collect a permissioned evaluation set across camera angles, lighting, distances, jersey similarity and football contexts. Separate event detection, target attribution, visibility, evidence retrieval and report usefulness. A single overall “AI accuracy” score would hide the failures that matter most.

## Next technical work, in order
1. Improve identity correction and scene-boundary handling before increasing video duration.
2. Build a stronger evaluation harness with independently labeled incidents and explicit uncertainty.
3. Add private object storage, proper organization/user authorization, a production job queue and robust deletion/retention.
4. Validate position-specific evidence rubrics with coaches. Only then consider carefully defined ratings and domain calibration.
5. Explore full-match processing, pitch calibration or ball tracking as separate measured projects, not prompt changes.
6. Test whether evidence requests and athlete responses create a useful ongoing workflow.

## What would justify continuing
A coach can complete a real review task more effectively, wants to use the tool again, and trusts the evidence/correction model enough to bring another submission. A player understands what footage is missing without interpreting the system as a judgment of personal potential. The system's failures are legible and recoverable.

## What would justify changing direction
Coaches already solve the problem adequately in existing tools; target attribution fails on the footage users actually have; the product creates more verification work than it saves; or the primary need turns out to be something outside video analysis. Those are useful findings. The modular evidence pipeline can still support a different review workflow.

## Keep the hackathon promise bounded
The ambitious deliverable is a functioning evidence-review product with a compelling correction loop and honest measured behavior. It is not an end-to-end recruiting platform, a scouting model validated across populations, or a proven scholarship-outcome intervention. A clear working system is a stronger foundation for the next experiment than a large feature list whose outputs cannot be defended.
