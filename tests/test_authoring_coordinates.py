import pytest

from src.authoring import CoordinateSpace, Timebase


@pytest.mark.parametrize(
    ("authoring", "runtime"),
    [
        ((0.0, 0.0), (-1.0, 1.0)),
        ((384.0, 448.0), (1.0, -1.0)),
        ((192.0, 224.0), (0.0, 0.0)),
        ((192.0, 100.8), (0.0, 0.55)),
    ],
)
def test_authoring_runtime_coordinate_contract(authoring, runtime):
    coordinates = CoordinateSpace()
    assert coordinates.authoring_to_runtime(*authoring) == pytest.approx(runtime)
    assert coordinates.runtime_to_authoring(*runtime) == pytest.approx(authoring)


def test_viewport_scale_does_not_change_runtime_position():
    coordinates = CoordinateSpace()
    logical = coordinates.viewport_to_runtime(
        96,
        112,
        viewport_width=384,
        viewport_height=448,
    )
    doubled = coordinates.viewport_to_runtime(
        192,
        224,
        viewport_width=768,
        viewport_height=896,
    )
    fractional = coordinates.viewport_to_runtime(
        144,
        168,
        viewport_width=576,
        viewport_height=672,
    )
    assert logical == pytest.approx(doubled)
    assert logical == pytest.approx(fractional)


def test_timebase_stores_frames_and_displays_seconds_and_beats():
    timebase = Timebase(60)
    assert timebase.frames_to_seconds(90) == 1.5
    assert timebase.seconds_to_frames(1.5) == 90
    assert timebase.frames_to_beats(90, 120.0) == 3.0
    assert timebase.beats_to_frames(3.0, 120.0) == 90
    with pytest.raises(ValueError):
        timebase.seconds_to_frames(-1)
    with pytest.raises(ValueError):
        timebase.frames_to_beats(1, 0)
    with pytest.raises(ValueError):
        Timebase(60.0)
