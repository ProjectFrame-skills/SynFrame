# SynFrame — 知识探索与理解 · 工具与 skill 的组合 · 解决方案探索

[English](README.md) · [한국어](README.ko.md) · **简体中文**

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

## 所需软件

| 软件 | 何时需要 |
|---|---|
| Codex 应用或 CLI | 运行 `$synframe` 的 AI 宿主，需要支持 skills、本地文件访问和 Python 执行权限。仅安装 npm 包不会提供 AI 宿主。 |
| [Python 3.11+](https://www.python.org/downloads/) | 安装及状态保存/恢复始终需要。SynFrame 还需要 Python 的 [sqlite3](https://docs.python.org/3/library/sqlite3.html) 模块，通常随 Python 提供，无需单独安装 SQLite 服务器或命令行程序。 |
| [Node.js 18+](https://nodejs.org/en/download)，含 npm | 使用 npm 安装或 `synframe` 命令时需要。建议选择仍受支持的 Node.js LTS 版本；npm 通常随 Node.js 安装。 |

**所需软件：** Codex + Node.js/npm + Python。

安装前可检查所需软件：

```bash
node --version
npm --version
python3 --version
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

Windows 上如使用 `python` 或 `py -3`，请替换相应命令。`SYNFRAME_PYTHON` 只选择已有的 Python 可执行文件，不负责安装 Python。其他 AI 宿主需要兼容的 skill 支持与本地执行能力。任务所需的额外工具和服务权限取决于具体目标，不属于通用前置条件。

### Python 自动查找与安装错误

npm CLI 先检查 PATH 中的 `python3`/`python`（Windows 还检查 `py -3`）。macOS/Linux 上如无法运行 Python 3.11+，会检查 Homebrew 默认位置、`brew --prefix` 返回的位置及已安装的 `python@…`。Homebrew 不是必需项；CLI 不会安装 Python 或修改 PATH。

`SYNFRAME_PYTHON` 显式指定一个可执行文件。路径或版本不正确时会报错，不会悄悄改用其他 Python。错误区分文件不存在、版本过旧、权限拒绝、Python 检查失败/超时，以及安装程序失败，并提供失败检查与下一步提示。

全局 CLI 安装后，必要时可指定已确认的 Python 路径：

```bash
SYNFRAME_PYTHON="/absolute/path/to/python3" synframe install
```

## 🚀 通过 npm 全局安装

```bash
npm install -g synframe-cli@latest
synframe install
```

第一条命令安装全局 CLI，第二条命令安装实际 skill。可用 `synframe --version` 检查 CLI。

需要 Node.js 18+ 和 Python 3.11+。安装后在新的 Codex 对话中调用 `$synframe`。

**一个连接所需知识与工具，引导用户更容易接近目标结果的 AI skill。**

SynFrame 从用户目标出发，探索并说明**需要哪些知识、应该使用哪些工具和 skill，以及如何组合并应用它们，更容易获得期望的结果。**

AI 会主动探索并理解必要知识，评估工具与 skill 的组合，将它们连接成可执行的解决路径。研究中发现的后续问题会继续探索，新知识会反馈到原始目标与解决方案。学习树没有预设深度；已有充分依据的分支必须结束。

## 主要功能

| 功能 | 作用 |
|---|---|
| 目标理解审查 | 分别检查当前理解的依据，以及是否遗漏重要视角。 |
| 递归学习 | 在回答当前问题的同时发现并处理必要的子问题，不预设深度。 |
| 自动化发现 | 即使已有工具，也探索新方法，并统一比较现有与新发现的工具和 skill。 |
| 能力组合 | 连接角色、输入输出、前提、兼容条件和互补能力，而非只罗列工具名。 |
| 情境化理解 | 根据选择、应用、故障和验证所需回答的问题判断 K0–K4。 |
| 结束与向上反馈 | 结束已充分解决的单元，将结果用于更新父问题、候选方案和原始目标。 |
| 审查与恢复 | 审查准确的候选及证据版本，将未完成工作和观察保存在 SQLite 中。 |

建议优先呈现当前目标下依据最充分的组合，直接说明主要工具与 skill 的名称、已确认功能、产出及衔接，并区分备选方案和执行顺序。

## 安装

### Codex

请使用上方 npm 全局安装命令。CLI 不依赖其他 npm 包；运行辅助代码只使用 Python 标准库和 SQLite。

默认安装位置为 `${CODEX_HOME:-$HOME/.codex}/skills/synframe`。安装后在新的 Codex 对话中调用，也可显式指定路径：

```bash
synframe install --destination /absolute/path/to/skills/synframe
```

替换前会备份已有的 SynFrame 安装。命令会报告安装位置、备份位置及文件 hash，并拒绝覆盖其他 skill 目录。

SynFrame 不需要专用模型 API key 或推理服务器。研究、编码和外部工具操作由宿主 AI 使用自己的工具及权限完成。具体任务所需外部服务的访问权限另行适用。

## 使用方法

### 来自真实对话的使用示例

以下示例根据用户的真实请求及讨论方向整理，展示如何从目标连接到知识、工具与解决路径，而非特定产品的固定答案。

#### 1. 将参考网站转化为应用设计改进

```text
$synframe 我想参考其他网站的设计，改善正在开发的应用。
请调查应该如何进行。
```

**讨论过的连接：** 发现设计 token 与设计系统视角 → 评估通过 Dembrandt 提取参考信息 → 与 UI/UX Pro Max 组合，整理设计规则与应用条件 → 评估如何迁移到目标应用并审查结果。

**用户得到的内容：** 说明提取什么、如何整理、怎样连接到应用的建议，而不仅是工具名称列表。

#### 2. 为正在开发的 skill 增加订阅和付费功能

```text
$synframe 我想为正在开发的 skills 增加收费功能，
以后新增的功能只对付费用户开放。应该如何实现？
```

**讨论过的探索方向：** 调查参考产品实际的支付、分发与权限机制 → 比较支付手段和授权验证的组合 → 检查功能限制位置、衔接前提与绕过风险 → 推导适合项目的实现及验证路径。

**用户得到的内容：** 从支付到实际功能访问的完整连接，以及实现所需的判断。

#### 3. 在不损失功能的前提下改善回答速度

```text
$synframe 请评估不损失功能的优化机会，
并只提取可实现的方案。
```

**讨论过的连接：** 检查重复查询、序列化及错误重试成本 → 排除削减学习、发现或验证的方案 → 考虑独立查询合并、准确返回对象复用及机器 JSON 精简 → 确认状态、证据与恢复责任保留。

**用户得到的内容：** 区分可减少的机械成本与必须保留判断的可应用候选。

无需预先指定技术名称、学习深度或搜索次数。自动选择取决于宿主配置，也可显式调用 `$synframe`。这些案例仅保留为 README 使用说明，不会加载为 skill 的运行条件。

### 恢复已保存的工作

```text
$synframe 恢复 run-… 并继续。
状态路径为 /absolute/project/path/.synframe。
请先确认未完成工作的实际效果。
```

状态保存在用户项目中，不放在已安装的 skill 目录内。恢复时会先核对原始目标、当前版本、剩余工作及实际外部效果，再继续执行。

## 工作结构

```text
用户目标 ↔ 问题视角 ↔ 所需能力 ↔ 信息需求
                                   ↕
                              发现与深入学习
                                   ↕
                            后续问题及子问题学习
                                   ↕
                       工具组合 ↔ 审查 ↔ 执行与验证

              学习结果向上反馈，更新父问题和原始目标
```

图中表示信息关系，而非每次都必须运行所有模块的固定流水线。

**宿主 AI** 是唯一的逻辑 Meta-Controller，负责语义理解、探索方向、方案比较、学习充分性及结束判断。**确定性核心** 负责 schema、引用、依赖、版本、失效传播、事务、恢复和 Commit 检查。结构检查通过不能证明语义事实为真，也不能代替用户目标完成验证。

## 执行效率

- 将同时需要的独立 schema 完整地合并查询。
- 复用观察保存操作返回的准确对象和 receipt。
- 机器 JSON 仅移除格式空白，保留全部值和原文字符串。
- Review 与 Gate 在单次查询中共享一致的数据库 snapshot。
- 分块读取完整文件来计算 hash，限制内存占用。

不会用摘要替代必读契约，不会限制学习深度，也不会自动生成 K、PASS 或结束判断。整体回答时间和 token 成本的改善幅度尚未通过独立运行确认。

## 高级用法

普通用户无需手写状态 JSON。集成辅助代码时，可以查询实际序列化格式：

```bash
python3 skills/synframe/scripts/synframe.py schema --entities Frame SolutionCandidate
python3 skills/synframe/scripts/synframe.py schema --for-command transition
python3 skills/synframe/scripts/synframe.py --compact schema --entity LearningTask
```

格式、版本及状态边界见[执行接口](skills/synframe/references/execution-interface.md)。CLI 的 `solve` 只注册运行，不会自行启动 LLM；实际判断与工具操作由宿主继续执行。

## 开发与验证

```bash
python3 -m unittest discover -s tests -v
python3 tools/verify.py
```

测试涵盖状态、引用、图、幂等性、错误、恢复、Gate 和 CLI。fixture 中预先编写的判断不代表自主推理质量。修改后应保持源码与安装版本一致，并调用实际安装版本验证。

```text
skills/synframe/     skill 入口、完整运行契约及辅助代码
tests/              可复现的运行检查
tools/install.py    保留旧版本备份的安装工具
tools/verify.py     验证结果记录
```

本仓库发布实现及使用文档，不包含个人对话、原始执行数据库或本地审计历史。

## 常见问题

- **找不到 skill：** 检查安装路径与 `SKILL.md`，然后在新对话中显式调用。
- **旧运行的 identity 不一致：** 不要修改记录中的 hash。请使用匹配的历史安装版本，或在明确关联的后续运行中重新评估。安装备份保留原代码。
- **输入被拒绝：** 检查当前 schema 和错误中的字段位置、所需类型。不要猜测字段名，也不要给旧 Review 换上最新版本号。
- **执行时间较长：** 区分必要学习与相同资料的重复查询。充分解决的单元应结束，但重要缺口与后续义务不能省略。

README 的结构参考了 [UI UX Pro Max 韩文 README](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/README.ko.md)，功能及安装说明依据 SynFrame 自身实现编写。
