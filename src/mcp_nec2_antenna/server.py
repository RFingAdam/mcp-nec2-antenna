#!/usr/bin/env python3
"""MCP server for NEC2 wire antenna design and simulation.

This server provides tools for designing and simulating wire antennas using the
NEC2 (Numerical Electromagnetics Code) method of moments solver.

Supported antenna types:
- Half-wave dipole
- Yagi-Uda (directional)
- Ground-plane vertical
- Full-wave loop
- Inverted-V dipole

Usage:
    python -m mcp_nec2_antenna.server
"""

import asyncio
import json
import math
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsRequest, ListToolsResult, TextContent, Tool

# Speed of light in m/s
C = 299792458.0

# -----------------------------------------------------------------------------
# Yagi-Uda design constants
#
# Element lengths are expressed as ratios of the *resonant* element length for
# the wire gauge in use, not as fixed fractions of a half wavelength. A real
# element resonates short of lambda/2, and by an amount that depends on how fat
# the wire is in wavelengths, so a design pinned to lambda/2 drifts out of tune
# as the frequency rises for a fixed wire diameter. See
# RESONANT_DIPOLE_LENGTH_LAMBDA below.
#
# Ratios and spacings follow standard Yagi practice: reflector about 5% longer
# than the driven element, directors about 5% shorter and tapering gently along
# the boom, elements spaced about 0.2 lambda apart.
# -----------------------------------------------------------------------------
REFLECTOR_LENGTH_RATIO = 1.05
DIRECTOR_LENGTH_RATIO = 0.95
DIRECTOR_TAPER = 0.98
REFLECTOR_SPACING_LAMBDA = 0.2
DIRECTOR_SPACING_LAMBDA = 0.2

# Resonant length of a centre-fed cylindrical dipole, as (radius/lambda,
# length/lambda) pairs. Measured with nec2c by bisecting on the length that
# zeroes the feedpoint reactance, 41 segments, free space. Matches the standard
# published dipole-shortening tables to within a few parts in ten thousand.
RESONANT_DIPOLE_LENGTH_LAMBDA = (
    (1e-5, 0.4878),
    (3e-5, 0.4861),
    (1e-4, 0.4835),
    (3e-4, 0.4801),
    (1e-3, 0.4741),
    (3e-3, 0.4650),
    (1e-2, 0.4568),
)

# Free-space forward gain of the Yagi geometry built by create_yagi, as a
# function of boom length. Least squares fit of
#     gain_dBi = a + b * log10(boom / lambda)
# to 72 nec2c runs: 3 to 20 elements at 14.2, 50, 146 and 435 MHz. Residuals are
# zero mean with an RMS of 0.63 dB and a worst case of 1.39 dB. The slope is
# well under the 10 dB/decade of an ideal aperture because short-boom Yagis
# saturate; do not extrapolate this fit outside roughly 0.4 to 4 wavelengths of
# boom.
YAGI_GAIN_FIT_INTERCEPT_DBI = 10.98
YAGI_GAIN_FIT_SLOPE_DB = 5.70
YAGI_GAIN_FIT_RMS_DB = 0.63
YAGI_GAIN_FIT_MAX_ERROR_DB = 1.39


def resonant_dipole_length_lambda(radius_over_lambda: float) -> float:
    """Resonant length of a cylindrical dipole, in wavelengths.

    Log-interpolated over RESONANT_DIPOLE_LENGTH_LAMBDA and clamped to its
    range. Below the bottom of the table the curve is flat to three decimal
    places; above the top NEC2's thin-wire kernel is no longer trustworthy
    anyway, so clamping is the honest answer.
    """
    lo_a, lo_len = RESONANT_DIPOLE_LENGTH_LAMBDA[0]
    hi_a, hi_len = RESONANT_DIPOLE_LENGTH_LAMBDA[-1]
    if radius_over_lambda <= lo_a:
        return lo_len
    if radius_over_lambda >= hi_a:
        return hi_len

    log_a = math.log(radius_over_lambda)
    for (a0, l0), (a1, l1) in zip(RESONANT_DIPOLE_LENGTH_LAMBDA, RESONANT_DIPOLE_LENGTH_LAMBDA[1:], strict=False):
        if radius_over_lambda <= a1:
            t = (log_a - math.log(a0)) / (math.log(a1) - math.log(a0))
            return l0 + t * (l1 - l0)
    return hi_len


def yagi_boom_length_lambda(num_directors: int) -> float:
    """Boom length in wavelengths, reflector to last director."""
    return REFLECTOR_SPACING_LAMBDA + num_directors * DIRECTOR_SPACING_LAMBDA


