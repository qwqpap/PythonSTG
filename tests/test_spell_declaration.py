from src.game.stage.spell_declaration import SpellDeclaration, TOTAL_DURATION


def test_spell_declaration_stays_visible_after_intro_until_finished():
    declaration = SpellDeclaration("Test Spell")

    declaration.update(TOTAL_DURATION + 5.0)

    assert declaration.active
    assert not declaration.blocks_spell_update

    state = declaration.get_state((0, 0, 384, 448), (640, 480))
    assert state.name_anchor_right == 1.0
    assert state.name_cy == 38
    assert state.line_visible
    assert state.line_alpha == 1.0
    assert state.band_alpha == 0.0

    declaration.finish()

    assert not declaration.active
