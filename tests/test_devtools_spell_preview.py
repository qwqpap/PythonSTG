from __future__ import annotations

import textwrap

import pytest

from src.devtools.spell_preview import (
    SpellPreviewRuntime,
    SpellPreviewError,
    SpellPreviewSession,
    get_spell_preview_patch,
    load_spell_target,
    parse_vec2,
    preview,
    resolve_preview_load,
)
from src.game.bullet.optimized_pool import OptimizedBulletPool
from src.game.stage.spellcard import SpellCard


def _write_spell(tmp_path, source: str):
    path = tmp_path / "stage1.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_load_spell_target_by_class_name(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class MySpell(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )

    target = load_spell_target(path, "MySpell")

    assert target.script_path == path.resolve()
    assert target.spell_class.__name__ == "MySpell"


def test_load_spell_target_auto_detects_single_spell(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class OnlySpell(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )

    target = load_spell_target(path)

    assert target.spell_class.__name__ == "OnlySpell"


def test_load_spell_target_requires_name_for_multiple_spells(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class SpellA(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)

        class SpellB(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )

    with pytest.raises(SpellPreviewError, match="multiple SpellCard"):
        load_spell_target(path)


def test_load_spell_target_uses_single_preview_metadata_class(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class SpellA(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)

        class SpellB(SpellCard):
            preview = {"seed": 7}

            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )

    target = load_spell_target(path)

    assert target.spell_class.__name__ == "SpellB"


def test_parse_vec2_accepts_comma_pair():
    assert parse_vec2("0,-0.8") == (0.0, -0.8)


def test_parse_vec2_accepts_json_pair():
    assert parse_vec2([0, -0.8]) == (0.0, -0.8)


def test_parse_vec2_rejects_bad_shape():
    with pytest.raises(ValueError):
        parse_vec2("0,-0.8,1")


def test_preview_config_file_overrides_class_metadata(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class MySpell(SpellCard):
            preview = {
                "boss": "class_boss",
                "player_pos": (0, -0.4),
                "seed": 1,
                "duration": 60,
            }

            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )
    path.with_suffix(".preview.json").write_text(
        """
        {
          "spell": "MySpell",
          "boss": "file_boss",
          "player_pos": [0, -0.8],
          "seed": 114514,
          "speed": 1.5,
          "hitbox": true,
          "auto_reload": false,
          "duration": 1800
        }
        """,
        encoding="utf-8",
    )

    result = resolve_preview_load(path)

    assert result.target.spell_class.__name__ == "MySpell"
    assert result.config.boss == "file_boss"
    assert result.config.player_pos == (0.0, -0.8)
    assert result.config.seed == 114514
    assert result.config.speed == 1.5
    assert result.config.hitbox is True
    assert result.config.auto_reload is False
    assert result.config.duration == 1800


def test_preview_decorator_attaches_metadata():
    @preview(boss="decorated_boss", player_pos=(0, -0.7), seed=42)
    class DecoratedSpell(SpellCard):
        async def run(self):
            while True:
                await self.wait(1)

    patch = get_spell_preview_patch(DecoratedSpell)

    assert patch["boss"] == "decorated_boss"
    assert patch["player_pos"] == (0.0, -0.7)
    assert patch["seed"] == 42


def test_spell_preview_session_restarts_and_steps_spell():
    class OneShotSpell(SpellCard):
        async def run(self):
            self.fire(x=0, y=0, angle=-90, speed=1, bullet_type="ball_m", color="red")
            await self.wait(1)

    bullet_pool = OptimizedBulletPool(max_bullets=32)
    session = SpellPreviewSession(bullet_pool, seed=123)

    session.restart(OneShotSpell)
    session.step_one()

    assert session.frame == 1
    assert session.bullet_count == 1

    session.restart()

    assert session.frame == 0
    assert session.bullet_count == 0
    session.close()


def test_spell_preview_runtime_seek_fast_forwards_from_reset():
    class FireEveryFrameSpell(SpellCard):
        async def run(self):
            while True:
                self.fire(x=0, y=0, angle=-90, speed=1, bullet_type="ball_m", color="red")
                await self.wait(1)

    bullet_pool = OptimizedBulletPool(max_bullets=32)
    runtime = SpellPreviewRuntime(bullet_pool, use_config=False)
    runtime.target = type(
        "Target",
        (),
        {
            "script_path": None,
            "spell_class": FireEveryFrameSpell,
            "module": None,
        },
    )()

    runtime.seek(5)

    assert runtime.session.frame == 5
    assert runtime.session.bullet_count == 5
    runtime.close()


def test_spell_preview_runtime_pauses_when_spell_ends():
    class OneShotSpell(SpellCard):
        async def run(self):
            await self.wait(1)

    bullet_pool = OptimizedBulletPool(max_bullets=32)
    runtime = SpellPreviewRuntime(bullet_pool, use_config=False)
    runtime.session.restart(OneShotSpell)

    runtime.update()
    assert runtime.paused is False

    runtime.update()

    assert runtime.paused is True
    assert runtime.status == "Spell ended at frame 2"
    runtime.close()


def test_spell_preview_runtime_reload_failure_keeps_old_target(tmp_path):
    path = _write_spell(
        tmp_path,
        """
        from src.game.stage.spellcard import SpellCard

        class GoodSpell(SpellCard):
            async def run(self):
                while True:
                    await self.wait(1)
        """,
    )
    bullet_pool = OptimizedBulletPool(max_bullets=32)
    runtime = SpellPreviewRuntime(bullet_pool)

    runtime.load(path)
    old_target = runtime.target
    path.write_text("class Broken(:\n", encoding="utf-8")

    with pytest.raises(SpellPreviewError):
        runtime.reload()

    assert runtime.target is old_target
    assert runtime.error_info is not None
    assert runtime.error_info.title == "Reload failed"
    assert runtime.error_info.keeps_old_instance is True
    runtime.close()