def estimate_yagi_gain_dbi(num_directors: int) -> float:
    """Estimated free-space forward gain, in dBi, from boom length alone.

    This is a regression against nec2c runs of this module's own geometry, not
    a measurement, and not a claim about any other Yagi. It exists only as a
    fallback for when the nec2c solver is unavailable; when nec2c can be run,
    report the simulated figure instead. Accurate to about 0.6 dB RMS and 1.4 dB
    worst case over 3 to 20 elements and 14 to 435 MHz. See
    YAGI_GAIN_FIT_INTERCEPT_DBI for the fit and its provenance.
    """
    boom_lambda = yagi_boom_length_lambda(num_directors)
    return YAGI_GAIN_FIT_INTERCEPT_DBI + YAGI_GAIN_FIT_SLOPE_DB * math.log10(boom_lambda)


# =============================================================================
# Data Models
# =============================================================================


class AntennaType(str, Enum):
    """Types of wire antennas."""
    DIPOLE = "dipole"
    YAGI = "yagi"
    VERTICAL = "vertical"
    LOOP = "loop"
    INVERTED_V = "inverted_v"
    QUAD = "quad"


class GroundType(str, Enum):
    """Ground plane types."""
    FREE_SPACE = "free_space"
    PERFECT = "perfect"
    REAL = "real"


@dataclass
class Wire:
    """A wire segment in NEC2."""
    tag: int
    segments: int
    x1: float
    y1: float
    z1: float
    x2: float
    y2: float
    z2: float
    radius: float

    def to_nec2(self) -> str:
        """Convert to NEC2 GW card."""
        return f"GW {self.tag} {self.segments} {self.x1:.6f} {self.y1:.6f} {self.z1:.6f} {self.x2:.6f} {self.y2:.6f} {self.z2:.6f} {self.radius:.6f}"


@dataclass
class Excitation:
    """Excitation source."""
    tag: int
    segment: int
    voltage_real: float = 1.0
    voltage_imag: float = 0.0

    def to_nec2(self) -> str:
        """Convert to NEC2 EX card (voltage source)."""
        return f"EX 0 {self.tag} {self.segment} 0 {self.voltage_real:.6f} {self.voltage_imag:.6f}"


@dataclass
class Antenna:
    """Complete antenna definition."""
    id: str
    name: str
    antenna_type: AntennaType
    description: str = ""
    frequency_mhz: float = 146.0
    wires: list[Wire] = field(default_factory=list)
    excitations: list[Excitation] = field(default_factory=list)
    ground_type: GroundType = GroundType.FREE_SPACE
    ground_params: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def wavelength(self) -> float:
        """Calculate wavelength in meters."""
        return C / (self.frequency_mhz * 1e6)

    def to_nec2_input(self, freq_start: float = None, freq_end: float = None, freq_steps: int = 1) -> str:
        """Generate NEC2 input file."""
        lines = [
            f"CM {self.name}",
            f"CM {self.description}",
            f"CM Frequency: {self.frequency_mhz} MHz",
            "CM Generated by mcp-nec2-antenna",
            "CE",
        ]

        for wire in self.wires:
            lines.append(wire.to_nec2())

        lines.append("GE 0")

        if self.ground_type == GroundType.PERFECT:
            lines.append("GN 1")
        elif self.ground_type == GroundType.REAL:
            eps = self.ground_params.get("dielectric", 13.0)
            sigma = self.ground_params.get("conductivity", 0.005)
            lines.append(f"GN 2 0 0 0 {eps:.4f} {sigma:.6f}")

        for exc in self.excitations:
            lines.append(exc.to_nec2())

        if freq_start and freq_end and freq_steps > 1:
            freq_step = (freq_end - freq_start) / (freq_steps - 1)
            lines.append(f"FR 0 {freq_steps} 0 0 {freq_start:.4f} {freq_step:.6f}")
        else:
            lines.append(f"FR 0 1 0 0 {self.frequency_mhz:.4f} 0")

        lines.append("RP 0 91 120 1000 0 0 2 3")
        lines.append("EN")

        return "\n".join(lines)


@dataclass
class ImpedanceResult:
    """Impedance at a frequency."""
    frequency_mhz: float
    resistance: float
    reactance: float

    def vswr(self, z0: float = 50.0) -> float:
        """Calculate VSWR relative to reference impedance."""
        z = complex(self.resistance, self.reactance)
        gamma = abs((z - z0) / (z + z0))
        if gamma >= 1:
            return float('inf')
        return (1 + gamma) / (1 - gamma)


@dataclass
class PatternPoint:
    """A point in the radiation pattern."""
    theta: float
    phi: float
    gain_db: float


