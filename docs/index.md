# mcp-nec2-antenna

**Design and simulate wire antennas with the NEC2 method-of-moments solver, driven over MCP.**
**Gain patterns, impedance, VSWR, radiation lobes: from your terminal or AI agent.**

---

## What it is

mcp-nec2-antenna wraps the canonical NEC2C reference solver behind an
MCP server with 9 tools. Five parameterized geometries (dipole, Yagi,
vertical, loop, inverted-V) compile to NEC2 card decks, solve with
`nec2c`, and return impedance / VSWR / gain / pattern in a single call.

## Install

```bash
# Install NEC2C first
sudo apt install nec2c          # Ubuntu/Debian
brew install nec2c              # macOS

# Then the MCP server
git clone https://github.com/RFingAdam/mcp-nec2-antenna.git
cd mcp-nec2-antenna
uv pip install -e .
```

## First call

=== "MCP"

    Add to `claude_desktop_config.json`:

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

    Then ask your assistant:

    > *"Design a 5-element Yagi for 435 MHz at 10 m height and simulate it."*

=== "CLI"

    ```bash
    uv run mcp-nec2-antenna   # starts the stdio MCP server
    ```

## Where to next

- [Tool reference](tools.md). Every MCP tool with arguments
- [Usage examples](usage.md): design a satellite Yagi end-to-end
- [Architecture](architecture.md): how this MCP fits inside eng-mcp-suite

---

!!! note "Part of eng-mcp-suite"
    This MCP server is part of [eng-mcp-suite](https://github.com/RFingAdam/eng-mcp-suite),
    an umbrella of engineering MCP servers across RF, EMC, PCB, signal
    integrity, EM simulation, and lab test.
