# Usage

This page walks one realistic scenario from problem to result.

---

## Scenario: 70 cm satellite Yagi

You want a small directional antenna for working amateur satellites on
the 70 cm band (435 MHz). It needs ≥10 dBi forward gain, a clean
front-to-back, and you want to verify before you cut aluminium.

## Setup

```bash
sudo apt install nec2c
git clone https://github.com/RFingAdam/mcp-nec2-antenna.git
cd mcp-nec2-antenna
uv pip install -e .
```

Register with Claude Desktop / Code:

```json
{
  "mcpServers": {
    "nec2-antenna": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-nec2-antenna", "mcp-nec2-antenna"]
    }
  }
}
```

Restart your MCP client.

## Step 1: Synthesize the geometry

Ask the assistant:

> *"Create a 5-element Yagi for 435 MHz at 3 m boom height."*

The agent calls `nec2_create_yagi`:

```json
{
  "name": "satyagi-435",
  "frequency_mhz": 435.0,
  "num_elements": 5,
  "boom_height_m": 3.0
}
```

It returns an `antenna_id` and the wire layout.

## Step 2: Sweep impedance + VSWR around the band

> *"Sweep it from 430 to 440 MHz and tell me the best match."*

The agent calls `nec2_simulate`:

```json
{
  "antenna_id": "satyagi-435",
  "frequency_start_mhz": 430.0,
  "frequency_stop_mhz": 440.0,
  "steps": 21,
  "ground_type": "real"
}
```

A trimmed response:

```json
{
  "success": true,
  "best_match": {
    "frequency_mhz": 435.0,
    "resistance": 27.6,
    "reactance": -1.4,
    "vswr": 1.81
  },
  "pattern": {
    "max_gain_dbi": 10.4,
    "front_to_back_db": 18.7,
    "elevation_deg": 12
  }
}
```

The agent reports: VSWR of 1.81:1 at design frequency, 10.4 dBi forward
gain, and 18.7 dB front-to-back: well past the spec.

## Step 3: Export the card deck for 4nec2

> *"Give me the raw NEC2 card deck so I can double-check it in 4nec2."*

The agent calls `nec2_get_nec_cards` and returns the GW/EX/FR/GN/RP
deck. You paste it into 4nec2 and the patterns agree to within
0.1 dB: same solver under the hood.

---

## What just happened

In three tool calls, the agent went from "I need a satellite Yagi" to
"here is the verified geometry, here is the VSWR curve, here is the
deck you can hand off to a CAD-style frontend." No NEC card hand-
writing, no `.nec` file editing, no segment-count guessing.

- For more tools: [Tool reference](tools.md)
- For how this fits in the suite: [Architecture](architecture.md)
- For sibling MCPs that compose with this one: [eng-mcp-suite catalog](https://github.com/RFingAdam/eng-mcp-suite#whats-included)