@dataclass
class RadiationPattern:
    """Complete radiation pattern."""
    frequency_mhz: float
    points: list[PatternPoint] = field(default_factory=list)
    max_gain_db: float = 0.0
    max_gain_theta: float = 0.0
    max_gain_phi: float = 0.0
    front_to_back_db: float = 0.0


@dataclass
class SimulationResult:
    """Complete simulation results."""
    success: bool
    antenna_id: str
    impedances: list[ImpedanceResult] = field(default_factory=list)
    patterns: list[RadiationPattern] = field(default_factory=list)
    error: Optional[str] = None


# =============================================================================
# Antenna Design Functions
# =============================================================================


def create_dipole(
    name: str,
    frequency_mhz: float,
    height_m: float = 10.0,
    wire_radius_mm: float = 1.0,
) -> Antenna:
    """Create a half-wave dipole antenna."""
    antenna = Antenna(
        id=str(uuid.uuid4()),
        name=name,
        antenna_type=AntennaType.DIPOLE,
        frequency_mhz=frequency_mhz,
        description=f"Half-wave dipole at {height_m}m height",
    )

    wavelength = antenna.wavelength()
    half_length = (wavelength / 2) * 0.95 / 2
    radius = wire_radius_mm / 1000

    antenna.wires.append(Wire(
        tag=1, segments=21,
        x1=-half_length, y1=0, z1=height_m,
        x2=half_length, y2=0, z2=height_m,
        radius=radius,
    ))
    antenna.excitations.append(Excitation(tag=1, segment=11))

    return antenna


def create_vertical(
    name: str,
    frequency_mhz: float,
    num_radials: int = 4,
    wire_radius_mm: float = 1.0,
) -> Antenna:
    """Create a ground-plane vertical antenna."""
    antenna = Antenna(
        id=str(uuid.uuid4()),
        name=name,
        antenna_type=AntennaType.VERTICAL,
        frequency_mhz=frequency_mhz,
        description=f"Vertical with {num_radials} radials",
    )

    wavelength = antenna.wavelength()
    height = wavelength * 0.25
    radial_length = wavelength * 0.25
    radius = wire_radius_mm / 1000

    antenna.wires.append(Wire(
        tag=1, segments=21,
        x1=0, y1=0, z1=0,
        x2=0, y2=0, z2=height,
        radius=radius,
    ))

    for i in range(num_radials):
        angle = 2 * math.pi * i / num_radials
        x = radial_length * math.cos(angle)
        y = radial_length * math.sin(angle)
        antenna.wires.append(Wire(
            tag=i + 2, segments=11,
            x1=0, y1=0, z1=0,
            x2=x, y2=y, z2=0,
            radius=radius,
        ))

    antenna.excitations.append(Excitation(tag=1, segment=1))
    return antenna


def create_yagi(
    name: str,
    frequency_mhz: float,
    num_directors: int = 3,
    boom_height_m: float = 10.0,
    wire_radius_mm: float = 2.0,
) -> Antenna:
    """Create a Yagi-Uda directional antenna.

    The boom runs along +x with the reflector at negative x, so the main lobe is
    at phi = 0. Element lengths are scaled from the resonant length for this
    wire gauge at this frequency rather than from a bare half wavelength: a
    fixed wire diameter is electrically fatter at UHF than at HF, which shortens
    the resonant length by several percent, and a design that ignores that ends
    up with directors long enough to act as reflectors and an array that fires
    out of the back.
    """
    antenna = Antenna(
        id=str(uuid.uuid4()),
        name=name,
        antenna_type=AntennaType.YAGI,
        frequency_mhz=frequency_mhz,
        description=f"{num_directors + 2}-element Yagi",
    )

    wavelength = antenna.wavelength()
    radius = wire_radius_mm / 1000

    driven_length = resonant_dipole_length_lambda(radius / wavelength) * wavelength
    reflector_length = driven_length * REFLECTOR_LENGTH_RATIO
    director_length = driven_length * DIRECTOR_LENGTH_RATIO

    reflector_spacing = wavelength * REFLECTOR_SPACING_LAMBDA
    director_spacing = wavelength * DIRECTOR_SPACING_LAMBDA

    tag = 1

    # Reflector
    antenna.wires.append(Wire(
        tag=tag, segments=21,
        x1=-reflector_spacing, y1=-reflector_length/2, z1=boom_height_m,
        x2=-reflector_spacing, y2=reflector_length/2, z2=boom_height_m,
        radius=radius,
    ))
    tag += 1

    # Driven element
    antenna.wires.append(Wire(
        tag=tag, segments=21,
        x1=0, y1=-driven_length/2, z1=boom_height_m,
        x2=0, y2=driven_length/2, z2=boom_height_m,
        radius=radius,
    ))
    antenna.excitations.append(Excitation(tag=tag, segment=11))
    tag += 1

    # Directors
    for i in range(num_directors):
        x_pos = (i + 1) * director_spacing
        dir_len = director_length * (DIRECTOR_TAPER ** i)
        antenna.wires.append(Wire(
            tag=tag, segments=21,
            x1=x_pos, y1=-dir_len/2, z1=boom_height_m,
            x2=x_pos, y2=dir_len/2, z2=boom_height_m,
            radius=radius,
        ))
        tag += 1

    return antenna


