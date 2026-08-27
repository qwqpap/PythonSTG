from __future__ import annotations

import textwrap
import sys

import pytest

from src.authoring.dsl import Break, FireCircle, Repeat, Stage, Wait, ring_burst as builtin_ring_burst, template
from src.authoring.program import Node, TemplateTarget, make_template_call
from src.authoring.python_source import load_python_source, save_python_source
from src.authoring.templates import (
    ImportSpec,
    TemplateExpansionError,
    TemplateRegistry,
    TemplateResolutionError,
    expand_nodes,
)


@template
def ring_burst(count: int = 12, interval: int = 6):
    return [Repeat(count, [FireCircle(count=24), Wait(interval)])]


def test_template_call_is_retained_and_build_expansion_is_separate():
    call = ring_burst(count=20, uid="ring_call")
    registry = TemplateRegistry()
    registry.register(ring_burst)

    expanded = expand_nodes([call], registry)

    assert call.kind == "TemplateCall"
    assert call.arguments == {"count": 20}
    assert expanded[0].kind == "Repeat"
    assert expanded[0].arguments["count"] == 20
    assert expanded[0].uid.startswith("ring_call__expanded_")
    assert call.uid == "ring_call"


def test_template_arguments_are_recursively_checked_against_annotations():
    @template
    def typed_wait(frames: int, labels: list[str] = []):
        return [Wait(frames)]

    registry = TemplateRegistry()
    registry.register(typed_wait)

    for call in (
        typed_wait(frames="sixty", uid="bad_frames"),
        typed_wait(frames=60, labels=[1], uid="bad_labels"),
    ):
        with pytest.raises(TemplateExpansionError) as captured:
            expand_nodes([call], registry)
        assert captured.value.code == "template_signature"
        assert captured.value.call_uid == call.uid
        assert captured.value.related


def test_template_return_nodes_are_structurally_validated_and_mapped_to_call():
    @template
    def bad_wait():
        return [Wait("bad")]

    @template
    def bad_break():
        return [Break()]

    registry = TemplateRegistry()
    registry.register(bad_wait)
    registry.register(bad_break)

    for call in (bad_wait(uid="bad_wait_call"), bad_break(uid="bad_break_call")):
        with pytest.raises(TemplateExpansionError) as captured:
            expand_nodes([call], registry)
        assert captured.value.code == "template_result"
        assert captured.value.call_uid == call.uid
        assert captured.value.related


def test_template_cannot_mutate_retained_call_arguments_during_expansion():
    @template
    def mutating(values: list[int], options: dict[str, int]):
        values.append(99)
        options["changed"] = 1
        return []

    call = mutating([1, 2], {"original": 1}, uid="mutating_call")
    before = call.semantic_data()
    registry = TemplateRegistry()
    registry.register(mutating)

    assert expand_nodes([call], registry) == []
    assert call.semantic_data() == before


def test_template_reusing_one_node_produces_independent_unique_derived_nodes():
    @template
    def reuse_node():
        shot = FireCircle(count=8)
        return [shot, shot]

    call = reuse_node(uid="reuse_call")
    registry = TemplateRegistry()
    registry.register(reuse_node)

    first = expand_nodes([call], registry)
    second = expand_nodes([call], registry)

    assert first[0] is not first[1]
    assert first[0].uid != first[1].uid
    assert [node.uid for node in first] == [node.uid for node in second]

    @template
    def reuse_nested():
        wait = Wait(2)
        from src.authoring.dsl import Parallel

        return [Parallel([[wait], [wait]])]

    registry.register(reuse_nested)
    nested = expand_nodes([reuse_nested(uid="nested_call")], registry)[0]
    left = nested.children["branches"][0].children["body"][0]
    right = nested.children["branches"][1].children["body"][0]
    assert left is not right
    assert left.uid != right.uid


def test_mutable_template_default_is_deep_copied_after_apply_defaults():
    @template
    def mutable_default(values=[]):
        values.append(1)
        return [Wait(len(values))]

    call = mutable_default(uid="default_call")
    registry = TemplateRegistry()
    registry.register(mutable_default)

    first = expand_nodes([call], registry)
    second = expand_nodes([call], registry)

    assert first[0].arguments["frames"] == 1
    assert first[0].semantic_data() == second[0].semantic_data()


def test_builtin_template_uses_the_same_retained_call_and_expansion_api():
    registry = TemplateRegistry.with_builtins()
    call = builtin_ring_burst(count=2, interval=4, uid="builtin_call")

    expanded = expand_nodes([call], registry)

    assert call.kind == "TemplateCall"
    assert expanded[0].kind == "Repeat"
    assert expanded[0].arguments["count"] == 2


def test_project_module_and_explicit_external_template_use_the_same_registry_api():
    registry = TemplateRegistry()
    module = sys.modules[ring_burst.__module__]

    project_definitions = registry.register_module_templates(module)

    assert any(item.identity.endswith(".ring_burst") for item in project_definitions)
    external = TemplateRegistry()
    errors = external.load_explicit_imports(
        (ImportSpec(ring_burst.__module__, "ring_burst", "external_ring"),)
    )
    assert errors == ()
    assert external.resolve("external_ring").identity.endswith(".ring_burst")


def test_explicit_import_preload_ignores_ordinary_future_and_typing_symbols():
    registry = TemplateRegistry()

    errors = registry.load_explicit_imports(
        (
            ImportSpec("__future__", "annotations"),
            ImportSpec("typing", "Any"),
            ImportSpec(ring_burst.__module__, "ring_burst", "external_ring"),
        )
    )

    assert errors == ()
    assert registry.resolve("external_ring").identity.endswith(".ring_burst")


