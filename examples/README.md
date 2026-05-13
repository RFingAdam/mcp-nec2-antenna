# Examples

Runnable walkthroughs showing how to drive mcp-nec2-antenna from a
Claude / MCP client.

## Available examples

| Example | What it shows |
|---|---|
| [`dipole_resonance_sweep.md`](dipole_resonance_sweep.md) | Designing a 70-cm half-wave dipole and sweeping it across 420–450 MHz to find the resonance and impedance-bandwidth. |
| [`yagi_2m_design.md`](yagi_2m_design.md) | Five-element 2-meter (144 MHz) Yagi-Uda design — boom length, element spacing, expected forward gain and F/B ratio. |

## Running examples

Examples are written as Claude conversation scripts — user prompts on
the left, expected tool calls on the right. To reproduce:

1. Install: `pip install git+https://github.com/RFingAdam/mcp-nec2-antenna.git`
2. Make sure `nec2c` is on your `$PATH` (`brew install nec2c` on macOS,
   or build from source on Linux).
3. Wire the MCP server into Claude Desktop / Claude Code.
4. Open a new chat and follow the prompts.