def create_loop(
    name: str,
    frequency_mhz: float,
    height_m: float = 10.0,
    wire_radius_mm: float = 1.0,
) -> Antenna:
    """Create a full-wave loop antenna."""
    antenna = Antenna(
        id=str(uuid.uuid4()),
        name=name,
        antenna_type=AntennaType.LOOP,
        frequency_mhz=frequency_mhz,
        description="Full-wave loop antenna",
    )

    wavelength = antenna.wavelength()
    circumference = wavelength
    num_sides = 4
    radius_wire = wire_radius_mm / 1000
    loop_radius = circumference / (2 * math.pi)

    for i in range(num_sides):
        angle1 = 2 * math.pi * i / num_sides
        angle2 = 2 * math.pi * (i + 1) / num_sides

        x1 = loop_radius * math.cos(angle1)
        y1 = loop_radius * math.sin(angle1)
        x2 = loop_radius * math.cos(angle2)
        y2 = loop_radius * math.sin(angle2)

        antenna.wires.append(Wire(
            tag=i + 1, segments=11,
            x1=x1, y1=y1, z1=height_m,
            x2=x2, y2=y2, z2=height_m,
            radius=radius_wire,
        ))

    antenna.excitations.append(Excitation(tag=1, segment=1))
    return antenna


def create_inverted_v(
    name: str,
    frequency_mhz: float,
    apex_height_m: float = 15.0,
    droop_angle_deg: float = 45.0,
    wire_radius_mm: float = 1.0,
) -> Antenna:
    """Create an inverted-V dipole antenna."""
    antenna = Antenna(
        id=str(uuid.uuid4()),
        name=name,
        antenna_type=AntennaType.INVERTED_V,
        frequency_mhz=frequency_mhz,
        description=f"Inverted-V with {droop_angle_deg} deg droop",
    )

    wavelength = antenna.wavelength()
    arm_length = wavelength / 4 * 0.95
    radius = wire_radius_mm / 1000
    droop_rad = math.radians(droop_angle_deg)

    horizontal_dist = arm_length * math.sin(droop_rad)
    vertical_drop = arm_length * math.cos(droop_rad)
    end_height = apex_height_m - vertical_drop

    antenna.wires.append(Wire(
        tag=1, segments=11,
        x1=0, y1=0, z1=apex_height_m,
        x2=-horizontal_dist, y2=0, z2=end_height,
        radius=radius,
    ))
    antenna.wires.append(Wire(
        tag=2, segments=11,
        x1=0, y1=0, z1=apex_height_m,
        x2=horizontal_dist, y2=0, z2=end_height,
        radius=radius,
    ))
    antenna.excitations.append(Excitation(tag=1, segment=1))

    return antenna


# =============================================================================
# NEC2 Simulation
# =============================================================================


async def run_nec2_simulation(
    antenna: Antenna,
    freq_start: float = None,
    freq_end: float = None,
    freq_steps: int = 21,
    nec2_path: str = "nec2c",
) -> SimulationResult:
    """Run NEC2 simulation on an antenna.

    Uses asyncio.create_subprocess_exec for safe subprocess execution
    without shell interpolation.
    """
    if freq_start is None:
        freq_start = antenna.frequency_mhz * 0.9
    if freq_end is None:
        freq_end = antenna.frequency_mhz * 1.1

    nec2_input = antenna.to_nec2_input(freq_start, freq_end, freq_steps)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, "antenna.nec")
            output_file = os.path.join(tmpdir, "antenna.out")

            with open(input_file, "w") as f:
                f.write(nec2_input)

            # Safe subprocess execution without shell
            process = await asyncio.create_subprocess_exec(
                nec2_path,
                "-i", input_file,
                "-o", output_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tmpdir,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=300.0,
            )

            raw_output = ""
            if os.path.exists(output_file):
                with open(output_file) as f:
                    raw_output = f.read()

            impedances = parse_impedance(raw_output)
            patterns = parse_pattern(raw_output)

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="ignore")
                return SimulationResult(
                    success=False,
                    antenna_id=antenna.id,
                    error=error_msg or "NEC2 simulation failed",
                )

            return SimulationResult(
                success=True,
                antenna_id=antenna.id,
                impedances=impedances,
                patterns=patterns,
            )

    except asyncio.TimeoutError:
        return SimulationResult(
            success=False,
            antenna_id=antenna.id,
            error="Simulation timed out",
        )
    except FileNotFoundError:
        return SimulationResult(
            success=False,
            antenna_id=antenna.id,
            error="nec2c not found. Install with: sudo apt install nec2c",
        )
    except Exception as e:
        return SimulationResult(
            success=False,
            antenna_id=antenna.id,
            error=str(e),
        )


