# SynFrame — 지식 탐색 및 이해 · 도구와 skill의 조합 · 해결책 탐색

[English](README.md) · **한국어** · [简体中文](README.zh.md)

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

## 필수 프로그램

| 프로그램 | 필요한 경우 |
|---|---|
| Codex 앱 또는 CLI | `$synframe`을 실행할 AI 호스트입니다. skills·로컬 파일 접근·Python 실행 권한이 필요하며, npm 패키지만 설치한다고 AI 호스트가 제공되는 것은 아닙니다. |
| [Python 3.11 이상](https://www.python.org/downloads/) | 설치와 상태 저장·복구에 항상 필요합니다. SynFrame은 Python의 [sqlite3](https://docs.python.org/3/library/sqlite3.html) 모듈도 사용합니다. 보통 Python에 포함되어 있으므로 별도 SQLite 서버나 명령행 프로그램을 설치할 필요는 없습니다. |
| [Node.js 18 이상](https://nodejs.org/en/download) + npm | npm 방식으로 전역 설치하거나 `synframe` 명령을 쓸 때 필요합니다. 현재 지원되는 Node.js LTS 버전을 권장하며, npm은 보통 Node.js와 함께 설치됩니다. |

**필수 프로그램:** Codex + Node.js/npm + Python.

npm 설치 전에 다음 명령으로 확인할 수 있습니다.

```bash
node --version
npm --version
python3 --version
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

Windows에서 Python 명령이 `python` 또는 `py -3`라면 해당 명령을 사용하세요. `SYNFRAME_PYTHON`은 이미 설치된 Python 실행 파일을 선택하며 Python을 설치해 주지는 않습니다. 다른 AI 호스트는 호환되는 skill 지원과 로컬 실행 기능이 필요합니다. 작업별 추가 도구·서비스 권한은 실제 목표에 따라 달라지며 공통 필수 프로그램은 아닙니다.

### Python 자동 탐색과 설치 오류

npm CLI는 먼저 PATH의 `python3`·`python`을 확인합니다(Windows는 `py -3`도 확인). macOS/Linux에서 Python 3.11 이상을 실행하지 못하면 Homebrew 기본 경로와 `brew --prefix`의 경로, 설치된 `python@…`도 탐색합니다. Homebrew는 선택사항이며 Python을 자동 설치하거나 PATH를 수정하지 않습니다.

`SYNFRAME_PYTHON`으로 실행 파일을 지정하면 해당 파일만 사용합니다. 경로·버전이 잘못돼도 다른 Python으로 조용히 바꾸지 않습니다. 오류는 실행 파일 없음·버전 부족·권한 거부·Python 검사 실패/시간 초과·설치 프로그램 실패를 구분하고, 실패한 검사와 다음 조치를 안내합니다.

전역 CLI 설치 후 필요하면 확인한 Python 경로를 직접 지정할 수 있습니다.

```bash
SYNFRAME_PYTHON="/absolute/path/to/python3" synframe install
```

## 🚀 npm으로 전역 설치

```bash
npm install -g synframe-cli@latest
synframe install
```

첫 명령은 전역 CLI를, 두 번째 명령은 실제 skill을 설치합니다. `synframe --version`으로 CLI 설치를 확인할 수 있습니다.

Node.js 18 이상과 Python 3.11 이상이 필요합니다. 설치 후 새 Codex 대화에서 `$synframe`을 호출하세요.

**필요한 지식과 도구를 찾아 연결하고, 원하는 결과에 더 쉽게 다가가도록 안내하는 AI skill.**

SynFrame은 사용자의 목표를 바탕으로 **어떤 지식이 필요한지, 어떤 도구와 skill을 활용해야 하는지, 어떻게 조합하고 실행하면 원하는 결과에 더 쉽게 도달할 수 있는지**를 탐색하고 안내하도록 설계됐습니다.

이를 위해 AI가 필요한 지식을 직접 탐색하고 이해하며, 도구와 skill의 조합을 검토해 실행 가능한 해결 경로로 연결합니다. 조사 중 발견한 후속 질문을 탐색하고, 새 지식을 원래 목표와 해결책에 반영합니다. 학습의 깊이는 고정하지 않고, 필요한 근거가 충분해진 가지는 종료합니다.

## 주요 기능

| 기능 | 하는 일 |
|---|---|
| 목표 해석 검토 | 현재 해석의 근거와 중요한 관점 누락을 별도로 확인합니다. |
| 재귀 학습 | 답을 얻는 동시에 후속 질문을 발견하고, 필요한 자식 질문을 깊이 제한 없이 이어갑니다. |
| 자동화 수단 탐색 | 기존 도구가 있어도 새로운 수단을 탐색하고, 기존·신규 도구와 skill을 함께 비교합니다. |
| 기능 중심 조합 | 이름 나열을 넘어 역할·입출력·전제·호환성·상호보완성을 연결합니다. |
| 맥락별 이해 수준 | 선택·적용·실패·검증에 필요한 질문을 기준으로 K0–K4를 판단합니다. |
| 학습 종료와 상향 반영 | 충분한 가지는 끝내고, 결과가 부모 질문·후보·원래 목표를 갱신하게 합니다. |
| 검토와 상태 복구 | 정확한 후보·근거 버전을 검토하고, 미완료 작업과 관측을 SQLite에 보존합니다. |

추천은 현재 목표에서 가장 근거가 충분한 조합을 먼저 설명합니다. 주요 도구·skill의 실제 이름, 확인된 기능, 산출물과 연결을 명시하며 대안과 실행 순서를 구분합니다.

## 설치

### Codex

위의 npm 전역 설치 명령을 사용하세요. CLI는 추가 npm 의존성이 없고, 실행 보조 코드는 Python 표준 라이브러리와 SQLite만 사용합니다.

기본 설치 위치는 `${CODEX_HOME:-$HOME/.codex}/skills/synframe`입니다. 설치 후 새 Codex 대화에서 skill을 호출하세요. 설치 경로를 직접 지정할 수도 있습니다.

```bash
synframe install --destination /absolute/path/to/skills/synframe
```

기존 SynFrame 설치는 교체 전에 별도 백업합니다. 설치 명령의 결과에서 설치 경로, 백업 경로, 파일 hash를 확인할 수 있습니다. 다른 skill 폴더에는 설치하지 않습니다.

SynFrame 전용 모델 API 키나 추론 서버는 필요하지 않습니다. 실제 검색·코딩·외부 도구 사용은 호스트 AI가 자신의 도구와 권한으로 수행합니다. 특정 작업에 필요한 외부 서비스의 접근 권한은 별개입니다.

## 업데이트

```bash
synframe update
```

최신 npm 버전으로 전역 CLI를 갱신한 뒤, 새 버전의 설치 도구로 실제 skill도 갱신합니다. 이후 새 Codex 대화에서 사용하세요. 기존과 같은 `CODEX_HOME`을 사용하고, 설치 경로를 직접 지정했다면 `update`에도 같은 `--destination` 옵션을 넘기세요. 사용자 지정 경로를 자동으로 기억하지는 않습니다.

이전 CLI에서 `update`를 인식하지 못하면 위의 전역 설치 명령 두 개를 한 번 실행하세요. npm 갱신 후 skill 설치만 실패했다면 안내된 문제를 해결하고 같은 경로 옵션으로 `synframe install`을 실행하세요.

## 사용법

### 실제 대화에서 가져온 사용 예시

아래는 사용자의 실제 요청과 논의한 방향을 요약해 재구성한 예시입니다. 제품별 고정 정답이 아니라 목표에서 지식·도구·해결 경로를 연결하는 모습을 보여 줍니다.

#### 1. 참고 웹사이트를 내 앱의 디자인으로 연결

```text
$synframe 다른 웹사이트의 디자인을 참고해서 지금 만들고 있는 앱의 디자인을 개선하고 싶어.
어떤 방법으로 진행하는 게 좋을지 알아봐줘.
```

**대화에서 검토한 연결:** 디자인 토큰·디자인 시스템이라는 관점 발견 → Dembrandt를 통한 참조 사이트 정보 추출 검토 → UI/UX Pro Max와 조합해 디자인 규칙·적용 조건 정리 → 대상 앱에 옮길 방법과 결과 검토.

**사용자가 얻는 것:** 도구 이름의 나열을 넘어, 무엇을 추출하고 어떤 규칙으로 정리하며 어떻게 앱에 연결할지 보여 주는 추천안.

#### 2. 만들고 있는 skill에 구독·유료 기능 추가

```text
$synframe 지금 만들고 있는 skills에 과금 기능을 넣고,
나중에 추가될 기능은 결제했을 때만 열어주고 싶어. 어떻게 할 수 있어?
```

**논의한 탐색 방향:** 참고 제품의 실제 결제·배포·권한 운영 조사 → 결제 수단과 접근 권한 검증의 조합 비교 → 기능 잠금 위치·연결 전제·우회 가능성 검토 → 프로젝트에 맞는 구현·검증 경로.

**사용자가 얻는 것:** 결제 서비스 하나의 이름보다, 결제 이후 실제 기능 접근까지 이어지는 구조와 필요한 판단.

#### 3. 기능을 잃지 않고 응답 속도 개선

```text
$synframe 기능적 손해가 없는 방향으로 최적화 가능성을 검토하고,
실현 가능한 것만 추려줘.
```

**대화에서 검토한 연결:** 반복 조회·직렬화·오류 재시도 비용 확인 → 학습·탐색·검증을 줄이는 방안 제외 → 독립 조회 묶음·정확한 반환 객체 재사용·기계 JSON 정리 → 기존 상태·근거·복구 책임 유지 확인.

**사용자가 얻는 것:** 줄여도 되는 기계적 비용과 유지해야 할 판단을 구분한 적용 후보.

기술 이름·학습 깊이·검색 횟수를 미리 지정할 필요가 없습니다. 자동 선택은 호스트 설정에 따르며, `$synframe`으로 명시적으로 호출할 수 있습니다. 이 사례는 README 사용법에만 남고 skill의 운영 조건으로 로딩되지 않습니다.

### 저장된 작업 이어가기

```text
$synframe run-…를 복원해 계속해줘.
상태 경로는 /absolute/project/path/.synframe 이야.
미완료 작업의 실제 효과부터 확인해줘.
```

상태는 사용자의 프로젝트에 보관하며 설치된 skill 폴더 안에 저장하지 않습니다. 중단 후에는 원래 목표·현재 버전·남은 작업·실제 외부 효과를 확인한 뒤 재개합니다.

## 작동 구조

```text
사용자 목표 ↔ 문제 관점 ↔ 필요한 기능 ↔ 정보 요구
                                      ↕
                                 발견·심화 학습
                                      ↕
                              후속 질문과 자식 학습
                                      ↕
                        도구 조합 ↔ 검토 ↔ 실행·검증

       학습 결과는 부모 질문과 원래 목표까지 거슬러 올라가 반영
```

이 그림은 정보의 연결을 나타냅니다. 모든 단계를 매번 실행하는 고정 파이프라인은 아닙니다.

**호스트 AI**가 하나의 논리적 Meta-Controller로 의미 해석·탐색·비교·학습 충분성·종료를 판단합니다. **결정론적 코어**는 스키마·참조·의존 관계·버전·무효화·트랜잭션·복구와 Commit 검사를 담당합니다. 구조 검사 통과는 의미적 사실의 진실이나 사용자 목표 달성의 증명이 아닙니다.

## 실행 비용 최적화

- 함께 필요한 독립 schema를 전체 내용 그대로 묶어 조회합니다.
- 관측 보존이 반환한 정확한 객체와 receipt를 재사용합니다.
- 기계용 JSON은 불필요한 공백만 제거하고 모든 값과 원문을 유지합니다.
- Review·Gate는 한 조회 안의 일관된 DB snapshot을 공유합니다.
- 파일 hash는 전체 바이트를 나누어 읽어 메모리 사용을 제한합니다.

필수 계약 요약, 탐색 깊이 제한, K·PASS·종료의 자동 승인은 하지 않습니다. 전체 답변 시간과 토큰 비용의 개선 폭은 아직 독립 실행으로 확정하지 않았습니다.

## 고급 사용

일반 사용자는 상태 JSON을 직접 작성할 필요가 없습니다. 보조 코드와 연동할 때는 실제 형식을 조회합니다.

```bash
python3 skills/synframe/scripts/synframe.py schema --entities Frame SolutionCandidate
python3 skills/synframe/scripts/synframe.py schema --for-command transition
python3 skills/synframe/scripts/synframe.py --compact schema --entity LearningTask
```

형식·버전·상태 계약은 [실행 인터페이스](skills/synframe/references/execution-interface.md)에 있습니다. `solve`는 실행을 등록하며 모델을 자동 실행하지 않습니다. 호스트가 실제 판단과 도구 작업을 이어갑니다.

## 개발 및 검증

```bash
python3 -m unittest discover -s tests -v
python3 tools/verify.py
```

검사는 상태·참조·그래프·중복 적용·오류·복구·Gate와 CLI를 다룹니다. 예제 fixture의 사전 작성된 판단을 자율 추론 품질의 증거로 간주하지 않습니다. 변경 시 source와 설치본을 일치시키고 실제 설치본을 호출해 확인하세요.

```text
skills/synframe/     skill 진입점·전체 운영 계약·보조 코드
tests/              재현 가능한 실행 검사
tools/install.py    백업을 보존하는 설치
tools/verify.py     검증 결과 기록
```

이 저장소는 구현체와 사용 문서를 배포합니다. 개인 대화·원본 실행 DB·로컬 분석 이력은 포함하지 않습니다.

## 문제 해결

- **skill이 보이지 않음:** 설치 결과의 경로와 `SKILL.md`를 확인하고 새 대화에서 명시적으로 호출하세요.
- **이전 실행과 identity가 다름:** 기록의 hash를 고치지 마세요. 해당 실행에 맞는 보존 설치본을 사용하거나 명시적으로 연결한 후속 실행에서 재판정하세요. 설치 백업은 원래 코드를 보존합니다.
- **형식 거부:** 현재 schema와 오류의 위치·요구 타입을 확인하세요. 필드명을 추측해 반복하거나 옛 Review 참조를 최신 숫자로 교체하지 마세요.
- **작업이 오래 걸림:** 필요한 탐색·학습과 같은 자료의 반복 조회를 구분하세요. 충분한 단위는 종료하되 중요한 공백·후속 작업을 생략하지 않습니다.

README의 구성은 [UI UX Pro Max의 한국어 README](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/blob/main/README.ko.md)를 참고했으며, 기능과 설치 안내는 SynFrame 구현을 기준으로 작성했습니다.