def test_template_signature_exception_and_recursion_map_to_call_and_definition():
    registry = TemplateRegistry()
    registry.register(ring_burst)
    bad_signature = ring_burst(no_such_argument=1, uid="bad_signature")
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([bad_signature], registry)
    assert caught.value.code == "template_signature"
    assert caught.value.call_uid == "bad_signature"
    assert caught.value.related

    @template
    def broken():
        raise RuntimeError("boom")

    registry.register(broken)
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([broken(uid="broken_call")], registry)
    assert caught.value.code == "template_exception"
    assert caught.value.call_uid == "broken_call"

    @template
    def recursive():
        return [recursive()]

    registry.register(recursive)
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([recursive(uid="recursive_call")], registry)
    assert caught.value.code == "template_recursion"
    assert caught.value.call_uid == "recursive_call"
    assert "recursive" in caught.value.message

    @template
    def nested_broken():
        raise RuntimeError("nested boom")

    @template
    def outer():
        return [nested_broken()]

    registry.register(nested_broken)
    registry.register(outer)
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([outer(uid="outer_source_call")], registry)
    assert caught.value.code == "template_exception"
    assert caught.value.call_uid == "outer_source_call"
    assert caught.value.identity.endswith(".nested_broken")
    assert caught.value.related


@pytest.mark.parametrize("invalid_result", (None, 123, {"not": "nodes"}))
def test_template_invalid_scalar_or_mapping_result_is_not_treated_as_empty(invalid_result):
    @template
    def invalid():
        return invalid_result

    registry = TemplateRegistry()
    registry.register(invalid)

    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([invalid(uid="invalid_call")], registry)

    assert caught.value.code == "template_result"
    assert caught.value.call_uid == "invalid_call"
    assert caught.value.related


def test_missing_external_package_is_reported_without_losing_call_arguments():
    imports = (ImportSpec("definitely_missing_pystg_templates", "ring"),)
    registry = TemplateRegistry()
    errors = registry.load_explicit_imports(imports)
    call = make_template_call(
        TemplateTarget(
            identity="definitely_missing_pystg_templates.ring",
            symbol="ring",
            module="definitely_missing_pystg_templates",
        ),
        keywords={"count": 9},
        uid="missing_call",
    )

    assert len(errors) == 1
    assert call.arguments == {"count": 9}
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([call], registry)
    assert caught.value.code == "template_missing"
    with pytest.raises(TemplateResolutionError):
        registry.resolve_explicit_target(call.template, imports)


def test_import_time_template_module_exception_is_always_wrapped(tmp_path, monkeypatch):
    module_name = "pystg_boom_templates_for_test"
    (tmp_path / f"{module_name}.py").write_text(
        "raise RuntimeError('import boom')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = TemplateRegistry()
    imports = (ImportSpec(module_name, "burst"),)
    target = TemplateTarget(
        identity=f"{module_name}.burst",
        symbol="burst",
        module=module_name,
    )

    with pytest.raises(TemplateResolutionError, match="import boom"):
        registry.load_module_templates(module_name)
    errors = registry.load_explicit_imports(imports)
    assert len(errors) == 1
    assert "import boom" in errors[0].message
    with pytest.raises(TemplateResolutionError, match="import boom"):
        registry.resolve_explicit_target(target, imports)

    call = make_template_call(target, uid="source_call")
    with pytest.raises(TemplateExpansionError) as caught:
        expand_nodes([call], registry)
    assert caught.value.code == "template_missing"
    assert caught.value.call_uid == "source_call"


def test_python_source_keeps_local_template_call_aggregated_across_save(tmp_path):
    path = tmp_path / "stage.py"
    path.write_text(
        textwrap.dedent(
            """
            from src.authoring.dsl import FireCircle, Repeat, Stage, Wait, template

            @template
            def local_ring(count: int = 12):
                return [Repeat(count, body=[FireCircle(count=24), Wait(6)])]

            stage = Stage(
                id="stage_1",
                name="Stage",
                body=[local_ring(count=20)],
            )
            """
        ).lstrip(),
        encoding="utf-8",
    )
    document = load_python_source(path, module_name="demo.stage")

    call = document.unit.body[0]
    assert call.kind == "TemplateCall"
    assert call.template.identity == "demo.stage.local_ring"
    assert call.arguments == {"count": 20}
    signature = document.templates[0].signature
    assert signature.parameters["count"].annotation == "int"
    assert signature.parameters["count"].default == 12

    document.mark_dirty()
    rendered = save_python_source(document)
    reopened = load_python_source(path, module_name="demo.stage")

    assert "local_ring(count=20" in rendered
    assert "Repeat(" in rendered  # template definition only
    assert reopened.unit.body[0].kind == "TemplateCall"
    assert reopened.unit.body[0].arguments == {"count": 20}


@pytest.mark.parametrize(
    ("import_line", "call_name"),
    (
        ("from missing_template_package import templates as t", "t.ring"),
        ("from missing_template_package import templates", "templates.ring"),
    ),
)
def test_from_imported_template_module_attribute_call_is_retained(
    tmp_path, import_line, call_name
):
    path = tmp_path / "stage.py"
    path.write_text(
        textwrap.dedent(
            f"""
            from src.authoring.dsl import Stage
            {import_line}

            stage = Stage(
                "stage_1",
                "Stage",
                [{call_name}(count=5)],
            )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    document = load_python_source(path, module_name="demo.stage")
    call = document.unit.body[0]
    before = document.unit.semantic_data()
    document.mark_dirty()
    rendered = save_python_source(document)
    reopened = load_python_source(path, module_name=document.module_name)

    assert call.template.identity == "missing_template_package.templates.ring"
    assert f"{call_name}(count=5" in rendered
    assert reopened.unit.semantic_data() == before
