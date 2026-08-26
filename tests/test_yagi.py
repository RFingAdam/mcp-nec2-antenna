"""Regression tests for the Yagi design rules and its reported gain.

Two defects motivated these:

1. ``nec2_create_yagi`` reported ``expected_gain_dbi = 7 + 2*num_directors``.
   That number was invented, unbounded (47 dBi at 20 directors) and, for a
   7-element array at 434 MHz, overstated the deck's own simulated gain of
   6.1 dBi by 10.9 dB.

2. The generated geometry fired backwards. Element lengths were fixed fractions
   of a half wavelength while the wire radius was a fixed 2 mm, so at UHF the
   electrically fatter wire left the directors long enough to act as reflectors
   and NEC put the main lobe at phi = 180.

Tests that shell out to nec2c are marked ``nec2c`` and skip when the solver is
absent.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import subprocess
import tempfile

import pytest
from mcp.types import CallToolRequestParams

from mcp_nec2_antenna import server
from mcp_nec2_antenna.server import (
    SimulationResult,
    create_yagi,
    estimate_yagi_gain_dbi,
    parse_pattern,
    yagi_boom_length_lambda,
)

NEC2C = shutil.which("nec2c")
needs_nec2c = pytest.mark.skipif(NEC2C is None, reason="nec2c solver not installed")

# THETA, PHI, VERT, HOR, TOTAL -- we want the TOTAL power gain column.
_PATTERN_ROW = re.compile(
    r"^\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s"
)


def call_tool(tool: str, **arguments):
    """Invoke an MCP tool and return its decoded JSON payload."""
    result = asyncio.run(
        server.handle_call_tool(None, CallToolRequestParams(name=tool, arguments=arguments))
    )
    return json.loads(result.content[0].text)


def nec2c_pattern(deck: str) -> list[tuple[float, float, float]]:
    """Run a deck through nec2c and parse (theta, phi, gain_dbi) independently.

    Deliberately does not use the server's own parser, so a parsing bug cannot
    make the comparison agree with itself.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        nec_in = os.path.join(tmpdir, "a.nec")
        nec_out = os.path.join(tmpdir, "a.out")
        with open(nec_in, "w") as handle:
            handle.write(deck)
        subprocess.run([NEC2C, "-i", nec_in, "-o", nec_out], capture_output=True, timeout=300, check=True)
        with open(nec_out) as handle:
            raw = handle.read()

    points = []
    for block in raw.split("RADIATION PATTERNS")[1:]:
        for line in block.split("\n"):
            match = _PATTERN_ROW.match(line)
            if match:
                points.append((float(match.group(1)), float(match.group(2)), float(match.group(5))))
    return points


def gain_at(points, theta: float, phi: float) -> float:
    for point_theta, point_phi, gain in points:
        if abs(point_theta - theta) < 1e-6 and abs(point_phi - phi) < 1e-6:
            return gain
    raise AssertionError(f"direction theta={theta} phi={phi} not sampled")


# ---------------------------------------------------------------------------
# Defect 1: the reported gain must be the solver's, not an invented formula
# ---------------------------------------------------------------------------


@needs_nec2c
@pytest.mark.nec2c
@pytest.mark.parametrize("frequency_mhz,num_directors", [(146.0, 5), (434.0, 5), (146.0, 1)])
def test_reported_gain_matches_an_independent_nec2c_run(frequency_mhz, num_directors):
    """The gain handed back is the gain nec2c computes for the same deck.

    Against the old ``7 + 2*num_directors`` this fails by 5 dB at 146 MHz and
    by 10.9 dB at 434 MHz.
    """
    reported = call_tool(
        "nec2_create_yagi", name="t", frequency_mhz=frequency_mhz, num_directors=num_directors
    )
    assert reported["gain_basis"] == "simulated"

    antenna = server._antennas[reported["antenna_id"]]
    points = nec2c_pattern(antenna.to_nec2_input())
    solver_peak = max(gain for _, _, gain in points)

    assert reported["gain_dbi"] == pytest.approx(solver_peak, abs=0.1)


@needs_nec2c
@pytest.mark.nec2c
def test_reported_gain_sits_in_a_physically_sane_band():
    """A 7-element Yagi is a 10-13 dBi antenna, not a 17 dBi one."""
    reported = call_tool("nec2_create_yagi", name="t", frequency_mhz=434.0, num_directors=5)
    assert 9.0 <= reported["gain_dbi"] <= 14.0


def test_gain_is_always_labelled_and_the_invented_field_is_gone():
    """Callers can tell simulated from estimated, and the old field is retired."""
    reported = call_tool("nec2_create_yagi", name="t", frequency_mhz=146.0, num_directors=3)
    assert "expected_gain_dbi" not in reported
    assert reported["gain_basis"] in {"simulated", "estimated"}
    assert reported["gain_method"]


