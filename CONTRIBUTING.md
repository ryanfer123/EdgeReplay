# Contributing

Start with a reproducible recording and the behavior that should change. Keep
parsing deterministic and reject malformed inputs rather than inventing values.
Preserve source order for same-timestamp CAN bursts. A new protocol profile needs
explicit byte ordering, units, field positions, malformed-frame tests, and an
export round-trip example.

Run `python -m unittest discover -s tests -v` before submitting a change. For the
frontend, check desktop, narrow mobile, keyboard navigation, replay transport,
range notices, import errors, and reduced motion. Labels must always be described
as imported comparisons unless a separately verified model runner is introduced.
Never claim a model was executed, hardware was exercised, or performance was
measured based only on fixture tests.

Useful next extensions include explicit DBC schema import, configurable unit
metadata, more careful min/max waveform decimation, timestamped annotation export,
and adapters for independently recorded model outputs.
