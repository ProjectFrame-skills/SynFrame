# SynFrame — Knowledge Discovery & Understanding · Tool & Skill Composition · Solution Exploration

**English** · [한국어](README.ko.md) · [简体中文](README.zh.md)

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

## Prerequisites

| Program | When it is required |
|---|---|
| Codex app or CLI | The AI host that runs `$synframe`, with skills, local file access, and permission to execute Python. Installing the npm package alone does not provide an AI host. |
| [Python 3.11+](https://www.python.org/downloads/) | Required for installation and the state/recovery helper. SynFrame also requires Python's [sqlite3](https://docs.python.org/3/library/sqlite3.html) module; it is normally included in Python distributions, so a separate SQLite server or command-line program is unnecessary. |
| [Node.js 18+](https://nodejs.org/en/download), with npm | Required for the npm installation route and the `synframe` command. Use a currently supported Node.js LTS release. npm is normally included with Node.js. |

**Required:** Codex + Node.js/npm + Python.

Check the required programs before installation:

```bash
node --version
npm --version
python3 --version
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

On Windows, use `python` or `py -3` if that is your Python command. `SYNFRAME_PYTHON` selects an existing Python executable; it does not install Python. Other AI hosts need compatible skill support and local execution. Additional tools or service access depend on the actual goal and are not universal prerequisites.

### Python discovery and installation errors

The npm CLI first uses `python3`/`python` on PATH (`py -3` on Windows). On macOS/Linux, if those cannot run Python 3.11+, it checks Homebrew's standard prefixes and `brew --prefix`, including installed `python@…` formulae. Homebrew is optional; the CLI does not install Python or edit PATH.

`SYNFRAME_PYTHON` explicitly selects one executable. If set, a bad path or version is reported instead of silently selecting another Python. Errors distinguish a missing executable, an old version, permission denial, a failed/timed-out Python check, and an installer failure. An error lists the failed Python checks and the next step.

After installing the global CLI, select a known Python directly if necessary:

```bash
SYNFRAME_PYTHON="/absolute/path/to/python3" synframe install
```

## 🚀 Global installation with npm

```bash
npm install -g synframe-cli@latest
synframe install
```

The first command installs the global CLI; the second installs the actual skill. Check the CLI with `synframe --version`.

Requires Node.js 18+ and Python 3.11+. Invoke `$synframe` in a new Codex conversation after installation.

**An AI skill that connects the knowledge and tools you need and guides you toward an easier path to your desired result.**

SynFrame starts from your goal to explore and explain **what knowledge you need, which tools and skills to use, and how to combine and apply them to reach your desired result more easily.**

The AI researches and understands the necessary knowledge, evaluates tool and skill combinations, and connects them into executable solution paths. It pursues follow-up questions discovered during research and carries new knowledge back into the original goal and solution. Learning has no fixed tree depth; sufficiently answered branches must end.

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

Use the global npm installation commands above. The CLI has no npm dependencies; the runtime helper uses only the Python standard library and SQLite.

The default destination is `${CODEX_HOME:-$HOME/.codex}/skills/synframe`. Invoke the skill in a new Codex conversation after installation. You can also choose an explicit destination:

```bash
synframe install --destination /absolute/path/to/skills/synframe
```

An existing SynFrame installation is backed up before replacement. The command reports the installed location, backup location, and file hashes. It refuses to replace a different skill directory.

SynFrame requires no dedicated model API key or reasoning server. The host AI performs research, coding, and external tool work using its available tools and authority. Access required by a task-specific external service is separate.

## Update

```bash
synframe update
```

Updates the global CLI to the latest published npm version, then runs that version's installer to update the actual skill. Use a new Codex conversation afterward. Keep the same `CODEX_HOME`; if you originally chose explicit paths, pass the same `--destination` options to `update`. Custom paths are not remembered automatically.

If your older CLI does not recognize `update`, run the two global installation commands above once. If npm succeeds but skill installation fails, fix the reported problem and run `synframe install` with the same path options.

## Usage

### Examples adapted from real conversations

These examples summarize the user's actual requests and the directions discussed. They illustrate how a goal connects to knowledge, tools, and a solution path; they are not fixed product-specific answers.

#### 1. Turn reference websites into improvements for an app

```text
$synframe I want to improve the app I'm building using other websites as design references.
Investigate how I should approach it.
```

**Connections discussed:** discover the design-token and design-system perspective → assess reference extraction with Dembrandt → combine it with UI/UX Pro Max to define design rules and application conditions → assess transfer into the target app and review the result.

**What the user gets:** a recommendation that explains what to extract, how to organize it, and how to apply it, beyond a list of tool names.

#### 2. Add subscriptions and paid features to a skill

```text
$synframe I want to add billing to the skills I'm building,
and unlock future features only for paying users. How can I do it?
```

**Exploration discussed:** investigate the reference product's actual payment, distribution, and access model → compare payment and authorization combinations → examine enforcement boundaries, connection requirements, and bypass risks → derive a project-specific implementation and validation path.

**What the user gets:** the connections from payment to actual feature access, together with the decisions needed to make them work.

#### 3. Improve response speed without losing functionality

```text
$synframe Investigate optimization opportunities without functional losses,
and extract only feasible options.
```

**Connections discussed:** inspect repeated retrieval, serialization, and error-retry costs → exclude reductions in learning, discovery, or validation → consider independent query bundles, exact returned-object reuse, and compact machine JSON → verify preservation of state, evidence, and recovery responsibilities.

**What the user gets:** actionable candidates that distinguish reducible mechanical costs from necessary judgments.

Technology names, learning depth, and search counts need not be specified in advance. Automatic selection depends on the host configuration; explicit `$synframe` invocation is available. These examples remain README usage material and are not loaded as operating conditions.

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
