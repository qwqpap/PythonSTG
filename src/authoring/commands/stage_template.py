"""Undoable beginner Stage skeletons over the Scene authoring model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.authoring.scene.document import (
    SceneDocument,
    StateGraphSpec,
    StateSpec,
    TimelineClip,
    TimelineKeyframe,
    TimelineTrack,
    TransitionSpec,
)
from src.authoring.scene.node_types import make_node


TemplateKind = Literal["midstage", "two_phase_boss"]


def _template_labels(language: str) -> dict[str, str]:
    """Return author-visible defaults without changing runtime type IDs."""

    if language != "zh-CN":
        return {}
    return {
        "Midstage": "道中关卡",
        "Two-phase Boss": "两阶段 Boss",
        "Stage": "关卡",
        "Spell": "符卡",
        "Emitter": "发射器",
        "Pattern": "弹幕实例",
        "Wave A": "第一波",
        "Wave B": "第二波",
        "Intro": "登场",
        "Normal": "通常阶段",
        "Enrage": "强化阶段",
        "End": "结束",
        "Background": "背景",
        "Background transition": "背景转场",
        "BGM": "背景音乐",
        "Stage BGM": "关卡背景音乐",
        "On encounter cleared": "敌人全灭后",
        "Continue after all enemies are defeated": "敌人全灭后继续",
        "Boss sweep": "Boss 横向移动",
        "Pattern suffix": "弹幕",
        "Movement suffix": "移动",
        "complete suffix": "完成",
    }


def _label(labels: dict[str, str], text: str) -> str:
    return labels.get(text, text)


class StageTemplateError(ValueError):
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


def _copy_scene(target: SceneDocument, source: SceneDocument) -> None:
    clone = SceneDocument.from_dict(source.to_dict())
    target.name = clone.name
    target.root = clone.root
    target.id = clone.id
    target.schema_version = clone.schema_version
    target.type = clone.type
    target.symbol_name = clone.symbol_name
    target.state_graph = clone.state_graph
    target.timeline = clone.timeline
    target.metadata = clone.metadata
    target.variables = clone.variables
    target.output_mappings = clone.output_mappings


def _pattern_track(
    name: str,
    target_id: str,
    duration: int,
    *,
    labels: dict[str, str],
) -> TimelineTrack:
    display_name = _label(labels, name)
    return TimelineTrack(
        name=(
            f"{display_name}{_label(labels, 'Pattern suffix')}"
            if labels
            else f"{display_name} Pattern"
        ),
        kind="Pattern",
        channel="danmaku",
        target_id=target_id,
        order=0,
        clips=[
            TimelineClip(
                name=display_name,
                kind="Pattern",
                start_frame=0,
                duration_frames=duration,
                channel="danmaku",
            )
        ],
    )


def _movement_track(
    name: str,
    target_id: str,
    duration: int,
    *,
    labels: dict[str, str],
) -> TimelineTrack:
    display_name = _label(labels, name)
    return TimelineTrack(
        name=(
            f"{display_name}{_label(labels, 'Movement suffix')}"
            if labels
            else f"{display_name} Movement"
        ),
        kind="Movement",
        channel="position",
        target_id=target_id,
        order=1,
        clips=[
            TimelineClip(
                name=_label(labels, "Boss sweep"),
                kind="Movement",
                start_frame=0,
                duration_frames=duration,
                channel="position",
                keyframes=[
                    TimelineKeyframe(0, {"x": 128.0, "y": 96.0}),
                    TimelineKeyframe(
                        duration,
                        {"x": 256.0, "y": 96.0},
                        interpolation="ease_in_out",
                    ),
                ],
            )
        ],
    )


def _background_track(
    resource: str,
    *,
    order: int = 2,
    labels: dict[str, str],
) -> TimelineTrack:
    return TimelineTrack(
        name=_label(labels, "Background"),
        kind="Background",
        channel="background",
        order=order,
        clips=[
            TimelineClip(
                name=_label(labels, "Background transition"),
                kind="Background",
                start_frame=0,
                duration_frames=1,
                channel="background",
                payload={"resource": resource, "fade_frames": 30},
            )
        ],
    )


def _audio_track(
    resource: str,
    duration: int,
    *,
    order: int = 3,
    labels: dict[str, str],
) -> TimelineTrack:
    return TimelineTrack(
        name=_label(labels, "BGM"),
        kind="Audio",
        channel="bgm",
        order=order,
        clips=[
            TimelineClip(
                name=_label(labels, "Stage BGM"),
                kind="Audio",
                start_frame=0,
                duration_frames=duration,
                channel="bgm",
                payload={"action": "play", "resource": resource, "loops": -1},
            )
        ],
    )


def _cleared_reaction(
    duration: int,
    *,
    order: int = 4,
    labels: dict[str, str],
) -> TimelineTrack:
    return TimelineTrack(
        name=_label(labels, "On encounter cleared"),
        kind="Reactive",
        channel="reaction",
        order=order,
        clips=[
            TimelineClip(
                name=_label(labels, "Continue after all enemies are defeated"),
                kind="Reactive",
                start_frame=0,
                duration_frames=duration,
                channel="reaction",
                payload={
                    "activation": {
                        "kind": "on_event",
                        "event_type": "encounter.cleared",
                    },
                    "reaction": {
                        "id": "beginner.encounter-cleared",
                        "event_type": "encounter.cleared",
                        "action": "stage.state.complete",
                        "scope": "state",
                        "once_per_scope": True,
                    },
                },
            )
        ],
    )


def _scene_nodes(
    document: SceneDocument,
    pattern_resource: str,
    *,
    labels: dict[str, str],
):
    stage = make_node("Stage", name=_label(labels, "Stage"))
    boss = make_node("Boss", name="Boss")
    boss.properties.update({"x": 192.0, "y": 96.0})
    spell = make_node("Spell", name=_label(labels, "Spell"))
    emitter = make_node("Emitter", name=_label(labels, "Emitter"))
    emitter.properties.update({"x": 192.0, "y": 96.0})
    pattern = make_node("PatternInstance", name=_label(labels, "Pattern"))
    pattern.properties["pattern"] = pattern_resource
    emitter.children.append(pattern)
    spell.children.append(emitter)
    boss.children.append(spell)
    stage.children.append(boss)
    document.root.children = [stage]
    return boss, pattern


def build_stage_template(
    document: SceneDocument,
    kind: TemplateKind,
    *,
    pattern_resource: str,
    background_resource: str,
    audio_resource: str = "stage_theme",
    language: str = "en",
) -> SceneDocument:
    for path, value in (
        ("template.pattern_resource", pattern_resource),
        ("template.background_resource", background_resource),
        ("template.audio_resource", audio_resource),
    ):
        if not isinstance(value, str) or not value.strip():
            raise StageTemplateError(path, "must be a non-empty resource reference")
        if path != "template.audio_resource" and not value.startswith("res://"):
            raise StageTemplateError(path, "must be project-relative (res://)")
    if kind not in {"midstage", "two_phase_boss"}:
        raise StageTemplateError("template.kind", "is unsupported")

    labels = _template_labels(language)
    result = SceneDocument.from_dict(document.to_dict())
    result.name = _label(
        labels, "Midstage" if kind == "midstage" else "Two-phase Boss"
    )
    boss, pattern = _scene_nodes(result, pattern_resource, labels=labels)

    if kind == "midstage":
        wave_a = StateSpec(name=_label(labels, "Wave A"), duration_frames=1800)
        wave_b = StateSpec(name=_label(labels, "Wave B"), duration_frames=1800)
        end = StateSpec(name=_label(labels, "End"), duration_frames=1)
        wave_a.tracks = [
            _pattern_track("Wave A", pattern.id, 1800, labels=labels),
            _movement_track("Wave A", boss.id, 180, labels=labels),
            _background_track(background_resource, labels=labels),
            _audio_track(audio_resource, 1800, labels=labels),
            _cleared_reaction(1800, labels=labels),
        ]
        wave_b.tracks = [
            _pattern_track("Wave B", pattern.id, 1800, labels=labels),
            _cleared_reaction(1800, order=1, labels=labels),
        ]
        wave_a.transitions.append(
            TransitionSpec(
                f"{wave_a.name}{_label(labels, 'complete suffix')}"
                if labels else "Wave A complete",
                wave_b.id,
                "complete",
            )
        )
        wave_b.transitions.append(
            TransitionSpec(
                f"{wave_b.name}{_label(labels, 'complete suffix')}"
                if labels else "Wave B complete",
                end.id,
                "complete",
            )
        )
        states = [wave_a, wave_b, end]
    else:
        intro = StateSpec(name=_label(labels, "Intro"), duration_frames=120)
        phase_one = StateSpec(name=_label(labels, "Normal"), duration_frames=1800)
        phase_two = StateSpec(name=_label(labels, "Enrage"), duration_frames=1800)
        end = StateSpec(name=_label(labels, "End"), duration_frames=1)
        intro.tracks = [
            _background_track(background_resource, order=0, labels=labels),
            _audio_track(audio_resource, 120, order=1, labels=labels),
        ]
        phase_one.tracks = [
            _pattern_track("Normal", pattern.id, 1800, labels=labels),
            _movement_track("Normal", boss.id, 240, labels=labels),
            _cleared_reaction(1800, labels=labels),
        ]
        phase_two.tracks = [
            _pattern_track("Enrage", pattern.id, 1800, labels=labels),
            _background_track(background_resource, order=1, labels=labels),
            _cleared_reaction(1800, order=2, labels=labels),
        ]
        intro.transitions.append(TransitionSpec(
            f"{intro.name}{_label(labels, 'complete suffix')}"
            if labels else "Intro complete",
            phase_one.id,
            "complete",
        ))
        phase_one.transitions.append(
            TransitionSpec(
                f"{phase_one.name}{_label(labels, 'complete suffix')}"
                if labels else "Normal complete",
                phase_two.id,
                "complete",
            )
        )
        phase_two.transitions.append(TransitionSpec(
            f"{phase_two.name}{_label(labels, 'complete suffix')}"
            if labels else "Enrage complete",
            end.id,
            "complete",
        ))
        states = [intro, phase_one, phase_two, end]

    for order, state in enumerate(states):
        state.order = order
    result.state_graph = StateGraphSpec(
        name="StageFlow",
        initial_state_id=states[0].id,
        states=states,
    )
    result.metadata["template"] = {"kind": kind, "version": 1}
    result.metadata["duration_frames"] = sum(state.duration_frames for state in states)
    result.validate()
    return result


@dataclass
class ApplyStageTemplateCommand:
    document: SceneDocument
    kind: TemplateKind
    pattern_resource: str
    background_resource: str
    audio_resource: str = "stage_theme"
    language: str = "en"
    label: str = "Apply Stage template"
    _before: SceneDocument | None = field(default=None, init=False, repr=False)
    _after: SceneDocument | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        if self._before is None:
            self._before = SceneDocument.from_dict(self.document.to_dict())
        if self._after is None:
            self._after = build_stage_template(
                self.document,
                self.kind,
                pattern_resource=self.pattern_resource,
                background_resource=self.background_resource,
                audio_resource=self.audio_resource,
                language=self.language,
            )
        _copy_scene(self.document, self._after)

    def undo(self) -> None:
        if self._before is None:
            raise StageTemplateError("command", "cannot undo before execution")
        _copy_scene(self.document, self._before)
