# Synthetic experiment fixture

These fictional sources and candidate drafts were manually authored to exercise the experiment harness. Arm labels describe intended study conditions; no model executed those conditions. There are no human ratings or model-quality results.

The four source hashes in `synthetic-study.json` are SHA-256 over these exact UTF-8 strings (without a trailing newline):

- `source-0`: Synthetic training example: State the result. Explain what changed. Thank the team.

- `source-1`: Synthetic held-out example one: We shortened the queue. People waited less. Next, we improve routing.

- `source-2`: Synthetic held-out example two: Reliability starts with small promises. Keep one promise, then the next.

- `source-3`: Synthetic held-out example three: A useful review tells us what to change. Specific feedback beats applause.

Use the commands in [the experiment guide](../../../docs/experiments.md) to prepare blinded ballots and an empty ratings template. A real study must supply actual candidate outputs, verified source metadata, and real reviewer decisions.
