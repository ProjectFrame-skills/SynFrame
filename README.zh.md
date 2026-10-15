# SynFrame

[English](README.md) · [한국어](README.ko.md) · **简体中文**

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

**一个发现所缺知识、确定所需理解深度，并组合工具和 skill 来形成可执行方案的 AI skill。**

SynFrame 让 AI 自主判断需要学习什么、学到什么程度。它从用户目标推导所需能力与问题，在学习中发现后续探索空间，并将结果反馈到原始目标与解决方案。学习树没有预设深度；已有充分依据的分支必须结束。

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

需要 Python 3.11 或更高版本及 Git。运行辅助代码只使用 Python 标准库和 SQLite。

```bash
git clone https://github.com/ProjectFrame-skills/SynFrame.git
cd SynFrame
python3 tools/install.py
```

默认安装位置为 `${CODEX_HOME:-$HOME/.codex}/skills/synframe`。安装后在新的 Codex 对话中调用，也可显式指定路径：

```bash
python3 tools/install.py --destination /absolute/path/to/skills/synframe
```

替换前会备份已有的 SynFrame 安装。命令会报告安装位置、备份位置及文件 hash，并拒绝覆盖其他 skill 目录。

SynFrame 不需要专用模型 API key 或推理服务器。研究、编码和外部工具操作由宿主 AI 使用自己的工具及权限完成。具体任务所需外部服务的访问权限另行适用。

## 使用方法

### 显式调用

```text
$synframe 我想参考其他网站，改善正在开发的应用设计。
请研究必要概念和自动化手段，并推荐适合当前项目的方法。
```

```text
$synframe 为当前项目增加订阅功能。
请调查参考产品的实际运营方式，并一起评估支付、权限和分发的衔接。
```

```text
$synframe 创建一个按客户和币种汇总支付 CSV 的工具。
请处理无效输入，并验证实际执行结果。
```

无需预先指定技术名称、学习深度或搜索次数。当前安装针对 Codex skill 格式进行验证。自动选择取决于宿主配置，也可使用明确的 `$synframe` 调用。

以上只是 README 使用示例，不会把特定领域、产品或预期答案作为运行契约中的固定要求。

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