def parse_impedance(output: str) -> list[ImpedanceResult]:
    """Parse impedance results from NEC2 output.

    NEC2 output format:
    - Frequency: "FREQUENCY : 1.4600E+02 MHz"
    - Impedance in table: columns are TAG, SEG, VOLT_R, VOLT_I, CURR_R, CURR_I, IMP_R, IMP_I, ...
    """
    impedances = []

    # Split by frequency sections
    freq_sections = re.split(r'-+\s*FREQUENCY\s*-+', output)

    for section in freq_sections[1:] if len(freq_sections) > 1 else []:
        # Parse frequency (scientific notation): "FREQUENCY : 1.4600E+02 MHz"
        freq_match = re.search(r'FREQUENCY\s*:\s*([+-]?\d+\.?\d*(?:E[+-]?\d+)?)\s*MHz', section, re.IGNORECASE)
        freq = float(freq_match.group(1)) if freq_match else 0.0

        # Find ANTENNA INPUT PARAMETERS section and parse impedance from table
        if "ANTENNA INPUT PARAMETERS" in section:
            # Match data rows: numbers in scientific notation
            # Format: TAG SEG VOLT_R VOLT_I CURR_R CURR_I IMP_R IMP_I ADM_R ADM_I POWER
            data_pattern = re.compile(
                r'^\s*(\d+)\s+(\d+)\s+'  # TAG, SEG
                r'([+-]?\d+\.?\d*E[+-]?\d+)\s+([+-]?\d+\.?\d*E[+-]?\d+)\s+'  # VOLT
                r'([+-]?\d+\.?\d*E[+-]?\d+)\s+([+-]?\d+\.?\d*E[+-]?\d+)\s+'  # CURR
                r'([+-]?\d+\.?\d*E[+-]?\d+)\s+([+-]?\d+\.?\d*E[+-]?\d+)',    # IMP
                re.MULTILINE
            )

            for match in data_pattern.finditer(section):
                resistance = float(match.group(7))
                reactance = float(match.group(8))

                impedances.append(ImpedanceResult(
                    frequency_mhz=freq,
                    resistance=resistance,
                    reactance=reactance,
                ))

    return impedances


def parse_pattern(output: str) -> list[RadiationPattern]:
    """Parse radiation patterns from NEC2 output, one per frequency.

    NEC2 emits a FREQUENCY banner followed by an ANTENNA INPUT PARAMETERS block
    and a RADIATION PATTERNS block for every step of a sweep. Split on the
    banner the same way parse_impedance does, so each pattern carries the
    frequency it was actually computed at rather than being lumped together.
    """
    patterns = []

    freq_sections = re.split(r'-+\s*FREQUENCY\s*-+', output)

    for section in freq_sections[1:] if len(freq_sections) > 1 else []:
        freq_match = re.search(r'FREQUENCY\s*:\s*([+-]?\d+\.?\d*(?:E[+-]?\d+)?)\s*MHz', section, re.IGNORECASE)
        freq = float(freq_match.group(1)) if freq_match else 0.0

        pattern_section = re.search(r"RADIATION PATTERNS(.*)", section, re.DOTALL | re.IGNORECASE)
        if not pattern_section:
            continue

        current_pattern = RadiationPattern(frequency_mhz=freq)

        for line in pattern_section.group(1).split("\n"):
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) >= 5:
                try:
                    theta = float(parts[0])
                    phi = float(parts[1])
                    total_db = float(parts[4])
                except ValueError:
                    continue

                point = PatternPoint(theta=theta, phi=phi, gain_db=total_db)
                current_pattern.points.append(point)

                # Seed from the first point rather than from 0 dB, so a pattern
                # whose peak is below isotropic is not reported as 0 dBi.
                if len(current_pattern.points) == 1 or total_db > current_pattern.max_gain_db:
                    current_pattern.max_gain_db = total_db
                    current_pattern.max_gain_theta = theta
                    current_pattern.max_gain_phi = phi

        if not current_pattern.points:
            continue

        back_phi = (current_pattern.max_gain_phi + 180) % 360
        back_gains = [
            p.gain_db for p in current_pattern.points
            if abs(p.theta - current_pattern.max_gain_theta) < 5 and
               abs(p.phi - back_phi) < 10
        ]
        if back_gains:
            current_pattern.front_to_back_db = current_pattern.max_gain_db - max(back_gains)

        patterns.append(current_pattern)

    return patterns


