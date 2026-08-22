# 5-element 2-meter Yagi-Uda design

Designing a five-element Yagi-Uda for the 2-meter amateur band centered
at 146 MHz. Optimization targets: forward gain ≥ 9 dBi, front-to-back
ratio ≥ 20 dB, feedpoint impedance compatible with 50-Ω coax via
gamma-match or hairpin.

## Scenario

You're building a directional 2-m antenna for FM repeater work. Five
elements is a reasonable balance between gain (more elements = more
gain) and boom length (which has to mount somewhere).

## Conversation script

```
You: Design a 5-element Yagi for 146 MHz. I want at least 9 dBi
     forward gain and 20 dB front-to-back. Start from the DL6WU
     long-Yagi template proportions.

Claude: [calls nec2_create_yagi with
         freq_mhz=146, num_elements=5,
         template="dl6wu", boom_diameter_mm=20]

        Created yagi "yagi_146mhz_5el_dl6wu":
          boom:        2.41 m
          reflector:   1.062 m at z = 0
          driven:      1.003 m at z = 0.41 m
          director 1:  0.969 m at z = 0.84 m
          director 2:  0.952 m at z = 1.41 m
          director 3:  0.942 m at z = 2.16 m

        [calls nec2_simulate at 146.0 MHz only]

        Performance at 146 MHz:
          Forward gain (dBi):       10.2
          Front-to-back ratio (dB): 23.5
          Feedpoint impedance (Ω):  29.4 + j8.1
          E-plane HPBW (deg):       54
          H-plane HPBW (deg):       58

You: Feedpoint is low (29 Ω). What's the easiest match to 50 Ω coax?

Claude: A gamma-match or hairpin is the standard fix for low-Z driven
        elements. For 29 + j8 Ω → 50 Ω, a hairpin of ~110 nH (a
        roughly 50 mm shorted stub of 6-mm copper) in parallel with
        the driven element gives you a clean 50-Ω match. Trim length
        on the bench using an antenna analyzer.
```

## Expected outputs

- Forward gain in the 9–11 dBi range for a well-tuned 5-element design
- Front-to-back ratio 20–25 dB
- Feedpoint impedance 20–35 Ω real (a known property of long Yagis:
  requires a matching network)
- Half-power beamwidths around 50–60° E-plane / 55–65° H-plane

## Tools exercised

- `nec2_create_yagi`: Yagi geometry generation with DL6WU / W3DZZ /
  G3SEK templates
- `nec2_simulate`: point-frequency analysis
- `nec2_get_nec_cards`: export for further tuning in another tool

## Notes

- **DL6WU long-Yagi proportions** are well-documented and start much
  closer to optimal than naïve "λ/2 elements, 0.2λ spacing" rules.
- **Gain plateaus quickly.** Going from 5 to 7 elements at this
  geometry adds ~1.5 dB. Going from 7 to 10 adds maybe 1 dB more.
  Boom-length cost grows faster than gain after ~7 elements.
- **NEC2 ground modeling.** Yagi gain numbers above assume free-space
  (no ground); for mast-mounted antennas at heights ≥ 3λ AGL, free-
  space is a good approximation. Below that, expect 2–6 dB extra
  forward gain due to ground reflection in some directions.
