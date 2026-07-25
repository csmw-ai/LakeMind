from __future__ import annotations
from lakemind_server.security.actions import Action, ALL_ACTIONS


class TestActions:
    def test_action_count(self):
        assert len(Action) == 36

    def test_all_actions_matches_enum(self):
        assert len(ALL_ACTIONS) == 36
        assert all(isinstance(a, str) for a in ALL_ACTIONS)

    def test_action_values_are_unique(self):
        values = [a.value for a in Action]
        assert len(values) == len(set(values))

    def test_action_format(self):
        for a in Action:
            assert ":" in a.value
            parts = a.value.split(":")
            assert len(parts) == 2
            assert parts[0]
            assert parts[1]

    def test_key_actions_exist(self):
        assert Action.JOB_SUBMIT.value == "job:submit"
        assert Action.ASSET_CREATE.value == "asset:create"
        assert Action.SKILL_EXECUTE.value == "skill:execute"
        assert Action.CONFIG_WRITE.value == "config:write"
        assert Action.OPERATION_APPROVE.value == "operation:approve"
