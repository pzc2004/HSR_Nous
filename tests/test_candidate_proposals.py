from __future__ import annotations

from dataclasses import replace
import json

import anyio
from mcp import ClientSession
from mcp.client.stdio import stdio_client
import pytest

from hsr_nous.research.protocol import CandidateGenerator, ProtocolValidationError
from hsr_nous.research.schema import (
    CandidateProposal,
    CandidateRule,
    CandidateSpace,
    ExperimentArm,
    canonical_json,
)
from tests._research_builders import (
    make_candidate_proposals,
    make_candidate_space,
    make_contract,
    make_patch,
)
from tests.test_research_mcp import _payload, _server_parameters


def test_candidate_space_round_trip_and_recursive_freezing():
    space = make_candidate_space()
    assert CandidateSpace.from_dict(space.to_dict()) == space
    with pytest.raises(TypeError):
        space.base_contract.budget["max_runs"] = 128
    with pytest.raises(ValueError, match="unknown fields"):
        CandidateProposal.from_dict({"path": ["base_stats", "atk"], "value": 1, "extra": 1})
    with pytest.raises(ValueError, match="paths must be unique"):
        CandidateSpace(space.base_contract, (space.rules[0], space.rules[0]))


def test_mechanism_proposals_materialize_only_declared_patch():
    base = make_candidate_space().base_contract
    hidden_variant = replace(
        base.experiment.variant,
        patches=(make_patch(value=900.0), make_patch(path=("values", 0), value=99.0)),
    )
    base = replace(base, experiment=replace(base.experiment, variant=hidden_variant))
    space = make_candidate_space(base_contract=base, values=(600, 550.0))
    proposals = make_candidate_proposals(space, values=(600.0, 550))

    plan = CandidateGenerator.build_candidate_set(space, proposals)

    assert [candidate.contract_id for candidate in plan.candidates] == ["candidate-0", "candidate-1"]
    for candidate, expected in zip(plan.candidates, (600.0, 550.0)):
        assert candidate.question == base.question
        assert candidate.experiment.build == base.experiment.build
        assert candidate.experiment.stage == base.experiment.stage
        assert candidate.experiment.baseline == base.experiment.baseline
        assert candidate.experiment.metric == base.experiment.metric
        assert candidate.budget == base.budget
        assert len(candidate.experiment.variant.patches) == 1
        patch = candidate.experiment.variant.patches[0]
        assert patch.path == ("base_stats", "atk")
        assert patch.value == expected and type(patch.value) is float
        assert candidate.experiment.variant.world == "hypothetical"
        assert candidate.experiment.variant.build_override is None


def test_configuration_proposals_change_only_the_allowed_path():
    space = make_candidate_space(configuration=True)
    proposals = make_candidate_proposals(space, labels=("cipher", "tingyun"))
    plan = CandidateGenerator.build_candidate_set(space, proposals)
    base = space.base_contract

    assert [candidate.contract_id for candidate in plan.candidates] == ["cipher", "tingyun"]
    for candidate, value in zip(plan.candidates, ("1406", "1202")):
        expected = json.loads(canonical_json(base.experiment.build))
        expected["build"]["team"][1]["character_template"] = value
        assert canonical_json(candidate.experiment.variant.build_override) == canonical_json(expected)
        assert candidate.experiment.build == base.experiment.build
        assert candidate.experiment.variant.world == "canonical"
        assert candidate.experiment.variant.patches == ()


def test_configuration_rejects_noop_bad_type_and_missing_path():
    baseline = make_candidate_space(configuration=True).base_contract.experiment.build
    original = baseline["build"]["team"][1]["character_template"]
    space = make_candidate_space(configuration=True, values=(original, "1202"))
    with pytest.raises(ProtocolValidationError, match="no-op"):
        CandidateGenerator.build_candidate_set(space, make_candidate_proposals(space))

    space = make_candidate_space(configuration=True, values=(1406, "1202"))
    with pytest.raises(ProtocolValidationError, match="type does not match"):
        CandidateGenerator.build_candidate_set(space, make_candidate_proposals(space))

    space = make_candidate_space(
        configuration=True, path=("build", "team", 9, "character_template")
    )
    with pytest.raises(ProtocolValidationError, match="path does not exist"):
        CandidateGenerator.build_candidate_set(space, make_candidate_proposals(space))

    space = make_candidate_space(
        configuration=True, path=("build", "team", 0, "level"), values=(81.0, 82)
    )
    with pytest.raises(ProtocolValidationError, match="type does not match"):
        CandidateGenerator.build_candidate_set(space, make_candidate_proposals(space))