def test_gain_falls_back_to_a_labelled_estimate_when_the_solver_is_missing(monkeypatch):
    """No solver means an estimate that says so, never a bare number."""

    async def no_solver(*args, **kwargs):
        return SimulationResult(
            success=False, antenna_id="x", error="nec2c not found. Install with: sudo apt install nec2c"
        )

    monkeypatch.setattr(server, "run_nec2_simulation", no_solver)
    reported = call_tool("nec2_create_yagi", name="t", frequency_mhz=146.0, num_directors=5)

    assert reported["gain_basis"] == "estimated"
    assert "boom-length regression" in reported["gain_method"]
    assert "nec2c not found" in reported["gain_method"]
    assert reported["gain_dbi"] == pytest.approx(estimate_yagi_gain_dbi(5), abs=0.01)


def test_gain_estimate_grows_with_boom_length_not_linearly_with_directors():
    """The estimate must not be the old unbounded 2 dB per director ramp."""
    assert estimate_yagi_gain_dbi(18) < 16.0
    # Doubling the boom is worth well under 6 dB for a real Yagi.
    gain_short = estimate_yagi_gain_dbi(4)
    gain_double = estimate_yagi_gain_dbi(9)
    assert yagi_boom_length_lambda(9) == pytest.approx(2 * yagi_boom_length_lambda(4))
    assert 1.0 < gain_double - gain_short < 3.0


@needs_nec2c
@pytest.mark.nec2c
@pytest.mark.parametrize("num_directors", [1, 3, 5, 8, 13])
def test_gain_estimate_stays_within_its_stated_accuracy(num_directors):
    """The fallback fit is honest about how close it is to the solver."""
    reported = call_tool("nec2_create_yagi", name="t", frequency_mhz=146.0, num_directors=num_directors)
    assert reported["gain_basis"] == "simulated"
    assert abs(estimate_yagi_gain_dbi(num_directors) - reported["gain_dbi"]) <= server.YAGI_GAIN_FIT_MAX_ERROR_DB


# ---------------------------------------------------------------------------
# Defect 2: the array must fire toward the directors
# ---------------------------------------------------------------------------


@needs_nec2c
@pytest.mark.nec2c
@pytest.mark.parametrize("frequency_mhz", [14.2, 146.0, 434.0, 1296.0])
@pytest.mark.parametrize("num_elements", [3, 5, 7, 10])
def test_main_lobe_points_at_the_directors(frequency_mhz, num_elements):
    """Main lobe on the boom axis at phi = 0, with a positive front-to-back.

    The old geometry put the lobe at phi = 180 for 4 and 5 elements at 434 MHz
    and for 5 elements upward at 1296 MHz.
    """
    antenna = create_yagi("t", frequency_mhz, num_directors=num_elements - 2)
    points = nec2c_pattern(antenna.to_nec2_input())

    peak_theta, peak_phi, peak_gain = max(points, key=lambda p: p[2])
    assert peak_phi == pytest.approx(0.0), f"main lobe at phi={peak_phi}, i.e. out of the back"
    # The elevation cut is flat-topped to the two decimals NEC prints, so max()
    # can land a sample either side of the boom axis. What matters is that
    # boresight is the main lobe, not which tied sample wins.
    assert abs(peak_theta - 90.0) <= 4.0, f"main lobe off the boom axis at theta={peak_theta}"

    forward = gain_at(points, 90.0, 0.0)
    backward = gain_at(points, 90.0, 180.0)
    assert forward == pytest.approx(peak_gain, abs=0.05), "boresight is not the main lobe"
    assert forward - backward > 3.0, f"front-to-back only {forward - backward:.1f} dB"


@needs_nec2c
@pytest.mark.nec2c
@pytest.mark.parametrize("frequency_mhz", [14.2, 146.0, 434.0])
def test_forward_gain_rises_with_element_count(frequency_mhz):
    """More elements on a longer boom must buy gain, at every band."""
    gains = []
    for num_elements in (3, 5, 7, 10):
        antenna = create_yagi("t", frequency_mhz, num_directors=num_elements - 2)
        gains.append(gain_at(nec2c_pattern(antenna.to_nec2_input()), 90.0, 0.0))

    assert gains == sorted(gains), f"forward gain not monotonic: {gains}"
    assert gains[-1] - gains[0] > 2.0


def test_element_lengths_follow_standard_yagi_practice():
    """Reflector longer than driven, directors shorter and tapering."""
    antenna = create_yagi("t", 146.0, num_directors=4)
    lengths = [abs(w.y2 - w.y1) for w in antenna.wires]
    reflector, driven, *directors = lengths

    assert reflector / driven == pytest.approx(1.05, abs=0.01)
    assert 0.93 <= directors[0] / driven <= 0.97
    assert directors == sorted(directors, reverse=True), "directors should taper along the boom"


