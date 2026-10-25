# Applied skills and verification

- **build-awwwards-quality-sites + frontend-design:** defined the instrument-sheet
  direction in PLAN.md before implementation; a real waveform is the focal asset.
  Deliberate typography, transport controls, channel inspector, and contract table
  support the investigation workflow. Solar icons, Manrope and motion libraries
  have recorded provenance. No award or third-party endorsement claim is made.
- **karpathy-guidelines:** bounded the first release to recorded data inspection,
  explicit CAN float pairs, and imported-label comparison. The app never implies
  live hardware, model execution, guessed units or missing data reconstruction.
- **python-testing:** exercised edge cases and real HTTP/SQLite behavior with
  isolated temporary fixtures, deterministic assertions, and coverage measurement.
  Standard-library unittest keeps the default test command dependency-free; pytest
  and coverage are optional development tools.
- **frontend-testing-debugging:** the target flow is app load → sample/import →
  replay/pause/scrub → select a channel → inspect contracts and labels → export.
  Browser checks exercised this full workflow on desktop and mobile.

The Python engine/API milestone passed 17 tests before the frontend was completed.
Browser verification: 24 October 2026, macOS. Final tests and package build rerun
on 25 October 2026 with the same passing results:

| Check | Result |
| --- | --- |
| Regression suite | 23 passed, 32 subtests |
| Engine/API statement coverage | 100% for telemetry.py and server.py, 224 statements |
| Python lint | Ruff passed |
| JavaScript syntax | node --check passed for app.js and motion.js |
| Wheel build | Passed; complete locally served frontend assets verified in archive |
| CLI | Inspected bundled CAN recording and exported 36 parsed frames |
| Desktop browser | Sample import, play/pause, channel switch, seek End, restart, next sample |
| Mobile browser | 390px wide; controls work, no horizontal overflow |
| Raw CAN | Imported 36 frames / 5 channels and inspected decoded values |
| Label audit | Synthetic 3-row recording: 3 pairs, 1 mismatch, 66.7% agreement; jump works |
| Reduced motion | reduce=true, Lenis=false, heading visible; preference restored |
| Console | No application errors in checked interactions |

Browser QA used the available shared browser through the computer-use integration.
There is no committed automated browser test runner. Screenshots are
[desktop](screenshots/desktop.jpg) and [mobile](screenshots/mobile.jpg).
The mobile image predates a whitespace-only copy correction; the desktop image
shows the current copy. Both represent synthetic fixture data, not live telemetry.

Motion uses GSAP with ScrollTrigger and a single Lenis instance. Locomotive was
not chosen because native document flow better suits the workbench. Reduced
motion bypasses initialization. Cleanup removes listeners/ticker callbacks,
destroys Lenis, cancels replay frames, and pauses replay when the document hides.
Three.js is omitted because two-dimensional plots convey these recordings more
clearly. Static headings and a no-JavaScript CLI notice remain readable without
motion or application scripts.

No hardware, live CAN bus, trained model inference, Python/C++ prediction parity,
vehicle fault-detection quality, or real-time playback accuracy has been verified.
