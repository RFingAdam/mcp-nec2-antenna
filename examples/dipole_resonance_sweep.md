# Dipole resonance sweep (70-cm band)

A short walkthrough: design a half-wave dipole for the 70-cm amateur
band (420–450 MHz), find its resonance, and check impedance bandwidth.

## Scenario

You need a half-wave dipole for the 70-cm band centered at 435 MHz.
You'd like to know:

- Where it actually resonates (vs the formula prediction)
- VSWR ≤ 2:1 bandwidth in MHz
- Feedpoint impedance at resonance

## Conversation script

```
You: Design a half-wave dipole for 435 MHz and tell me where it
     actually resonates.

Claude: [calls nec2_create_dipole with freq_mhz=435, height_m=10,
         wire_diameter_mm=2.0]

        Created dipole "dipole_435mhz_v1":
          length:    34.5 cm (each leg 17.25 cm)
          height:    10 m AGL
          wire ø:    2 mm

        [calls nec2_simulate with freq_sweep_start=420,
         freq_sweep_stop=450, freq_sweep_steps=31]

        Resonance found at 433.0 MHz (Z = 71.8 + j0.0 Ω, VSWR 1.44:1
        into 50 Ω). Slightly low. The dipole is ~0.5% long for
        target. Resonance shifts up if you trim each leg by ~1.6 mm.

You: What's the VSWR ≤ 2:1 bandwidth?

Claude: [reads back the previous sweep]

        VSWR ≤ 2:1 from 425.0 → 441.5 MHz (bandwidth 16.5 MHz, ~3.8%).
        That covers the full ITU-Region-1 70-cm band (430-440 MHz)
        with margin.
```

## Expected outputs

- Resonance frequency (within ~1% of formula prediction for a thin-wire
  dipole at λ/4 height)
- Feedpoint impedance ≈ 70–73 Ω at resonance for a free-space-like
  height (>2λ above ground)
- VSWR ≤ 2:1 bandwidth typically 3–5 % of center frequency for thin wire

## Tools exercised

- `nec2_create_dipole`: geometry generation
- `nec2_simulate`: frequency sweep driver
- (Optionally) `nec2_get_nec_cards`: to export the deck for inspection

## Notes

- **Ground effect matters.** A dipole at h < 0.5λ above ground sees
  impedance pulled down 10–30 Ω depending on ground quality. Use
  `height_m` ≥ 5 wavelengths if you want a "free space" reference.
- **NEC2 has wire-thickness limits.** The solver is accurate for
  `wire_diameter / wavelength < ~0.01`. For thicker antennas, NEC4 or
  a method-of-moments tool with extended kernel is more appropriate.
- **Cross-check against measurement** before fabricating. Method-of-
  moments is excellent for relative comparisons but ground/feedline/
  environment effects can shift resonance several percent in practice.
