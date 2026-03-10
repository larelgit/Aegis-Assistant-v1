"""Tests for the heuristic label function in build_dataset.py."""
import pytest
from build_dataset import label


def _row(**overrides):
    """Create a default row dict, then apply overrides."""
    defaults = dict(
        gold_adv=0, xp_adv=0,
        our_alive=5, enemy_alive=5,
        our_dead_tot=0, enemy_dead_tot=0,
        our_core_alive=2, enemy_core_alive=2, enemy_core_dead=0,
        roshan_alive=0, recent_deaths=0, towers_dire_t3_down=0,
    )
    defaults.update(overrides)
    return defaults


class TestLabel:
    def test_default_is_farm(self):
        assert label(_row(gold_adv=1000)) == "FARM"

    def test_stack_even_game(self):
        assert label(_row(gold_adv=500)) == "STACK"

    def test_teamfight(self):
        assert label(_row(recent_deaths=8)) == "TEAMFIGHT"

    def test_push(self):
        assert label(_row(gold_adv=5000, enemy_dead_tot=0)) == "PUSH"

    def test_defend(self):
        assert label(_row(gold_adv=-5000, our_dead_tot=0)) == "DEFEND"

    def test_siege(self):
        result = label(_row(gold_adv=12000, towers_dire_t3_down=1))
        assert result == "SIEGE"

    def test_take_roshan(self):
        result = label(_row(
            roshan_alive=1, enemy_core_dead=1,
            our_core_alive=2, gold_adv=1000,
        ))
        assert result == "TAKE_ROSHAN"

    def test_contest_roshan(self):
        result = label(_row(
            roshan_alive=1, our_core_alive=2,
            enemy_core_alive=2, recent_deaths=3,
        ))
        assert result == "CONTEST_ROSHAN"

    def test_gank(self):
        result = label(_row(
            our_alive=4, enemy_core_alive=1, recent_deaths=0,
            gold_adv=1000,
        ))
        assert result == "GANK"

    def test_teamfight_priority_over_roshan(self):
        """TEAMFIGHT (6+ deaths) should override TAKE_ROSHAN."""
        result = label(_row(
            recent_deaths=7, roshan_alive=1,
            enemy_core_dead=2, our_core_alive=2,
        ))
        assert result == "TEAMFIGHT"
