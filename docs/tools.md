# Tools

This page documents every MCP tool the server exposes. Tools are
registered under the `nec2-antenna` namespace when the server is loaded
by an MCP client.

## Tool index

| Tool                                                    | Purpose                                       |
| ------------------------------------------------------- | --------------------------------------------- |
| [`nec2_create_dipole`](#nec2_create_dipole)             | Half-wave horizontal dipole                   |
| [`nec2_create_yagi`](#nec2_create_yagi)                 | Yagi-Uda directional beam                     |
| [`nec2_create_vertical`](#nec2_create_vertical)         | Quarter-wave vertical w/ radials              |
| [`nec2_create_loop`](#nec2_create_loop)                 | Full-wave quad loop                           |
| [`nec2_create_inverted_v`](#nec2_create_inverted_v)     | Inverted-V dipole                             |
| [`nec2_simulate`](#nec2_simulate)                       | Run NEC2 sweep                                |
| [`nec2_get_nec_cards`](#nec2_get_nec_cards)             | Export raw NEC2 card deck                     |
| [`nec2_list_antennas`](#nec2_list_antennas)             | List antennas in session                      |
| [`nec2_list_antenna_types`](#nec2_list_antenna_types)   | List built-in antenna types                   |

---

## nec2_create_dipole

Create a half-wave horizontal dipole and add it to the session.

**Arguments**

| Name             | Type    | Default | Description                                  |
| ---------------- | ------- | ------- | -------------------------------------------- |
| `name`           | string  | _req_   | Human-readable antenna name                  |
| `frequency_mhz`  | number  | _req_   | Design frequency (MHz)                       |
| `height_m`       | number  | 10.0    | Height above ground (m)                      |
| `wire_radius_mm` | number  | 1.0     | Wire radius (mm)                             |
| `description`    | string  | `""`    | Optional design notes                        |

**Returns**: `antenna_id`, computed wire length, segment count.

---

## nec2_create_yagi

Create a Yagi-Uda directional beam (1 reflector + driven + N-2 directors).

**Arguments**

| Name              | Type   | Default | Description                                  |
| ----------------- | ------ | ------- | -------------------------------------------- |
| `name`            | string | _req_   | Human-readable antenna name                  |
| `frequency_mhz`   | number | _req_   | Design frequency (MHz)                       |
| `num_elements`    | int    | 3       | Total elements (>= 2)                        |
| `boom_height_m`   | number | 10.0    | Boom height above ground (m)                 |

---

## nec2_create_vertical

Create a quarter-wave vertical monopole with N ground radials.

**Arguments**

| Name              | Type   | Default | Description                                  |
| ----------------- | ------ | ------- | -------------------------------------------- |
| `name`            | string | _req_   | Human-readable antenna name                  |
| `frequency_mhz`   | number | _req_   | Design frequency (MHz)                       |
| `num_radials`     | int    | 16      | Number of ground-plane radials               |
| `radial_length_m` | number | `λ/4`   | Per-radial length                            |

---

## nec2_create_loop

Create a full-wave quad loop.

**Arguments**

| Name             | Type   | Default | Description                                  |
| ---------------- | ------ | ------- | -------------------------------------------- |
| `name`           | string | _req_   | Human-readable antenna name                  |
| `frequency_mhz`  | number | _req_   | Design frequency (MHz)                       |
| `height_m`       | number | 10.0    | Centre-of-loop height (m)                    |

---

## nec2_create_inverted_v

Create an inverted-V dipole from a single mast.

**Arguments**

| Name              | Type   | Default | Description                                  |
| ----------------- | ------ | ------- | -------------------------------------------- |
| `name`            | string | _req_   | Human-readable antenna name                  |
| `frequency_mhz`   | number | _req_   | Design frequency (MHz)                       |
| `apex_height_m`   | number | 12.0    | Apex height (mast top)                       |
| `droop_deg`       | number | 45      | Element droop angle from horizontal          |

---

## nec2_simulate

Run a NEC2 sweep over `[frequency_start_mhz, frequency_stop_mhz]` and
return impedance, VSWR, gain, and pattern.

**Arguments**

| Name                  | Type     | Default | Description                          |
| --------------------- | -------- | ------- | ------------------------------------ |
| `antenna_id`          | string   | _req_   | ID returned by a `_create_` tool     |
| `frequency_start_mhz` | number   | _req_   | Sweep start                          |
| `frequency_stop_mhz`  | number   | _req_   | Sweep stop                           |
| `steps`               | int      | 11      | Number of sweep points               |
| `ground_type`         | enum     | `real`  | `free_space` / `perfect` / `real`    |

**Returns**: per-frequency `resistance`, `reactance`, `vswr`, plus a
`best_match` summary, peak gain (dBi), and front-to-back ratio.

---

## nec2_get_nec_cards

Export the raw NEC2 card deck (`GW`, `EX`, `FR`, `GN`, `RP`, `EN`) so
you can run it in 4nec2, xnec2c, or any other NEC frontend.

**Arguments**: `antenna_id`.

**Returns**: multiline string of cards.

---

## nec2_list_antennas

List every antenna in the current session.

---

## nec2_list_antenna_types

List built-in antenna types with their characteristic gain and pattern
shape. No arguments.
