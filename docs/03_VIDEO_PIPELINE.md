# Media ingestion and truthful timestamps

## Accept less, validate more
For the demo, accept MP4/MOV uploads up to 200 MB and 90 seconds, with a configurable cap. Validate the decoded media rather than trusting the extension or browser MIME type. Check duration, video stream, resolution and rotation before allocating expensive work. Limit concurrent decodes to one. Reject malformed, zero-length and excessive-resolution inputs with an actionable message.

Store the original under a generated ID. Use ffprobe to persist codec, dimensions, rotation, frame-rate information, stream start time and duration. If needed, create a browser-compatible H.264 MP4 proxy with a bounded resolution, yuv420p pixel format and fast-start metadata. Preserve the original separately. Do not silently reinterpret portrait rotation or alter the analysis window.

## Time is a contract
The canonical timeline is elapsed playback time in the oriented source video. Variable-frame-rate footage means frame_number / assumed_fps is not a reliable source timestamp. Use decoded presentation timestamps, normalized to the first displayed video frame, and persist the mapping for every sampled frame.

| Manifest field | Meaning |
| --- | --- |
| frame_id | Server-issued reference used by model outputs |
| source_t_ms | Milliseconds on the canonical source playback timeline |
| derivative_t_ms | Time within the analysis window or proxy |
| source_pts | Decoded presentation timestamp for audit/debugging |
| width, height | Actual dimensions after orientation/resize |
| anchor_revision | Identity selection version used for this frame |
| image_sha256 | Exact bytes sent for analysis, for reproducibility |

If a derivative starts at source time s, its local time t maps to source time s+t only when the transcoding pipeline preserves this relationship. Confirm this with a frame at a known event. Do not depend on fast keyframe seek alone when exporting a precise interval; re-encode the short excerpt or verify the actual start offset.

## Sampling defaults
Analyze an explicit 6-8 second window, not an entire match. Begin around 2 frames/second, capped at 16 frames. If an action needs closer inspection, request one narrower, denser window, capped at 24 frames. Those are cost controls, not enough evidence for every football action. If contact or ball outcome falls between samples, say it is unobservable.

Keep full-frame context at a manageable resolution, approximately 960 pixels on the long edge as a starting point. A target crop may supplement it, but cannot replace field context. Test your actual input quality; a distant player may remain too small after resizing.

---

# Player selection, tracking, and identity boundaries

## M0: make identity explicit
Ask the user to draw a box around the target on the first, middle and last sampled frames where the player is visible. Store normalized coordinates, frame ID, optional jersey note and team-color note. These notes are user assertions, not independently verified identity. Allow a frame to be marked “target not visible.”

Do not paint an interpolated box as if a model tracked it. Between manual anchors, label its origin as interpolated/unverified and inspect it before use. The first version may ask for extra anchors on ambiguous frames. Any observation spanning an uncertain identity segment must be withheld or sent for explicit human review.

## Coordinate mapping
For an oriented image W by H in a canvas Cw by Ch using contain-fit, set scale = min(Cw/W, Ch/H). The rendered image offsets are ox = (Cw-scale*W)/2 and oy = (Ch-scale*H)/2. A CSS click (x,y) maps to normalized coordinates ((x-ox)/(scale*W), (y-oy)/(scale*H)). Reject clicks in the letterbox margins. Keep CSS and device-pixel coordinates distinct.

Apply the same orientation before selection, tracking and model input. Test portrait rotation and browser resize. The stored rectangle must survive a round trip from normalized coordinates back to the rendered image without moving to another player.

## Optional SAM 2.1 path
Use the official Meta SAM 2 video predictor with point/box prompts and corrective prompts. Start with the small checkpoint, sam2.1_hiera_small.pt, and its matching config. Follow the repository's installation requirements on the actual machine. A usable CUDA environment is a prerequisite for the planned timebox, not something this plan guarantees. [S11]

Process short windows, one target at a time. Convert masks to proposed boxes and store frame-level state. Stop or ask for a new anchor at a shot cut, a long occlusion, an implausible jump or overlap ambiguity. Heuristic thresholds are tunable warning signals, not calibrated identity probabilities.

## No identity magic
SAM tracks prompted visual objects; it does not establish who a player is across unrelated videos. Each new clip needs an explicit link to the submitted player and a new selection. Do not use face recognition, infer a name, or assume a jersey number is globally unique.

At the end of the 60-minute spike, keep SAM only if an overlay remains on the correct player in all frames you manually inspect across two clear windows and one crossing/occlusion window. Record the sample and failures; do not describe this small check as validated tracking accuracy.
