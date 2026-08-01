import pytest

from src.devtools.pattern_lab import PatternSpec, export_spellcard, simulate_burst
from src.devtools.pattern_runtime import PatternPlayback, preview_positions, spawn_pattern_burst


def test_pattern_lab_export_matches_spellcard_api_names():
    code = export_spellcard(PatternSpec(name="TestPattern", pattern="arc", count=7, angle_span=90))

    assert "class TestPattern" in code
    assert "arc_angle=90" in code
    assert "span=" not in code


def test_pattern_lab_export_formats_float_noise_cleanly():
    code = export_spellcard(PatternSpec(pattern="arc", speed=0.30000000000000004, x=-0.0))

    assert "speed=0.3" in code
    assert "x = 0.0" in code


def test_pattern_lab_simulation_returns_expected_frame_shape():
    frames = simulate_burst(PatternSpec(count=3), frames=4)

    assert len(frames) == 4
    assert all(len(frame) == 3 for frame in frames)


def test_native_pattern_runtime_uses_stage_context_create_bullet():
    calls = []

    class FakeContext:
        def create_bullet(self, **kwargs):
            calls.append(kwargs)
            return len(calls)

    spawned = spawn_pattern_burst(FakeContext(), PatternSpec(pattern="arc", count=3, angle_span=90), burst_index=1)

    assert spawned == 3
    assert len(calls) == 3
    assert calls[0]["bullet_type"] == "ball_m"
    assert calls[0]["color"] == "red"
    assert calls[1]["angle"] == 277.5


def test_native_pattern_preview_full_circle_uses_even_step():
    points = preview_positions(PatternSpec(count=4, angle_span=360, speed=1.0), age_seconds=1.0)

    assert len(points) == 4
    assert points[0][0] == pytest.approx(0.0)


def test_native_pattern_runtime_supports_multiple_modes():
    ring = preview_positions(PatternSpec(pattern="ring", count=4, speed=1.0), age_seconds=1.0)
    spiral = preview_positions(PatternSpec(pattern="spiral", count=4, angle_span=180, speed=1.0), age_seconds=1.0)
    flower = preview_positions(PatternSpec(pattern="flower", count=4, angle_span=90, speed=1.0), age_seconds=1.0)

    assert len(ring) == len(spiral) == len(flower) == 4
    assert spiral != ring
    assert flower != ring


def test_pattern_playback_uses_formal_batch_runner_not_per_bullet_calls():
    calls = []

    class FakeContext:
        def create_bullets_batch(self, **kwargs):
            calls.append(kwargs)
            return list(range(len(kwargs["angles"])))

        def create_bullet(self, **kwargs):
            raise AssertionError("formal playback must not use per-bullet spawning")

    playback = PatternPlayback(
        PatternSpec(pattern="ring", count=4, interval=2, bursts=2),
        owner_tag=4242,
    )

    assert playback.update(FakeContext()) == 4
    assert playback.update(FakeContext()) == 0
    assert playback.update(FakeContext()) == 4
    assert len(calls) == 2
    assert playback.runner.program is playback.program
