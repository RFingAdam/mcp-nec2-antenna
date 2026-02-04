<p align="center">
  <img src="assets/logo.svg" alt="MCP NEC2 Antenna" width="400">
</p>

<p align="center">
  <strong>Wire antenna design and simulation via MCP</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> •
  <a href="#features">Features</a> •
  <a href="#usage-examples">Usage</a> •
  <a href="#antenna-types">Antenna Types</a>
</p>

---

An MCP server that enables AI assistants to design and simulate wire antennas using the NEC2 (Numerical Electromagnetics Code) method of moments solver. Perfect for ham radio operators, RF engineers, and antenna enthusiasts.

## Features

### Antenna Design Tools
- **nec2_create_dipole** - Create half-wave dipole antennas
- **nec2_create_yagi** - Create Yagi-Uda directional antennas
- **nec2_create_vertical** - Create ground-plane vertical antennas with radials
- **nec2_create_loop** - Create full-wave loop antennas
- **nec2_create_inverted_v** - Create inverted-V dipole antennas

### Simulation Tools
- **nec2_simulate** - Run full NEC2 simulation with frequency sweep
- **nec2_get_nec_cards** - Export raw NEC2 card deck for external tools

### Query Tools
- **nec2_list_antennas** - List all designs in current session
- **nec2_list_antenna_types** - Show available antenna types with characteristics

## Installation

### Prerequisites

Install the NEC2 solver:

```bash
# Ubuntu/Debian
sudo apt install nec2c

# macOS (via Homebrew)
brew install nec2c

# Arch Linux
yay -S nec2c
```

### 1. Clone and install

```bash
git clone https://github.com/RFingAdam/mcp-nec2-antenna.git
cd mcp-nec2-antenna
uv pip install -e .
```

### 2. Add to your MCP client

**Claude Code:**
```bash
claude mcp add nec2-antenna -- uv run --directory /path/to/mcp-nec2-antenna mcp-nec2-antenna
```

**Codex CLI:**
```bash
codex mcp add nec2-antenna -- uv run --directory /path/to/mcp-nec2-antenna mcp-nec2-antenna
```

**Config file format:**
```json
{
  "command": "uv",
  "args": ["run", "--directory", "/path/to/mcp-nec2-antenna", "mcp-nec2-antenna"]
}
```

## Usage Examples

### Design a 2-meter band dipole

```
Create a dipole antenna for 146 MHz at 10 meters height, then simulate it
```

The AI will:
1. Use `nec2_create_dipole` to design the antenna
2. Use `nec2_simulate` to analyze performance
3. Report impedance, VSWR, and radiation pattern

### Design a directional Yagi for satellite work

```
Design a 5-element Yagi antenna for 435 MHz (70cm band) for working amateur satellites
```

### Compare antenna designs

```
Create both a vertical and a dipole for 7 MHz (40m band) and compare their radiation patterns
```

### Export for external simulation

```
Create a 3-element Yagi for 144 MHz and give me the NEC2 card deck
```

## Antenna Types

| Type | Description | Gain | Pattern | Best For |
|------|-------------|------|---------|----------|
| **Dipole** | Half-wave horizontal wire | 2.15 dBi | Omnidirectional | General purpose, portable |
| **Yagi-Uda** | Directional beam with elements | 7-15 dBi | Directional | DX, satellites, weak signals |
| **Vertical** | Quarter-wave with ground radials | 0-2 dBi | Omnidirectional | Mobile, limited space |
| **Loop** | Full-wave quad loop | 3-4 dBi | Bidirectional | Low noise, DX |
| **Inverted-V** | Drooping dipole from single mast | 2 dBi | Omnidirectional | Single support available |

## Simulation Output

The `nec2_simulate` tool returns:

- **Impedance**: Resistance and reactance at each frequency
- **VSWR**: Standing wave ratio vs 50Ω
- **Best Match**: Frequency with lowest VSWR
- **Radiation Pattern**: Gain, beamwidth, front-to-back ratio

Example output:
```json
{
  "success": true,
  "antenna_id": "abc-123",
  "best_match": {
    "frequency_mhz": 146.0,
    "resistance": 72.3,
    "reactance": 2.1,
    "vswr": 1.45
  },
  "pattern": {
    "max_gain_dbi": 7.2,
    "front_to_back_db": 15.3
  }
}
```

## Technical Details

- Uses NEC2C (Numerical Electromagnetics Code version 2, C implementation)
- Method of Moments (MoM) electromagnetic simulation
- Supports free-space, perfect ground, and real ground models
- Automatic wire segmentation for accurate results

## License

Apache-2.0

## Author

Adam Engelbrecht - [@RFingAdam](https://github.com/RFingAdam)
