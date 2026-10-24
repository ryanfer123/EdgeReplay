# EdgeReplay

Build a local telemetry workbench for importing recorded CSV signals or raw CAN
frames, checking their contracts, replaying them in the browser and inspecting
prediction disagreements without connecting hardware.

Visual direction: a light instrument sheet (#F5F7FA), navy ink (#20314A), cobalt
signals (#315DDC), teal channels (#087F84), coral event markers (#CC674D), and white
panels. Manrope carries readable controls and a large two-line title. The focal
asset is the user's actual waveform, not a decorative illustration. A compact
transport bar leads into traces, a frame inspector, channel contracts and model
comparison. GSAP introduces the heading and waveform; Lenis is the sole scrolling
engine, chosen over Locomotive because native document flow suits a workbench.
Reduced motion bypasses both. No Three.js: two-dimensional signals are clearer.
Solar icons come from Iconify; font and motion packages are served locally with
license notices. No invented endorsements or measured results.

1. Parse and validate bounded signal CSV and CAN float-pair recordings.
2. Persist sessions with source checksums and inspectable validation summaries.
3. Build replay, pause, speed, scrub, channel selection and signal plots.
4. Compare optional expected/predicted labels and expose disagreements.
5. Test parser/math/HTTP/persistence, build a wheel, and inspect desktop/mobile UI.