def pattern_nearest(patterns: list[RadiationPattern], frequency_mhz: float) -> Optional[RadiationPattern]:
    """The parsed pattern closest to a frequency, or None if there are none."""
    if not patterns:
        return None
    return min(patterns, key=lambda p: abs(p.frequency_mhz - frequency_mhz))


async def yagi_gain_report(antenna: Antenna, num_directors: int) -> dict[str, Any]:
    """Gain figures for a Yagi, always labelled with where the number came from.

    Runs nec2c once at the design frequency and reports what the solver
    computed. A single-frequency run over this geometry takes well under a
    second even for a 20-element array, so this is cheap enough to do at design
    time. When the solver is missing or fails, falls back to the boom-length
    regression in estimate_yagi_gain_dbi and says so.

    Callers must read ``gain_basis`` before using ``gain_dbi``: "simulated"
    means NEC2 computed it, "estimated" means it came from a curve fit.
    """
    sim = await run_nec2_simulation(antenna, freq_steps=1)
    pattern = pattern_nearest(sim.patterns, antenna.frequency_mhz) if sim.success else None

    if pattern is None:
        reason = sim.error or "nec2c produced no radiation pattern"
        return {
            "gain_dbi": round(estimate_yagi_gain_dbi(num_directors), 2),
            "gain_basis": "estimated",
            "gain_method": (
                f"boom-length regression {YAGI_GAIN_FIT_INTERCEPT_DBI} + "
                f"{YAGI_GAIN_FIT_SLOPE_DB}*log10(boom/lambda), fitted to nec2c runs of this "
                f"geometry over 3-20 elements and 14-435 MHz; {YAGI_GAIN_FIT_RMS_DB} dB RMS, "
                f"{YAGI_GAIN_FIT_MAX_ERROR_DB} dB worst case. Not a simulation: {reason}"
            ),
        }

    return {
        "gain_dbi": round(pattern.max_gain_db, 2),
        "gain_basis": "simulated",
        "gain_method": f"NEC2 (nec2c) free-space simulation at {antenna.frequency_mhz} MHz",
        "front_to_back_db": round(pattern.front_to_back_db, 1),
        "main_lobe_theta_deg": round(pattern.max_gain_theta, 1),
        "main_lobe_phi_deg": round(pattern.max_gain_phi, 1),
    }


# =============================================================================
# MCP Server
# =============================================================================

server = Server("mcp-nec2-antenna")

# Store antennas in memory
_antennas: dict[str, Antenna] = {}


async def handle_list_tools(ctx, params: ListToolsRequest) -> ListToolsResult:
    """List available NEC2 antenna tools."""
    return ListToolsResult(tools=[
        Tool(
            name="nec2_create_dipole",
            description="Create a half-wave dipole antenna. Returns antenna ID for simulation.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Antenna name"},
                    "frequency_mhz": {"type": "number", "description": "Design frequency in MHz (e.g., 146 for 2m band)"},
                    "height_m": {"type": "number", "description": "Height above ground in meters (default: 10)"},
                    "wire_radius_mm": {"type": "number", "description": "Wire radius in mm (default: 1)"},
                },
                "required": ["name", "frequency_mhz"],
            },
        ),
        Tool(
            name="nec2_create_yagi",
            description="Create a Yagi-Uda directional antenna with specified number of directors. Gain is simulated with nec2c when the solver is installed, and falls back to a labelled boom-length estimate when it is not.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Antenna name"},
                    "frequency_mhz": {"type": "number", "description": "Design frequency in MHz"},
                    "num_directors": {"type": "integer", "description": "Number of director elements (default: 3)"},
                    "height_m": {"type": "number", "description": "Boom height above ground in meters (default: 10)"},
                    "wire_radius_mm": {"type": "number", "description": "Element wire radius in mm (default: 2). Affects element lengths."},
                },
                "required": ["name", "frequency_mhz"],
            },
        ),
        Tool(
            name="nec2_create_vertical",
            description="Create a quarter-wave vertical antenna with ground radials.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Antenna name"},
                    "frequency_mhz": {"type": "number", "description": "Design frequency in MHz"},
                    "num_radials": {"type": "integer", "description": "Number of ground radials (default: 4)"},
                },
                "required": ["name", "frequency_mhz"],
            },
        ),
        Tool(
            name="nec2_create_loop",
            description="Create a full-wave loop antenna (quad configuration).",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Antenna name"},
                    "frequency_mhz": {"type": "number", "description": "Design frequency in MHz"},
                    "height_m": {"type": "number", "description": "Height above ground in meters (default: 10)"},
                },
                "required": ["name", "frequency_mhz"],
            },
        ),
        Tool(
            name="nec2_create_inverted_v",
            description="Create an inverted-V dipole antenna (requires only one support).",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Antenna name"},
                    "frequency_mhz": {"type": "number", "description": "Design frequency in MHz"},
                    "apex_height_m": {"type": "number", "description": "Apex height in meters (default: 15)"},
                    "droop_angle_deg": {"type": "number", "description": "Droop angle in degrees (default: 45)"},
                },
                "required": ["name", "frequency_mhz"],
            },
        ),
        Tool(
            name="nec2_simulate",
            description="Run NEC2 simulation on an antenna to get impedance and radiation pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "antenna_id": {"type": "string", "description": "Antenna ID from create_* tools"},
                    "frequency_start_mhz": {"type": "number", "description": "Start frequency for sweep (default: design freq * 0.9)"},
                    "frequency_end_mhz": {"type": "number", "description": "End frequency for sweep (default: design freq * 1.1)"},
                    "frequency_steps": {"type": "integer", "description": "Number of frequency points (default: 21)"},
                },
                "required": ["antenna_id"],
            },
        ),
        Tool(
            name="nec2_get_nec_cards",
            description="Get the raw NEC2 card deck for an antenna design (for manual editing or external tools).",
            input_schema={
                "type": "object",
                "properties": {
                    "antenna_id": {"type": "string", "description": "Antenna ID"},
                },
                "required": ["antenna_id"],
            },
        ),
        Tool(
            name="nec2_list_antennas",
            description="List all antenna designs in the current session.",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="nec2_list_antenna_types",
            description="List available antenna types and their characteristics.",
            input_schema={"type": "object", "properties": {}},
        ),
    ])


