# Changelog

All notable changes to **mcp-nec2-antenna** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-13

### Changed
- **License: Apache-2.0 → AGPL-3.0-or-later.** Aligns with the
  eng-mcp-suite toolkit-wide AGPL move (the AGPL closes the
  "wrap as a paid SaaS without contributing back" gap). NEC2 itself
  is public-domain US-government code; this wrapper is the original
  code being relicensed.

## [0.1.0] — 2026-05-13

### Added
- Five parameterized antenna geometries: dipole, Yagi-Uda, ground-plane
  vertical, full-wave loop, inverted-V — each compiling to NEC2 GW/EX/FR/RP
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
- NEC2 impedance output parsing — correctly handles the multi-line
  impedance/admittance output format for both NEC2C and PyNEC backends.
- Antenna tool response completeness — every tool now returns a
  consistent schema with impedance, VSWR, gain, and pattern data.
