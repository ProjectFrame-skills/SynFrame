# SynFrame

[English](README.md) · **한국어** · [简体中文](README.zh.md)

![Architecture](https://img.shields.io/badge/architecture-ACDS%20v3.2-2563eb)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Runtime](https://img.shields.io/badge/runtime-standard%20library%20%2B%20SQLite-16a34a)

**목표에 필요한 지식을 발견하고, 이해하고, 도구와 skill을 조합해 실행 가능한 해결책을 만드는 AI skill.**

SynFrame은 사용자가 어떤 기술을 얼마나 공부해야 할지 대신 정하도록 설계됐습니다. AI가 목표에서 필요한 기능과 질문을 도출하고, 조사 결과로 다음 탐색 공간을 넓히며, 새 지식을 원래 목표와 해결책에 반영합니다. 학습의 깊이는 고정하지 않고, 필요한 근거가 충분해진 가지는 종료합니다.

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

Python 3.11 이상과 Git이 필요합니다. 실행 보조 코드는 Python 표준 라이브러리와 SQLite만 사용합니다.

```bash
git clone https://github.com/ProjectFrame-skills/SynFrame.git
cd SynFrame
python3 tools/install.py
```

기본 설치 위치는 `${CODEX_HOME:-$HOME/.codex}/skills/synframe`입니다. 설치 후 새 Codex 대화에서 skill을 호출하세요. 설치 경로를 직접 지정할 수도 있습니다.

```bash
python3 tools/install.py --destination /absolute/path/to/skills/synframe
```

기존 SynFrame 설치는 교체 전에 별도 백업합니다. 설치 명령의 결과에서 설치 경로, 백업 경로, 파일 hash를 확인할 수 있습니다. 다른 skill 폴더에는 설치하지 않습니다.

SynFrame 전용 모델 API 키나 추론 서버는 필요하지 않습니다. 실제 검색·코딩·외부 도구 사용은 호스트 AI가 자신의 도구와 권한으로 수행합니다. 특정 작업에 필요한 외부 서비스의 접근 권한은 별개입니다.

## 사용법

### 명시적으로 호출

```text
$synframe 다른 웹사이트를 참고해 지금 만들고 있는 앱의 디자인을 개선하고 싶어.
필요한 개념과 자동화 수단을 조사하고, 우리 프로젝트에 맞는 방법을 추천해줘.
```

```text
$synframe 현재 프로젝트에 구독 기능을 추가하고 싶어.
참고 제품의 실제 운영 방식을 조사하고, 결제·권한·배포 연결까지 검토해줘.
```

```text
$synframe 결제 CSV를 고객·통화별로 합산하는 도구를 만들어줘.
잘못된 입력 처리와 실제 실행 결과도 확인해줘.
```

기술 이름·학습 깊이·검색 횟수를 미리 지정할 필요가 없습니다. 현재 설치는 Codex의 skill 형식을 대상으로 검증합니다. 자동 선택은 호스트 설정에 따르며, 명시적인 `$synframe` 호출로 사용할 수 있습니다.

이 예시는 README의 사용법입니다. 특정 분야·제품·예상 답을 운영 조건으로 강제하지 않습니다.

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