async def handle_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
    """Handle tool calls for NEC2 antenna operations."""
    name = params.name
    arguments = params.arguments
    try:
        if name == "nec2_create_dipole":
            antenna = create_dipole(
                name=arguments["name"],
                frequency_mhz=arguments["frequency_mhz"],
                height_m=arguments.get("height_m", 10.0),
                wire_radius_mm=arguments.get("wire_radius_mm", 1.0),
            )
            _antennas[antenna.id] = antenna
            wavelength = antenna.wavelength()
            result = {
                "success": True,
                "antenna_id": antenna.id,
                "name": antenna.name,
                "type": "dipole",
                "frequency_mhz": antenna.frequency_mhz,
                "calculated_length_m": round(wavelength / 2 * 0.95, 3),
                "height_m": arguments.get("height_m", 10.0),
            }

        elif name == "nec2_create_yagi":
            num_directors = arguments.get("num_directors", 3)
            antenna = create_yagi(
                name=arguments["name"],
                frequency_mhz=arguments["frequency_mhz"],
                num_directors=num_directors,
                boom_height_m=arguments.get("height_m", 10.0),
                wire_radius_mm=arguments.get("wire_radius_mm", 2.0),
            )
            _antennas[antenna.id] = antenna
            boom_lambda = yagi_boom_length_lambda(num_directors)
            result = {
                "success": True,
                "antenna_id": antenna.id,
                "name": antenna.name,
                "type": "yagi",
                "frequency_mhz": antenna.frequency_mhz,
                "elements": 2 + num_directors,
                "boom_length_m": round(boom_lambda * antenna.wavelength(), 3),
                "boom_length_wavelengths": round(boom_lambda, 3),
            }
            result.update(await yagi_gain_report(antenna, num_directors))

        elif name == "nec2_create_vertical":
            num_radials = arguments.get("num_radials", 4)
            antenna = create_vertical(
                name=arguments["name"],
                frequency_mhz=arguments["frequency_mhz"],
                num_radials=num_radials,
            )
            _antennas[antenna.id] = antenna
            wavelength = antenna.wavelength()
            result = {
                "success": True,
                "antenna_id": antenna.id,
                "name": antenna.name,
                "type": "vertical",
                "frequency_mhz": antenna.frequency_mhz,
                "calculated_height_m": round(wavelength * 0.25, 3),
                "radials": num_radials,
            }

        elif name == "nec2_create_loop":
            height_m = arguments.get("height_m", 10.0)
            antenna = create_loop(
                name=arguments["name"],
                frequency_mhz=arguments["frequency_mhz"],
                height_m=height_m,
            )
            _antennas[antenna.id] = antenna
            wavelength = antenna.wavelength()
            result = {
                "success": True,
                "antenna_id": antenna.id,
                "name": antenna.name,
                "type": "loop",
                "frequency_mhz": antenna.frequency_mhz,
                "circumference_m": round(wavelength, 3),
                "height_m": height_m,
            }

        elif name == "nec2_create_inverted_v":
            apex_height_m = arguments.get("apex_height_m", 15.0)
            droop_angle_deg = arguments.get("droop_angle_deg", 45.0)
            antenna = create_inverted_v(
                name=arguments["name"],
                frequency_mhz=arguments["frequency_mhz"],
                apex_height_m=apex_height_m,
                droop_angle_deg=droop_angle_deg,
            )
            _antennas[antenna.id] = antenna
            wavelength = antenna.wavelength()
            arm_length = wavelength / 4 * 0.95
            droop_rad = math.radians(droop_angle_deg)
            end_height = apex_height_m - arm_length * math.cos(droop_rad)
            result = {
                "success": True,
                "antenna_id": antenna.id,
                "name": antenna.name,
                "type": "inverted_v",
                "frequency_mhz": antenna.frequency_mhz,
                "apex_height_m": apex_height_m,
                "droop_angle_deg": droop_angle_deg,
                "total_wire_length_m": round(arm_length * 2, 3),
                "end_height_m": round(end_height, 3),
            }

        elif name == "nec2_simulate":
            antenna_id = arguments["antenna_id"]
            if antenna_id not in _antennas:
                result = {"success": False, "error": f"Antenna not found: {antenna_id}"}
            else:
                antenna = _antennas[antenna_id]
                sim_result = await run_nec2_simulation(
                    antenna=antenna,
                    freq_start=arguments.get("frequency_start_mhz"),
                    freq_end=arguments.get("frequency_end_mhz"),
                    freq_steps=arguments.get("frequency_steps", 21),
                )

                if sim_result.success:
                    best = None
                    for imp in sim_result.impedances:
                        vswr = imp.vswr()
                        if best is None or vswr < best["vswr"]:
                            best = {
                                "frequency_mhz": imp.frequency_mhz,
                                "resistance": round(imp.resistance, 1),
                                "reactance": round(imp.reactance, 1),
                                "vswr": round(vswr, 2),
                            }

                    result = {
                        "success": True,
                        "antenna_id": antenna_id,
                        "best_match": best,
                        "frequency_points": len(sim_result.impedances),
                    }

                    pattern = pattern_nearest(sim_result.patterns, antenna.frequency_mhz)
                    if pattern is not None:
                        result["pattern"] = {
                            "frequency_mhz": round(pattern.frequency_mhz, 4),
                            "max_gain_dbi": round(pattern.max_gain_db, 2),
                            "max_gain_theta_deg": round(pattern.max_gain_theta, 1),
                            "max_gain_phi_deg": round(pattern.max_gain_phi, 1),
                            "front_to_back_db": round(pattern.front_to_back_db, 1),
                            "gain_basis": "simulated",
                        }
                else:
                    result = {"success": False, "error": sim_result.error}

        elif name == "nec2_get_nec_cards":
            antenna_id = arguments["antenna_id"]
            if antenna_id not in _antennas:
                result = {"success": False, "error": f"Antenna not found: {antenna_id}"}
            else:
                antenna = _antennas[antenna_id]
                nec_cards = antenna.to_nec2_input()
                result = {
                    "success": True,
                    "antenna_id": antenna_id,
                    "nec_cards": nec_cards,
                }

        elif name == "nec2_list_antennas":
            result = {
                "success": True,
                "antennas": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "type": a.antenna_type.value,
                        "frequency_mhz": a.frequency_mhz,
                    }
                    for a in _antennas.values()
                ],
            }

        elif name == "nec2_list_antenna_types":
            result = {
                "success": True,
                "antenna_types": [
                    {"type": "dipole", "name": "Half-Wave Dipole", "gain": "2.15 dBi", "pattern": "omnidirectional"},
                    {"type": "yagi", "name": "Yagi-Uda", "gain": "7-15 dBi", "pattern": "directional"},
                    {"type": "vertical", "name": "Ground-Plane Vertical", "gain": "0-2 dBi", "pattern": "omnidirectional"},
                    {"type": "loop", "name": "Full-Wave Loop", "gain": "3-4 dBi", "pattern": "bidirectional"},
                    {"type": "inverted_v", "name": "Inverted-V Dipole", "gain": "2 dBi", "pattern": "omnidirectional"},
                ],
            }

        else:
            result = {"success": False, "error": f"Unknown tool: {name}"}

        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])

    except Exception as e:
        error_result = {"success": False, "error": str(e)}
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(error_result))])


def register_handlers(server: Server) -> None:
    """Register MCP request handlers."""
    server.add_request_handler("tools/list", ListToolsRequest, handle_list_tools)
    server.add_request_handler("tools/call", CallToolRequestParams, handle_call_tool)


register_handlers(server)


def main():
    """Run the MCP server."""
    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
