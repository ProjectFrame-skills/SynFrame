# SynFrame

**English** · [한국어](README.ko.md) · [简体中文](README.zh.md)

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

**An AI skill that discovers missing knowledge, develops the understanding a goal needs, and combines tools and skills into executable solutions.**

SynFrame is designed to let the AI determine what it needs to learn and how deeply. It derives capabilities and questions from your goal, discovers further questions while learning, and carries the results back into the original solution. Learning has no fixed tree depth; sufficiently answered branches must end.

## Features

| Capability | What it does |
|---|---|
| Goal interpretation review | Separately examines support for the current interpretation and omission of material perspectives. |
| Recursive learning | Answers a question while pursuing necessary descendants without a preset depth. |
| Automation discovery | Searches beyond the installed inventory and compares existing and newly discovered tools and skills together. |
| Capability composition | Connects roles, inputs, outputs, prerequisites, compatibility, and complementary capabilities. |
| Contextual understanding | Determines K0–K4 from the questions needed for selection, application, failure handling, and verification. |
| Termination and propagation | Ends sufficient units and updates parent questions, candidates, and the original goal. |
| Review and recovery | Reviews exact candidate/evidence versions and preserves pending work and observations in SQLite. |

Recommendations lead with the best-supported combination for the current goal. They name the principal tools and skills, explain their verified functions and outputs, and distinguish alternatives from execution steps.

## Installation

### Codex

You need Python 3.11 or later and Git. The runtime helper uses only the Python standard library and SQLite.

```bash
git clone https://github.com/ProjectFrame-skills/SynFrame.git
cd SynFrame
python3 tools/install.py
```

The default destination is `${CODEX_HOME:-$HOME/.codex}/skills/synframe`. Invoke the skill in a new Codex conversation after installation. You can also choose an explicit destination:

```bash
python3 tools/install.py --destination /absolute/path/to/skills/synframe
```

An existing SynFrame installation is backed up before replacement. The command reports the installed location, backup location, and file hashes. It refuses to replace a different skill directory.

SynFrame requires no dedicated model API key or reasoning server. The host AI performs research, coding, and external tool work using its available tools and authority. Access required by a task-specific external service is separate.

## Usage

### Invoke explicitly

```text
$synframe I want to improve the app I'm building using other websites as references.
Research the necessary concepts and automation options, then recommend an approach for my project.
```

```text
$synframe Add subscriptions to this project.
Investigate how the reference product actually operates and assess payment, access control, and distribution together.
```

```text
$synframe Build a tool that totals payment CSVs by customer and currency.
Handle invalid input and verify the actual execution results.
```

You do not need to specify technology names, learning depth, or search counts. The current installation is verified for Codex skills. Automatic selection depends on the host configuration; explicit `$synframe` invocation is available.

These are README usage examples. They do not prescribe products, domains, or expected answers in the operating contracts.

### Resume saved work

```text
$synframe Restore run-… and continue.
The state directory is /absolute/project/path/.synframe.
Inspect the actual effects of pending work first.
```

State belongs in your project, outside the installed skill. Recovery checks the original goal, current versions, outstanding work, and actual external effects before continuing.

## How it works

```text
User goal ↔ Problem frames ↔ Required capabilities ↔ Information needs
                                                          ↕
                                                Discovery and learning
                                                          ↕
                                            Follow-up questions and children
                                                          ↕
                                     Composition ↔ Review ↔ Execution/validation

                  Results propagate back to parents and the original goal
```

This diagram shows information relationships. It is not a fixed pipeline that runs every module on every operation.

The **host AI** is the single logical Meta-Controller. It judges meaning, research direction, alternatives, understanding, sufficiency, and termination. The **deterministic core** manages schemas, references, dependencies, versions, invalidation, transactions, recovery, and Commit checks. Passing a structural check does not establish the truth of a semantic claim or satisfaction of the user's goal.

## Execution efficiency

- Bundle independently needed schemas without omitting their contents.
- Reuse exact objects and receipts returned by observation preservation.
- Remove formatting whitespace from machine JSON while retaining every value and source string.
- Share a coherent database snapshot within each Review/Gate query.
- Hash complete files in chunks to bound memory use.

Required contracts are not summarized away. Learning depth is not capped, and K/PASS/termination judgments are not generated automatically. Improvements in whole-answer latency and token cost have not yet been established through independent runs.

## Advanced usage

Ordinary users do not need to author state JSON. Integrations can query the actual serialization contracts:

```bash
python3 skills/synframe/scripts/synframe.py schema --entities Frame SolutionCandidate
python3 skills/synframe/scripts/synframe.py schema --for-command transition
python3 skills/synframe/scripts/synframe.py --compact schema --entity LearningTask
```

See the [execution interface](skills/synframe/references/execution-interface.md) for formats, versions, and state boundaries. CLI `solve` registers a run; it does not launch an LLM. The host continues with actual judgments and tool work.

## Development and validation

```bash
python3 -m unittest discover -s tests -v
python3 tools/verify.py
```

Tests cover state, references, graphs, idempotency, errors, recovery, Gate, and CLI behavior. Prewritten fixture judgments are not evidence of autonomous reasoning quality. Keep source and installation identical and validate calls against the installed skill after changes.

```text
skills/synframe/     Skill entrypoint, full operating contracts, and helper code
tests/              Reproducible runtime checks
tools/install.py    Installer that preserves previous versions
tools/verify.py     Recorded verification results
```

This repository distributes the implementation and usage documentation. Personal conversations, original execution databases, and local audit history are excluded.

## Troubleshooting

- **Skill not visible:** Check the installation path and `SKILL.md`, then invoke it explicitly in a new conversation.
- **A saved run has a different identity:** Do not edit recorded hashes. Use the matching archived installation or a linked follow-up run with explicit reassessment. Installation backups preserve the original code.
- **Input rejected:** Inspect the current schema and reported field/type. Avoid guessing field names or attaching a newer revision number to an old Review.
- **Work takes too long:** Distinguish necessary research from repeated retrieval of the same information. End sufficient units while preserving important gaps and follow-up obligations.

The README structure draws on the [UI UX Pro Max Korean README](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/README.ko.md). Capabilities and installation instructions describe SynFrame's own implementation.
