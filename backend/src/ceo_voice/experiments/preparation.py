"""Seeded and reproducible baseline-paired reviewer ballot preparation."""

import json
import random
from uuid import uuid5

from .contracts import Assignment, Ballot, BallotExport, ExperimentManifest, PrivateKey


def prepare(manifest: ExperimentManifest) -> tuple[BallotExport, PrivateKey]:
    """Blind actual supplied outputs; keep arm assignments in a separate private artifact."""

    manifest = ExperimentManifest.model_validate(manifest.model_dump())
    rng = random.Random(manifest.seed)
    fingerprint = manifest.fingerprint()
    ballots: list[Ballot] = []
    assignments: list[Assignment] = []
    for case in manifest.cases:
        for arm in manifest.arms:
            if arm == manifest.baseline_arm:
                continue
            arms = [manifest.baseline_arm, arm]
            rng.shuffle(arms)
            ballot_id = uuid5(manifest.experiment_id, json.dumps([fingerprint, case.case_id, arm]))
            assignments.append(
                Assignment(ballot_id=ballot_id, case_id=case.case_id, arm_a=arms[0], arm_b=arms[1])
            )
            ballots.append(
                Ballot(
                    ballot_id=ballot_id,
                    author_id=case.author_id,
                    platform=case.platform,
                    brief=case.brief,
                    candidate_a=case.outputs[arms[0]],
                    candidate_b=case.outputs[arms[1]],
                    dimensions=manifest.dimensions,
                )
            )
    rng.shuffle(ballots)
    return (
        BallotExport(
            experiment_id=manifest.experiment_id,
            manifest_sha256=fingerprint,
            synthetic=manifest.synthetic,
            ballots=tuple(ballots),
        ),
        PrivateKey(
            experiment_id=manifest.experiment_id,
            manifest_sha256=fingerprint,
            assignments=tuple(assignments),
        ),
    )