def test_directors_sit_forward_of_the_driven_element():
    """Boom geometry: reflector behind the feed, every director ahead of it."""
    antenna = create_yagi("t", 146.0, num_directors=4)
    reflector, driven, *directors = antenna.wires

    assert reflector.x1 < 0
    assert driven.x1 == 0
    assert all(d.x1 > 0 for d in directors)
    assert [d.x1 for d in directors] == sorted(d.x1 for d in directors)


def test_element_lengths_track_wire_thickness():
    """A fatter wire in wavelengths must give shorter elements.

    This is the root cause of the backwards-firing array: with lengths pinned to
    a half wavelength, a fixed 2 mm wire at 434 MHz left the directors
    electrically long enough to reflect.
    """

    def driven_in_wavelengths(frequency_mhz):
        antenna = create_yagi("t", frequency_mhz, num_directors=1)
        return abs(antenna.wires[1].y2 - antenna.wires[1].y1) / antenna.wavelength()

    thin = driven_in_wavelengths(14.2)
    fat = driven_in_wavelengths(1296.0)
    assert fat < thin - 0.01, f"thickness ignored: {thin:.4f} vs {fat:.4f} wavelengths"
    assert 0.45 < fat < thin < 0.49


# ---------------------------------------------------------------------------
# The pattern a caller is shown must be the one for the frequency they asked for
# ---------------------------------------------------------------------------


def test_parse_pattern_labels_each_frequency_separately():
    """A sweep yields one pattern per frequency, each carrying its own value.

    The old parser returned a single unlabelled pattern built from the first
    block in the file, so a +/-10% sweep reported the pattern at 0.9x the design
    frequency as if it were the design-frequency pattern.
    """
    block = (
        "                    --------- FREQUENCY --------\n"
        "                     FREQUENCY : {freq}E+02 MHz\n"
        "                --------- ANTENNA INPUT PARAMETERS ---------\n"
        "                ---------- RADIATION PATTERNS -----------\n"
        "  THETA      PHI       VERTC    HORIZ    TOTAL\n"
        " DEGREES   DEGREES        DB       DB       DB\n"
        "   90.00      0.00   -999.99     {g}     {g}\n"
        "   90.00    180.00   -999.99      0.00      0.00\n"
    )
    raw = block.format(freq="1.3140", g="5.00") + block.format(freq="1.4600", g="11.70")

    patterns = parse_pattern(raw)
    assert [p.frequency_mhz for p in patterns] == [131.40, 146.00]
    assert [p.max_gain_db for p in patterns] == [5.00, 11.70]

    nearest = server.pattern_nearest(patterns, 146.0)
    assert nearest.frequency_mhz == 146.00
    assert nearest.max_gain_db == 11.70


def test_parse_pattern_reports_peaks_below_isotropic():
    """A pattern that never exceeds 0 dBi must not be reported as 0 dBi."""
    raw = (
        "        --------- FREQUENCY --------\n"
        "         FREQUENCY : 1.4600E+02 MHz\n"
        "        ---------- RADIATION PATTERNS -----------\n"
        "   90.00      0.00   -999.99     -3.00     -3.00\n"
        "   90.00    180.00   -999.99     -9.00     -9.00\n"
    )
    pattern = parse_pattern(raw)[0]
    assert pattern.max_gain_db == -3.00
    assert pattern.max_gain_phi == 0.0
    assert pattern.front_to_back_db == pytest.approx(6.0)


@needs_nec2c
@pytest.mark.nec2c
def test_simulate_reports_the_design_frequency_pattern():
    """nec2_simulate and nec2_create_yagi must agree about the same antenna."""
    created = call_tool("nec2_create_yagi", name="t", frequency_mhz=146.0, num_directors=5)
    simulated = call_tool("nec2_simulate", antenna_id=created["antenna_id"])

    assert simulated["pattern"]["frequency_mhz"] == pytest.approx(146.0, abs=0.5)
    assert simulated["pattern"]["max_gain_dbi"] == pytest.approx(created["gain_dbi"], abs=0.1)


def test_boom_length_is_reported_and_consistent():
    reported = call_tool("nec2_create_yagi", name="t", frequency_mhz=146.0, num_directors=5)
    wavelength = 299792458.0 / 146e6
    assert reported["boom_length_wavelengths"] == pytest.approx(1.2)
    assert reported["boom_length_m"] == pytest.approx(1.2 * wavelength, abs=0.01)
    assert not math.isnan(reported["gain_dbi"])