def test_proposals_reject_duplicates_count_overflow_and_values_outside_rules():
    space = make_candidate_space()
    with pytest.raises(ProtocolValidationError, match="proposal count"):
        CandidateGenerator.build_candidate_set(space, make_candidate_proposals(space)[:1])
    with pytest.raises(ProtocolValidationError, match="duplicate proposal"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, values=(600, 600.0))
        )
    with pytest.raises(ProtocolValidationError, match="duplicate candidate label"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, labels=("same", "same"))
        )
    with pytest.raises(ProtocolValidationError, match="invalid candidate label"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, labels=("bad label", "other"))
        )
    with pytest.raises(ProtocolValidationError, match="outside the rule"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, values=(600.0, 999.0))
        )

    path = space.rules[0].path
    proposals = (CandidateProposal(("other",), 1), CandidateProposal(path, 550.0))
    with pytest.raises(ProtocolValidationError, match="path is not allowed"):
        CandidateGenerator.build_candidate_set(space, proposals)

    space = make_candidate_space(max_candidates=2)
    with pytest.raises(ProtocolValidationError, match="proposal count"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, values=(600.0, 550.0, 500.0))
        )


def test_proposals_enforce_rule_kind_and_total_budget():
    space = make_candidate_space(configuration=True)
    invalid_rule = CandidateRule(
        space.rules[0].path, space.rules[0].values, "characters", "1202"
    )
    with pytest.raises(ProtocolValidationError, match="cannot carry template"):
        CandidateGenerator.build_candidate_set(
            replace(space, rules=(invalid_rule,)), make_candidate_proposals(space)
        )

    space = make_candidate_space()
    invalid_rule = CandidateRule(space.rules[0].path, space.rules[0].values)
    with pytest.raises(ProtocolValidationError, match="require template identity"):
        CandidateGenerator.build_candidate_set(
            replace(space, rules=(invalid_rule,)), make_candidate_proposals(space)
        )

    base = replace(space.base_contract, budget={"max_runs": 512})
    space = make_candidate_space(base_contract=base)
    with pytest.raises(ProtocolValidationError, match="total run budget"):
        CandidateGenerator.build_candidate_set(
            space, make_candidate_proposals(space, values=(600.0, 550.0, 500.0))
        )


def test_configuration_path_with_repeated_component_is_not_truncated():
    path = ("group", "group", "value")
    build = {"group": {"group": {"value": "baseline"}}}
    base = make_contract(
        build=build,
        comparison_kind="configuration",
        variant=ExperimentArm(
            arm_id="variant", world="canonical", build_override=build
        ),
    )
    space = CandidateSpace(base, (CandidateRule(path, ("a", "b")),))
    plan = CandidateGenerator.build_candidate_set(
        space, make_candidate_proposals(space, values=("a", "b"))
    )
    assert [
        candidate.experiment.variant.build_override["group"]["group"]["value"]
        for candidate in plan.candidates
    ] == ["a", "b"]


def test_mcp_candidate_proposals_execute_and_reject_invalid_input(tmp_path):
    space = make_candidate_space(values=(600.0, 550.0))
    proposals = make_candidate_proposals(space)
    expected = CandidateGenerator.build_candidate_set(space, proposals)

    async def scenario():
        async with stdio_client(_server_parameters(tmp_path)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                assert "submit_candidate_proposals" in tools
                submitted = _payload(await session.call_tool(
                    "submit_candidate_proposals",
                    {
                        "candidate_space_json": canonical_json(space),
                        "candidate_proposals_json": canonical_json(proposals),
                    },
                ))
                assert submitted["status"] == "accepted"
                assert submitted["candidate_set_id"] == expected.candidate_set_id
                assert submitted["candidate_report_id"] == submitted["report"]["report_id"]
                assert len(submitted["report"]["candidates"]) == 2
                value = submitted["report"]["candidate_set"]["candidates"][0][
                    "experiment"
                ]["variant"]["patches"][0]["value"]
                assert value == 600.0 and type(value) is float

                invalid = _payload(await session.call_tool(
                    "submit_candidate_proposals",
                    {
                        "candidate_space_json": canonical_json(space),
                        "candidate_proposals_json": canonical_json(
                            make_candidate_proposals(space, values=(600.0, 999.0))
                        ),
                    },
                ))
                assert invalid["status"] == "rejected"
                assert invalid["error"]["code"] == "invalid_submission"

                malformed = _payload(await session.call_tool(
                    "submit_candidate_proposals",
                    {
                        "candidate_space_json": canonical_json(space),
                        "candidate_proposals_json": "{}",
                    },
                ))
                assert malformed["status"] == "rejected"

    anyio.run(scenario)
