# Changelog

All notable changes to **mcp-nec2-antenna** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **`nec2_create_yagi` no longer invents its gain figure.** It reported
  `expected_gain_dbi = 7 + 2*num_directors`, which is unbounded (47 dBi at
  twenty directors) and overstated the gain of its own generated deck by
  10.9 dB for a 7-element array at 434 MHz. The tool now runs `nec2c` once at
  the design frequency and reports what the solver computed, together with
  `gain_basis: "simulated"`. Where the solver is unavailable it falls back to a
  boom-length regression fitted to 72 nec2c runs (0.63 dB RMS, 1.39 dB worst
  case over 3-20 elements and 14-435 MHz) and labels it
  `gain_basis: "estimated"`, naming the method and the reason in `gain_method`.
- **Yagi geometry could fire out of the back.** Element lengths were fixed
  fractions of a half wavelength while the wire radius stayed at 2 mm, so at
  UHF the electrically fatter wire left the directors long enough to act as
  reflectors: NEC put the main lobe at phi = 180 for 4 and 5 element arrays at
  434 MHz, and forward gain fell as elements were added. Element lengths are now
  scaled from the resonant length for the wire gauge actually in use, with
  standard ratios (reflector 5% longer than driven, directors 5% shorter,
  tapering) and 0.2 lambda director spacing in place of 0.3 lambda. Verified with
  nec2c from 14 MHz to 1296 MHz and 3 to 20 elements: main lobe on the boom
  axis throughout, front-to-back positive, forward gain monotonic in element
  count.
- **`nec2_simulate` reported the wrong frequency's pattern.** The parser kept
  only the first radiation-pattern block in the file, so a +/-10% sweep returned
  the pattern computed at 0.9x the design frequency as though it were the
  design-frequency pattern. Patterns are now parsed per frequency and the one
  nearest the design frequency is reported, with its frequency included. A peak
  below 0 dBi is also no longer clipped to 0 dBi.

### Added
- `wire_radius_mm` on `nec2_create_yagi`. Element lengths now depend on it, so
  it needs to be settable.
- `boom_length_m` and `boom_length_wavelengths` in the `nec2_create_yagi`
  response.
- `tests/test_yagi.py`: regression coverage for both defects, including
  comparison of the reported gain against an independently parsed `nec2c` run.
  Tests that shell out to the solver carry the `nec2c` marker and skip when it
  is not installed.

## [0.2.0]: 2026-05-13

### Changed
- **License: Apache-2.0 → AGPL-3.0-or-later.** Aligns with the
  eng-mcp-suite toolkit-wide AGPL move (the AGPL closes the
  "wrap as a paid SaaS without contributing back" gap). NEC2 itself
  is public-domain US-government code; this wrapper is the original
  code being relicensed.

## [0.1.0]: 2026-05-13

### Added
- Five parameterized antenna geometries: dipole, Yagi-Uda, ground-plane
  vertical, full-wave loop, inverted-V. Each compiling to NEC2 GW/EX/FR/RP
  cards and solved with the `nec2c` reference engine.
- Per-antenna tools: `nec2_create_dipole`, `nec2_create_yagi`,
  `nec2_create_vertical`, `nec2_create_loop`, `nec2_create_inverted_v`.
- Simulation driver `nec2_simulate` returning impedance, VSWR, gain,
  front-to-back ratio, and elevation/azimuth radiation patterns.
- Card-deck export via `nec2_get_nec_cards` for users who want to drive
  `nec2c` directly.
- Comprehensive test procedure document validating each antenna against
  expected impedance and resonance behavior.
- Brand assets aligned with eng-mcp-suite design system (logo, banner, docs).

### Fixed
- NEC2 impedance output parsing: correctly handles the multi-line
  impedance/admittance output format for both NEC2C and PyNEC backends.
- Antenna tool response completeness. Every tool now returns a
  consistent schema with impedance, VSWR, gain, and pattern data.
