# Architecture

## Internal layout

```
┌──────────────────────────────────────────────────────────────────┐
│  User-facing surface                                             │
│  ┌────────────────────────────┐                                  │
│  │  MCP server (stdio)        │                                  │
│  │  mcp.server.Server         │                                  │
│  └────────────────────────────┘                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Orchestration                                                   │
│  • Antenna model + Wire / Excitation dataclasses                 │
│  • NEC2 card-deck builder (GW / EX / FR / GN / RP / EN)          │
│  • Session manager (in-memory id → Antenna map)                  │
│  • Output parser (impedance, VSWR, gain, pattern)                │
└──────────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────────┐
│  Kernel                                                          │
│  • nec2c — external C binary (LLNL Fortran NEC2, Kyriazis port)  │
└──────────────────────────────────────────────────────────────────┘
```

The server is pure-Python orchestration. Each tool call: build a card
deck, write it to a temp file, invoke `nec2c`, parse the output
listing, return a structured response. No persistent state between
restarts — the session is in-memory only.

## Source layout

```
mcp-nec2-antenna/
├── src/mcp_nec2_antenna/
│   ├── __init__.py
│   └── server.py        ← MCP server + all tool handlers + card builders
├── examples/
├── assets/              ← logo-banner.svg, logo.svg
└── docs/
```

## Position in eng-mcp-suite

mcp-nec2-antenna sits in the **electromagnetic solver** layer — wire
antennas / MoM only. For 3D structure / planar antennas reach for
[`mcp-openems`](https://github.com/RFingAdam/mcp-openems) (FDTD).

```
        ┌─────────────────────────────────────┐
        │   AI agent (Claude Code / Desktop)  │
        └──────┬──────────────┬───────────────┘
               │              │ via MCP
       ┌───────▼──────────┐ ┌─▼─────────────────────────┐
       │ mcp-nec2-antenna │ │ lineforge / mcp-openems   │
       │  (MoM, wires)    │ │ (trans-line / FDTD 3D)    │
       └───────┬──────────┘ └───────────────────────────┘
               │
       ┌───────▼──────────────────────┐
       │  mcp-emc-regulations         │  (post-design limit check)
       └──────────────────────────────┘
```

### Feeds (this MCP produces output that)…

- **mcp-emc-regulations** — radiated-emission predictions for limit
  margin checks against CISPR / FCC.
- **drawio-engineering-mcp** — antenna geometry + pattern for design
  documentation.

### Consumes (this MCP accepts input from)…

- **mcp-ltspice-qucs** — matching-network port impedance to feed
  into the antenna feedpoint model.

### Workflow bundles that include this MCP

| Bundle           | Role of this MCP                                  |
| ---------------- | ------------------------------------------------- |
| `rf-design`      | Wire-antenna design step                          |
| `antenna-bench`  | Pre-measurement simulation baseline               |

See the [suite manifest](https://github.com/RFingAdam/eng-mcp-suite/blob/main/manifest.yaml)
for full bundle definitions.

---

## Design decisions

- **External `nec2c` binary, not a bundled library.** The reference
  solver is GPL/PD Fortran-or-C, well-tested over decades. Wrapping
  it as a subprocess keeps this MCP's license clean (Apache-2.0) and
  lets users swap in newer NEC ports if they want.
- **Parameterized geometries over freeform GW cards.** Five built-in
  antennas cover ~90% of practical wire-antenna design. Power users
  can still emit raw cards via `nec2_get_nec_cards` for advanced
  geometry edits in 4nec2 / xnec2c.
- **In-memory sessions only.** No DB, no on-disk cache — a designed
  antenna lives until the MCP server exits. Re-runs are cheap (NEC2
  solves a small antenna in milliseconds).
