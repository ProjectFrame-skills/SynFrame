# v3.2 JSON·CLI 표현

이 파일은 합의 §§12–14·21–26의 구체적인 저장 표현이다. 판단 정책은 필수 계약을
따른다. Python 표준 라이브러리/SQLite만 사용하며 모델·서버를 실행하지 않는다.

## 호출과 버전

HostIO.build_result는 새 변경 중 호스트가 명시한 result_ids의 예상 참조와
명시적인 preserved_refs를 result_refs로 만든다. 나머지 의미적 결과 묶음은 모두
호스트가 전달한다. 결과 객체를 반환하며 적용하지 않는다. finish(operation, result)는
prepare와 apply를 실제 수행한다. 적용 뒤 work_context로 저장 결과·미완료를 대조한다.
finish는 같은 prepare/apply를 한 CLI 호출에서 수행하며 적용 검사는 그대로 실행한다.
preserve_files는 (path, source) 쌍 또는 정확히 path/source 두 키를 가진 레코드 목록을
받는다. 원자료의 위치·출처를 추측하지 않고 전체 목록의 형식/파일을 확인한 뒤 보존한다.

`python3 <skill-dir>/scripts/synframe.py --state <project>/.synframe <command>`

JSON은 `--input <path>` 또는 `--input -`로 전달한다. 성공은 JSON/코드 0,
거부나 Gate 실패는 JSON/코드 2다. 상태는 설치 skill 밖의 허용 위치에 둔다.

- schema: 14개 엔터티 필수 필드, 상태 축, 역할·연산 enum을 조회한다.
- schema --entity TYPE: 해당 엔터티의 필드·허용값·중첩 형식만 조회한다. 판단 기본값은 없다.
- schema --entities TYPE ...: 이미 함께 필요한 독립 형식의 전체 결과를 반환한다. HostIO.schemas(*types)도 같다. 실제 출력 예산 안에서만 묶고 고정 조회 목록으로 쓰지 않는다.
- schema --for-command transition: 실행 전이의 실제 입력 형식·상태 전이·완료 검증 구조를 조회한다.
- read-contract: 상태 없이 skill 파일명·현재 hash·문자 수를 조회한다. --name 상대명,
  --offset 문자 위치, --limit 1..6000, --expected-sha 현재 hash로 전문을 나누어 읽는다.
  next_offset이 남으면 그 파일의 필수 읽기는 아직 끝나지 않았다. 전송 크기는 추론
  할당량이 아니다. 실제 출력 잘림·문맥 소실·hash 변경을 확인하며 전달을 이해로 보지 않는다.
- work-context: --run [--operation ID]. 현재 observe의 revision/digest, 원문, 선택 질문,
  선언 소비자의 요청 참조/현재 객체/일치 여부, 기존·신규 자산과 후보, 미완료 학습,
  미반영 관측, 상향 의무와 채택 참조를 조회한다. stale 참조를 고치거나 역할을 추론하지 않는다.
  연산을 생략하면 반환 전 실제 잔여 작업 대조에 쓴다. PARTIAL 상태에서도 미반영을 노출한다.
- patch-refs: --run --input 변경 목록. 명시한 객체의 예상 새 버전과 현재 run revision을 조회한다.
  기존 참조를 새 버전으로 바꾸지 않으며, 의미·근거·종료·채택을 승인하지 않는다.
- review-context: --run --candidate ID@REV. Gate와 같은 현재 원문 facet·기능·질문·
  독립 후속·owner refs·snapshot과 structure의 기능 coverage/I/O 오류를 조회한다.
  structure는 Gate와 같은 검사를 사용하며 PASS나 종료 판단은 생성하지 않는다.
- preflight: --run --operation --input 결과. 실제 prepare/apply 검사 경로를 실행하고
  트랜잭션을 되돌린다. validated는 구조 검사 결과이며 의미 승인·버전 예약이 아니다.
  prepared_result를 검토하고 명시적으로 apply한다. apply 시 현재 버전을 다시 검사한다.
- solve: GoalSpec과 선택적 environment/resources, parent-run으로 CREATED 등록.
  모델 실행이 아니다. ACTIVE 전이 후 호스트가 실제 판단·도구를 수행한다.
- observe/status: --run. 현재 목표·질문·learning_tasks·frontier·propagation_obligations·
  path_assessments·미완료 연산·stale 참조·실제 피드백을 조회한다. observe는 digest를 제공한다.
- intent/apply/prepare: --run --input; apply/prepare는 --operation도 필요하다.
- finish: --run --operation --input. 기존 prepare→apply를 한 호출로 수행한다.
  새 추론 연산이 아니며 자동 재시도·판단 생성은 없다. 별도 prepare/apply도 유지한다.
- snapshot/gate: --run --candidate ID@REV; gate에는 --review ID@REV도 필요하다.
- learning-basis: --input task.json. closure_assessment.basis에 쓸 hash만 계산한다.
- get/list: --run. get은 --id와 선택적 --revision으로 과거 원문도 조회한다.
- explain/result: --run. 결정·이벤트 또는 package/검증/산출물/현재 한계를 조회한다.
- transition: --run --expected REV --input. target/reason와 필요한 evidence_refs,
  verification/package_ref. 기존 8개 실행 상태와 완료 조건은 그대로 유지한다.
- resume: --run만 쓰면 호환성·무결성 검사 후 복원한다. 실제 재개는 --expected와
  reason/evidence_refs가 필요하며 pending 효과 확인·reconcile가 먼저다.
- reconcile: --run --operation --expected --input. 실제 효과 검사 근거와
  resolution(not_executed/result_recovered/effects_inspected), reason을 기록한다.
- cancel: --run --expected --input(reason). 이후 작업 중지이며 외부 변경 취소가 아니다.
- migrate: --run. v3.1/schema1 원본을 수정하지 않고 연결된 v3.2 새 실행을 만든다.
  질문·기존 답은 OPEN/UNASSESSED 또는 PROVISIONAL로 이전하며 예전 K/Review/
  Commit/완료를 새 승인으로 바꾸지 않는다. pending 원본 작업도 기록한다.
- compare: --input left/right/dimensions(min|max). 미확인은 지배 관계로 계산하지 않는다.
- artifact: 실제 경로와 --source로 path/hash/source를 얻는다. 업로드 권한이 아니다.

엔터티 schema는 2, SQLite 테이블 layout은 1이다. 구버전 저장소는 읽기 전용 조회할
수 있지만 계약·코드 identity가 다르면 복원/쓰기하지 않는다. 원본 matching archive
또는 migrate/명시적으로 연결된 새 실행을 사용한다. 기존 hash를 새 hash로 덮어쓰지 않는다.

## 공통 엔터티·참조

보조 직렬화 API는 `scripts/synframe_host.py`의 HostIO가 제공한다. `edit(document,
**changes)`는 metadata를 제외한 깊은 복사다. 원본 관측·중첩 부모·기존 판정을 수정하지
않으며, 필드 값과 참조를 자동 교정하지 않는다. `patch_refs(changes)`의 예상 버전은
현재 상태에 한정된다. 변경 전 input_refs와 변경 후 결과/소비자 참조를 호스트가
구별해 연결한다. 오래된 참조를 무조건 최신으로 바꾸지 않는다.

`preserve_files(operation, files, expected_revision=REV)`는 호스트가 제공한
(path, source) 목록에서 실제 절대 경로와 파일 hash를 만들어 observe-result에
전달한다. 반환된 actual_observations의 path 또는 source를 EvidenceRecord.source에
명시적으로 연결한다. 이것은 내용의 지지 범위·검증 상태·충분성 판단이 아니다.
`preserve_observation`의 입력은 artifact 목록 자체이며 별도 객체로 감싸지 않는다.

`review_context(candidate_ref)`는 Gate와 같은 투영을 사용한다. 미선택 자산을
제외한 뒤 canonical 질문을 조회하므로 남아 있는 목표/선택 책임을 잃지 않는다.
각 질문과 독립 후속의 판단은 호스트가 수행하며 조회 결과를 일괄 PASS로 바꾸지 않는다.

`preflight(operation, result)`는 실제 검사에서 실패하면 오류를 반환하고, 통과해도
객체·이벤트·연산·체크포인트 변경을 모두 rollback한다. 새 의미 판단·외부 도구 실행은
없다. 성공 응답의 prepared_result와 예상 적용은 실제 적용·목표 완료가 아니다.
낯선 구조 작성/오류 교정 때 사용하며 모든 연산에서 검사를 두 번 실행하는 고정
파이프라인으로 만들지 않는다. 실패 원인이 근거·학습·상향 작업의 부재이면 실제
작업으로 복귀한다. 버전만 다시 붙여 통과시키지 않는다.

HostError는 stderr/stdout·종료 코드와 JSON detail을 보존한다. 오류 출력을 성공 JSON으로
읽지 않으며 실패 입력/출력과 교정 후 결과를 구분해 보관한다. 새 명령은 기존 상태
조회·직렬화·검증 책임의 보조 인터페이스다. 엔터티·schema/layout·추론 연산은 유지한다.

공통 metadata(id/type/revision/schema_version/created_at/updated_at/source_run_id/
provenance/validity_status)는 코어가 생성한다. apply에는 id/type/의미 필드, 선택적
provenance/validity_status/dependency_refs/extensions만 쓴다. 수정은 의미 필드 전체를
제공하며 새 revision이 된다. ReasoningRun/DecisionRecord/OperationRecord/Checkpoint는
일반 patch로 쓰지 않는다. 참조는 정확히 `{id, revision}`이다. 새 patch 객체는 새
revision을 가리킨다. 존재/버전/타입·참조·closure basis를 검사한다.

Frame lineage, LearningTask.origin_refs/goal_connections의 경로와 발견 목록은 이력이다.
실제 증명 의존은 역할로 선언한다. owner의 questions는 task의 당시 정확한 참조이며
현재 질문 조회는 canonical task의 최신 상태를 투영한다. 별도 답변 사본을 쓰지 않는다.
선택 후보의 snapshot에는 현재 task revision이 들어간다. 원본 관측·옛 상태를 삭제하지 않는다.

GoalSpec.extensions.goal_alignment는 decision-loop의 원문 facet 연결이다.
Capability.extensions.criterion_ids는 기능이 충족하는 성공 기준 ID다. 기능은 결과를
만드는 능력·선행으로 표현한다. 답변 목차를 기능으로 치환하지 않는다.
KnowledgeAsset.understanding는 context/level/questions(task refs)/evidence_refs/
stop_condition이며 asset provenance와 맥락별 이해 근거는 역할이 다르다.

## 작성 시점의 기계적 오류 감소 — 2026-10-14 후속 지시

schema --entity Frame은 실제 transformation 허용값을, LearningTask는 발견 항목 전체,
학습 판단 대상/소비자/관측 형식과 해석 본문의 문자열 조건을 노출한다. ReviewRecord는
independent_followups의 사전/항목 형식을 노출한다. 조회된 형식은 판단이나 기본 답이 아니다.

HostIO.patch_ref(id)는 정확히 `{"$patch_ref": id}`인 작성용 표시다. build_result가 같은
changes 묶음에 명시한 ID의 예상 새 참조로만 해석한다. 존재하지 않는 patch ID/잘못된
표시는 거부한다. 기존의 문자 그대로인 `{id, revision}` 참조는 변경하지 않는다.
입력 질문·원본 관측·과거 근거는 원래 정확한 참조를 보존한다. 호스트는 실제 변경
소비자에만 새 참조 표시를 선택하며, 의미·근거·Review·종료 재대조를 대신하지 않는다.
해석된 결과를 읽고 LearningTask의 closure basis는 해석 후의 내용에서 계산한다.
표시는 DB에 저장하지 않으며 finish의 기존 참조/버전/원자성 검사는 그대로 적용된다.

HostIO.connect(source, output, target, input, evidence_refs=...)는 호스트가 명시적으로
선택한 포트 이름과 선언 타입만 검사해 연결을 직렬화한다. saved 객체는 해당 버전,
patch 객체는 명시적 patch_ref를 사용한다. 포트/타입 불일치는 작성 시점에 거부한다.
이름·타입이 같아도 의미·단위·조건·전달 주체·근거의 유효성은 호스트가 확인하고,
후속 Gate는 선택 자산·현재 참조·근거·미연결 입력을 계속 검사한다. 연결을 추측하거나
변환 수단을 만들거나 provenance/PROVIDES/Review를 자동 승인하지 않는다.

HostIO.call('artifact', path=..., source=...)는 실제 CLI의 위치 인자 path로 전달한다.
일반 옵션 변환 때문에 --path를 만들어 실패하는 경로를 교정했다. 해시는 실제 bytes의
동일성만 확인하며, 파일 생성·원문 충족·내용 검증을 수행한 것으로 간주하지 않는다.

동일 파일·hash의 읽은 범위가 현재 문맥에 온전히 남아 있으면 중복 구간을 다시
출력하지 않는다. 맥락 소실·잘림·변경에는 해당 필수 전문을 다시 확보한다. 전송 크기
1..6000은 read-contract 목록에도 안내되며 추론·탐색·학습 깊이 제한이 아니다.

### 반복 작성 오류의 연결 보완 — 2026-10-15 후속 지시

상태 작성은 기존 HostIO를 재사용한다. build_result의 명시적 판단 입력을 wrapper에서
공통 성공·공백 없음·고정 K로 대체하지 않는다. 판단과 종료의 기존 책임은 그대로다.

preserve_files/preserve_observation에서 expected_revision을 생략하면 전달한
OperationRecord.extensions.expected_apply_revision을 사용한다. OperationRecord.revision은
그 연산 객체의 버전이며 실행 전체의 버전이 아니다. 관측 보존이 반환한 새 연산을
다음 보존에 사용한다. 동시 변경·오래된 연산은 기존 검사가 거부하며 자동 최신화하지 않는다.

모든 변경·연결을 끝낸 뒤 build_result로 표시를 해석한다. 공통 schema 검사가 엔터티와
결과 묶음의 실제 형식을 확인한다. answer_refs는 EvidenceRecord 참조 목록이며 주장
항목 참조가 아니다. schema --entity OperationRecord/SolutionPackage에서 결과 묶음과
패키지의 정확한 열 필드를 조회한다. build 후 새 표시를 추가하면 finish가 위치를
알려 거부한다. 결과를 다시 구성하고 종료 hash를 현재 내용에서 확인한다. 오래된
Review·근거의 참조 숫자를 자동 교체하지 않는다.

SolutionCandidate.extensions.functional_proof_refs/selection_validity는 코어가 계산한
투영이다. apply는 복사된 이 값을 입력 증명으로 사용하지 않고 현재 그래프에서
재계산한다. 호스트의 asset_refs/condition_refs/judgment_dependencies/provenance와
관계·근거·기능 증명·Review/Gate 검사는 유지한다. 옛 저장 객체·판단은 변경하지 않는다.

build_result와 finish는 같은 형식 검사를 사용한다. 형식 검사는 상태 변경·충분성 승인·
근거 내용의 검증이 아니며, 적용 시 현재 참조·의무·버전·원자성 검사를 계속 수행한다.
오류 원인이 실제 근거·기능·학습의 부재라면 해당 작업으로 복귀한다. 모든 연산에
preflight를 추가하는 고정 절차나 자동 반복 수정 루프를 만들지 않는다.

### 형식 추측·참조 추측·중복 전달 경로 교정 — 2026-10-15 후속 지시

완료는 `schema --for-command transition`의 입력을 따른다. verification은 별도 criteria나
success_criteria 객체로 감싸지 않고 현재 GoalSpec.success_criteria의 ID를 직접 키로 쓴다.
각 값은 정확히 status(PASS/FAIL/UNKNOWN), evidence_refs(EvidenceRecord 참조 목록),
rationale(호스트가 판단한 근거 설명)이다. `HostIO.complete(context, package_ref=...,
reason=..., evidence_refs=..., verification=...)`는 관측한 work_context의 revision과
명시적 검증을 전달한다. 공통 validator가 잘못된 위치·필수 키를 알려주며 코어도 같은
형식을 검사한다. 호스트의 PASS/중요도/범위 판단을 만들지 않는다. 현재 근거·Commit·
성공 기준·pending·산출물·minor uncertainty 근거·버전 검사는 계속 완료를 차단한다.

`HostIO.result_ref(applied_result, id)`는 실제 결과에 반환된 그 ID의 정확한 참조만
가져온다. 결과에 없는 ID는 거부하며 최신 객체 조회나 revision 증가를 하지 않는다.
`HostIO.gate(candidate_ref, review_ref)`로 이 참조를 전달한다. 오래된 판단에 새 숫자를
붙이지 않는다. `review_context.structure`에서 실제 연결·기능 오류를 먼저 확인하되,
Gate의 전체 검사와 호스트의 의미 Review를 대신하지 않는다.

schema --entity Frame은 structural_difference.rationale까지 안내한다. dependency_refs는
일반 참조 목록이고 역할 있는 의존은 SolutionCandidate.extensions.judgment_dependencies다.
SolutionPackage.validation_refs는 ReviewRecord가 아닌 EvidenceRecord 참조 목록이다.
minor uncertainties는 description/important/rationale/evidence_refs로 실제 비중요 근거를
호스트가 작성한다. 오류의 path/expected_keys/expected_type과 입력을 대조하여 고친다.
필드명만 바꿔 가며 재시도하거나 실제 공백을 형식 변경으로 숨기지 않는다.

read-contract --retained FILE의 JSON은 `{retained_in_current_context: true, ranges: [...]}`다.
각 range는 이전 실제 응답의 name/sha256/offset/end/chunk_sha256를 포함한다. 호스트가
그 전문 범위를 현재 문맥에 온전히 보유함을 확인한 경우에만 선언한다. 현재 파일 hash와
구간 hash가 같고 요청 전체가 덮이면 text를 다시 전달하지 않고 reused_retained를 반환한다.
부분 범위·변경 파일·선언 생략은 전문을 다시 전달한다. 잘못된 구간 hash는 거부한다.
문맥 소실·잘림에는 선언을 비우고 필수 전문을 확보한다. 디스크 영수증·과거 전달만으로
현재 보유·읽기·이해를 인정하지 않으며 프로세스/세션 전체의 자동 캐시로 쓰지 않는다.

### 기능을 유지하는 운반·조회 최적화 — 2026-10-15 도입

HostIO는 --compact 기계 JSON을 사용한다. 직접 CLI의 기본 보기는 들여쓰기를 유지하고,
--compact는 command 앞에 명시한다. 모든 키·값·원문 문자열과 종료 코드가 같으며 판단
내용을 요약하거나 삭제하지 않는다. 여러 schema 조회의 묶음은 요청한 전체 구조를
반환하며 명시적 타입만 다룬다. 필수 전문·학습·탐색·Review 횟수를 제한하지 않는다.

preserve_files/preserve_observation의 반환은 실제 갱신된 OperationRecord다. 중간 쓰기가
없으면 즉시 같은 객체를 get하지 않고 반환을 사용한다. 여러 파일/source를 한 번에
전달하고 반환 actual_observations의 명시한 receipt만 산출물에 연결할 수 있다. 서로
의존하는 학습·판단을 배치로 합치지 않는다. 파일 hash는 기존 검사 경계마다 전체 바이트를
나누어 읽어 계산하며 메모리에 한꺼번에 올리지 않는다. 변조·부재 검사는 유지한다.

snapshot/review-context/Gate는 한 readonly SQLite snapshot 안의 문서·정확한 현재 참조를
함께 사용한다. 쓰기 트랜잭션 안에서 호출하면 그 현재 snapshot만 사용한다. 호출이 끝나면
뷰를 폐기하며 다른 호출·revision·쓰기 뒤에 재사용하지 않는다. 패키지 identity·stale·
역사 참조·호스트 의미 판단·최종 apply 검사는 그대로다. 의미적 PASS·K·종료 캐시는 없다.

## LearningTask

- goal_ref, question, subject: subject는 `{concept}` 또는 `{asset_ref}`.
- context: purpose/environment/version/conditions/constraints/scope.
- origin_refs, goal_connections: 각 연결은 goal_ref/facet_ids/path_refs/rationale.
  원문 facet까지 상속하며 초기 criterion에 질문이 없었다는 이유로 거부하지 않는다.
- answer_requirements: id/ability/discriminator/sufficient_when/evidence_requirement 목록.
- assessment: relevance(RELEVANT/POSSIBLE/UNASSESSED/NOT_RELEVANT), materiality
  (MATERIAL/NONMATERIAL/UNKNOWN), role(CRITICAL/SELECTION/INDEPENDENT/SCOPING),
  rationale/evidence_refs/unknowns. 역할은 기존 계약의 작업 성격을 직렬화한 것이다.
- answer: status/claims/counterevidence_refs/gaps/scope. claim은 stable id/text/
  evidence_refs/source_locator/conditions/inference. 반박을 보존해 처리할 때 선택적
  counterevidence_assessments(counter_ref/disposition/rationale/evidence_refs)를 쓴다.
  disposition은 RESOLVED/OUT_OF_SCOPE/UNRESOLVED이며 미처리는 종료를 막는다.
- understanding: status/abilities(id/status(MET/UNMET/UNKNOWN)/evidence_refs/rationale)/
  k_level(null|0..4). SUFFICIENT는 필요한 모든 ability의 실제 근거 연결을 요구한다.
- expansion: status/discoveries/scope_rationale/evidence_refs. discovery의 필드는
  decision-loop에 있다. ACCOUNTED는 모든 처분·실제 후속 참조가 있어야 한다.
- dependency_refs: source_ref/role/required/scope/rationale 목록. provider→현재 task.
  역할은 DISCOVERED_FROM/ANSWER_DEPENDS_ON/SUPPORTS/REFUTES/AFFECTS/COMPARES_USING/
  USES_PROOF/REUSES. 발견 이력을 필수 증명으로 승격하지 않는다.
- work_state, disposition, closure_assessment, reopen_conditions: 독립 상태 축이다.
  closure는 verdict/rationale/evidence_refs/basis/scope/remaining_uncertainties를 포함한다.
  ANSWERED/NOT_APPLICABLE/SUPERSEDED/REUSED가 CLOSED 사유다. 재사용은 target_ref/
  compatibility/preserved_connections를 추가한다. MERGED는 모든 연결·발견·의존·
  재개 의무를 대상에 보존한다. DEFERRED/PAUSED는 impact/remaining_work/재개 조건이 필요하다.
- extensions.next_action: 실제 다음 기존 연산. 종료 단위는 예약하지 않는다.
  extensions.reopen_event: kind(COUNTEREVIDENCE/CONTEXT_CHANGED/PARENT_NEED/
  EVIDENCE_INVALID/SCOPE_CHANGED), rationale, 실제 새로운 evidence_refs.

충분성에는 현재 맥락의 답·능력·근거·처리된 발견·필수 의존·반박 처리가 필요하다.
그 상태에서 OPEN으로 계속 예약하려 하면 거부한다. 충분하지 않은 unit을 닫거나,
경로 종료/제약을 ANSWERED로 바꾸거나, 같은 근거로 종료를 재개하면 거부한다.

## 그래프·후보·검토

DependencyLink는 sources→target_ref, relation, group_id, evidence_refs다. 기능 관계는
AND/OR/REQUIRES/PROVIDES/TRANSFORMS/CONFLICTS/ENABLES, 의미 소비자 관계는 위 역할들이다.
그룹 key는 target+relation+group_id. 최소 근거 고정점으로 순환만의 충족을 거부한다.
OR는 유효한 한 witness와 그 witness의 모든 선행을 사용한다. 후보 extensions의
proof_choices는 `target/OR/group_id`→source ID로 실제 witness를 지정할 수 있다.
condition_refs는 선택해 사용하는 EvidenceRecord 조건 참조이며, 기능·전제는 Capability로
표현할 수 있다. CONFLICTS는 실제 증명에 쓰이는 자산·기능·조건 모두를 검사한다.
코어가 functional_proof_refs를 계산해 선택 경로의 의존만 기록한다. 미선택 OR 원소의
변경은 전체 카탈로그를 깨뜨리지 않는다. 비교 의존은 judgment_dependencies의
source_ref/role/required/scope/rationale 또는 역할 DependencyLink로 별도 연결한다.

ReviewRecord.checks는 기존 coverage/io/knowledge/evidence/conflicts/complexity/
selection/marginal_value 및 constraint:<id>. 값은 status/rationale/evidence_refs다.
필수 extensions는 verdict, goal_alignment(facet ID별), capability_conditions(기능 ID별),
question_assessments(현재 질문 key별), information_need_refs(정확한 owner refs),
search_value(alternatives/stop_rationale)다. 대안은 action/expected_improvement/cost/rationale.
verdict는 READY/NEEDS_WORK/PARTIAL_ONLY/BLOCKED다. Gate는 READY 및 정확한 snapshot,
개별 근거, 중요한 task·발견·상향 의무 해소, 기능·입출력·제약 검사를 요구한다.
구조 검사가 문서의 의미적 진실까지 보증하지 않는다.

## 연산 입력·출력과 원자성

입력: action/observed_revision/input_refs/constraints/evidence_refs/decision/intent/
idempotency_key. decision은 action/ddc/alternatives/evidence_refs/rationale/expected_effects.
DDC는 기존 8필드이며 observable_state는 revision/state_digest/facts다.
학습 intent는 learning_task_refs와 learning_plan을 포함한다(필드는 decision-loop 참조).

출력: operation_id/result_refs/proposed_state_changes/evidence_refs/unresolved_items/
observed_effects/next_decision_inputs/outcome(SUCCEEDED|FAILED|UNKNOWN) 및 다음 목록.

- learning_results: task_ref(입력 버전)/result_ref(실제 새 task)/answer_refs/
  understanding_change/discovery_ids/upward_effects/observations/prediction_difference.
  선택 task를 정확히 덮으며 네 묶음이 실제 결과에 연결돼야 한다.
- propagation_resolutions: id/assessment/evidence_refs/rationale/result_refs/remaining_work.
  코어 생성 의무의 ID를 사용한다. NEEDS_OBSERVATION은 남은 작업이 있고 PENDING,
  다른 판정은 실제 반영 후 RESOLVED다. REVISE/INVALIDATE는 대상 새 revision이 필요하다.
- path_assessments: id/task_ref/verdict(PATH_END)/rationale/evidence_refs/next_paths.
  종료한 경로와 OPEN 질문을 구분한다.

해당 없는 목록은 빈 목록일 수 있으나 호스트가 실제 범위에서 비적용을 판단한다.
학습 결과·피드백을 모든 연산에서 고정 빈 목록이나 성공 문구로 만들지 않는다.
prepare는 실제 저장 상태와 patch의 미해결 task/상향 의무를 전달한다. 호스트의 별도
조건을 보존하고, 반복 finish는 저장된 동일 결과를 재사용한다. apply는 원자적으로
새 상태·발견 처리·의존·무효화·상향 의무·종료·실제 피드백·체크포인트를 저장한다.

상향 의무는 OperationRecord.extensions.propagation_obligations에 저장하며 새 엔터티가
아니다. id/source_ref/source_change_id/target_ref/relationship_role/affected_scope/status/
assessment/evidence_refs/rationale/result_refs/remaining_work를 갖는다. 후속 연산의
resolution도 이력으로 보존한다. source가 바뀐 옛 PENDING은 새 의무가 인계한 경우만
SUPERSEDED로 남고 inherited_remaining_work를 보존한다.

REFRAME는 네 기존 trigger와 steps(assumptions/axis/structural_difference/
information_requirements/graph_changes/dependent_judgments/validity_changes/rediscovery_scope)를
그대로 요구한다. 중복 Frame과 새 다섯 번째 트리거는 허용하지 않는다.
COMMIT은 시작/결과 적용 모두 Gate가 필요하며 실행 완료가 아니다. COMPLETED에는
실제 성공 기준별 관측과 package, 구현/산출물 요청에는 직접 측정 근거와 실제 path/hash가
필요하다. 원본 pending·실패·미검증을 성공 기록으로 덮어쓰지 않는다.

## 2026-10-13 상세 조건의 저장 표현 (§27.6)

학습 계획은 decision-loop의 상세 실행 연결을 따른다. next_observation은 문자열이
아닌 target/source/locator/information/decision_effect 객체다. requirement_ids는 현재
answer_requirements의 ID를, known_evidence_refs는 실제 기존 근거를 연결한다.
judgment_target은 target_ref/item_id(null 가능)/decision/consumer_refs/scope다.
판단 항목 ID는 참조한 정확한 객체 버전에 존재해야 한다. 능력 기준 변경은
extensions.requirements_change.rationale/evidence_refs로 실제 변경 근거를 연결한다.

discovery는 understanding_gap 문자열을 포함한다. UPDATE에 공백이 남으면 실제 미완료
LearningTask도 target_refs에 포함한다. DEFERRED는 기존 종료/영향/재개 필드와 함께
closure_assessment.selected_action/comparison_rationale를 포함한다.
Review NEEDS_WORK의 extensions.followup_refs는 실제 미완료 task/operation 또는 해당
patch에서 실제 갱신한 DependencyLink를 연결한다. 의존 수정에 불필요한 새 학습을 강제하지 않는다.
READY 검사의 independent_followups는 decision-loop의 현재 독립 미완료 질문별 평가다.
MAINTAIN은 실제 현재 대상 버전을 result_refs에 연결한다.

observe-result --run --operation --expected --input artifacts.json은 기존 pending
연산에 실제 관측 파일 목록(path/sha256/source)을 보존한다. 파일 존재와 hash를 검사하고
OperationRecord.extensions.actual_observations, 이벤트, checkpoint를 함께 저장한다.
평가·성공·K·종료는 생성하지 않으며, apply 전 관측 보존 뒤에도 결과 적용이 가능하도록
expected_apply_revision을 갱신한다. 중단 복원에서 pending intent와 함께 확인한다.
같은 artifact 재등록은 중복 저장하지 않는다. 다른 동시 상태 변경은 거부한다.
호스트가 의미 평가를 끝내면 원래 operation_id에 prepare/apply한다.

## 자동화 우선 계약의 기존 표현 (§27.7)

새 엔터티·필수 JSON 필드·추론 연산을 추가하지 않는다. 실제 판단과 다음 행동은
decision-loop의 §27.7 연결 절차 및 필수 learning-contract 전체를 따른다.

| 판단·결과 | 기존 저장·호출 |
|---|---|
| 수행 방식·수동 요구 범위 | GoalSpec 원문 facet/interpretation·explicit_constraints |
| 기능 도출부터 기존 능력 평가 | Capability I/O·조건·derivation_refs, DDC/DecisionRecord |
| 중요한 존재·능력·연결 미확인 | LearningTask, capability questions, learning_plan, DISCOVER/DEEPEN |
| 자산 실체·절차·주체·저장·검증 범위 | KnowledgeAsset·주장별 EvidenceRecord·canonical task |
| 출력→입력·전제·변환·공백 | candidate.connections, DependencyLink, task·기존 io Review |
| 개입·재사용·새 구현 부담 비교 | candidate.attributes/comparison_rationale, COMPARES_USING |
| 후보·작업 대체 | 대상 새 revision, 기존 task 처리·효과 확인/reconcile·상향 resolution |
| 종료와 남은 독립 의무 | closure/frontier, independent_followups, actual_feedback |
| 채택 차단과 수정 | checks/capability_conditions, NEEDS_WORK.followup_refs, Gate |

Review.checks의 추가 중요한 조건도 기존 status/rationale/evidence_refs 형식이다.
기본 검사뿐 아니라 선언된 모든 조건이 유효 근거 있는 PASS여야 Gate를 통과한다.
키 이름으로 의미를 추론하거나 특정 자동화 검사 키를 강제하지 않는다. 비중요한
잔여 불확실성은 범위·근거 있는 uncertainties/gaps 및 독립 질문 평가에 보존한다.

엔터티 schema 2와 테이블 layout 1, 아홉 추론 연산은 유지한다. 패키지 identity가
변경되므로 이전 실행의 직접 복원/쓰기는 거부된다. 이전 아카이브 또는 연결된 새
실행으로 재평가하며 이전의 답·K·Review·완료를 새 승인으로 사용하지 않는다.


## 신규 탐색·통합 조합의 기존 표현 (§§27.8–27.10)

세 책임은 기존 LearningTask의 안정 ID로 식별한다. 새 엔터티·상태 축·필수 최상위
JSON 필드·추론 연산을 추가하지 않는다. `schema`의 record_contracts.tool_obligations는
식별 규칙과 능력 ID를 조회하며 의미 판단을 생성하지 않는다.

| 책임 | ID | 필수 능력 ID |
|---|---|---|
| 적용 판정 | `<goal-id>:tool-scope` | scope.applicability |
| 실제 신규 탐색 | `<goal-id>:tool-discovery` | discovery.goal_link / discovery.actual_search / discovery.observed_scope / discovery.selection_effect / discovery.termination |
| 통합 조합 | `<goal-id>:tool-composition` | composition.roles / composition.dispositions / composition.combinations / composition.connections / composition.comparison / composition.remaining_work |

solve는 적용 질문만 미평가 등록한다. 호스트의 적용 판정이 현재 목표에서
CLOSED/ANSWERED이면 코어는 두 의무를 OPEN/UNANSWERED/UNASSESSED로 등록한다.
prepare는 이 미해결 등록을 실제 다음 판단 입력으로 투영한다. 실제 답이나 K를
대신 생성하지 않는다. 비적용은 근거 있는 CLOSED/NOT_APPLICABLE이며 적용 질문의
SUPPORTED 답·SUFFICIENT 능력·ACCOUNTED 평가와 현재 버전을 확인한다.

고정된 ID와 최소 능력 항목은 채택된 책임을 추적하기 위한 것이며 실행 횟수나
학습 깊이가 아니다. 현재 목적에 맞게 question/context/능력의 구별·관측 기준을
구체화한다. 기준 변경에는 기존 requirements_change의 관측 근거를 연결한다.
의무의 역할은 scope=SCOPING, discovery/composition=SELECTION이다. 적용되는 두
의무를 비중요·비관련·독립 개선으로 낮추지 않는다.

신규 탐색을 닫으려면 실제 DISCOVER_KNOWLEDGE 연산의 선택 질문과 actual_search
근거가 보존된 관측에 연결돼야 한다. 기존 observe-result로 path/sha256/source를
보존하고 EvidenceRecord.source를 원 출처 또는 그 파일 경로로 연결한다. 직접 질문
또는 ANSWER_DEPENDS_ON/SUPPORTS/USES_PROOF/REUSES로 연결된 학습 제공자의 실제
관측을 사용할 수 있다. 파일·해시·연산 연결은 실제 탐색의 의미적 적절성을 증명하지 않는다.

최종 통합 조합은 current discovery를 COMPARES_USING으로 연결하고, 현재
EXPAND_COMPOSITION learning_results의 result_ref/observations/upward_effects로 실제
평가를 연결한다. 중간 조합 작업은 탐색과 번갈아 수행할 수 있으나 최종 closure는
미완료 탐색을 생략하지 않는다. discovery의 변경이 만드는 상향 의무는 기존
propagation_resolutions로 실제 처리한다. 기능 증명에 모든 대안을 AND로 넣지 않는다.

병합·재사용 시 책임별 안정 ID는 앵커로 보존하며 target_ref로 대표 질문에 연결한다.
대표 질문은 각 책임의 능력·목표·범위·관측·미완료·부모 연결을 보존한다. 순환 재사용과
능력 소실은 거부한다. 과거 실행의 승인을 새 identity로 자동 이전하지 않는다.

observe/status의 tool_obligations는 현재 적용 판정과 기대되는 책임·참조의 읽기 전용
투영이다. core Gate는 Review의 임의 검사 키와 독립적으로 적용 질문·조건부 두 의무의
존재/현재 목표/유효성/충족/실제 관측 바인딩을 확인한다. READY 저장과 Commit/COMPLETED에
같은 차단을 적용한다. 실제 접근 제약은 미해결 상태와 PARTIAL/BLOCKED/SUSPENDED로
보존하며 비적용이나 성공으로 바꾸지 않는다.

독립 개선은 선택·미선택 자산 모두 Review.independent_followups에서 평가한다.
UNKNOWN 영향·CONTINUE는 채택을 막는다. 근거 있는 DEFER/NO_CURRENT_EFFECT는 현재
결론의 유지 조건·영향·재검토 조건을 보존하며 해당 질문의 완료를 뜻하지 않는다.
필수 증명 의존이 있는 질문은 역할 이름을 바꾸는 것만으로 의존이 없어지지 않는다.

## 목표 해석 검토의 기존 표현 (§§27.11–27.12)

기존 LearningTask의 안정 ID `<goal-id>:goal-interpretation`을 사용한다. solve는
미평가 질문과 일곱 능력만 등록한다. assessment.role은 SCOPING이고 비관련·비중요·
독립 개선으로 제외할 수 없다. 모든 목표에서 처리하되 복수 Frame·외부 검색·고정 K를
강제하지 않는다. schema의 record_contracts.goal_interpretation에서 식별을 조회한다.

기존 extensions에 `interpretation_review`를 직렬화한다. 새 필수 최상위 필드·엔터티·
연산·실행 상태는 없다. 아래는 채택된 원문 책임의 저장 표현이다.

- current_interpretation, assumptions, result_properties: 현재 해석·가정의 종류·결과
  성질과 미확정의 실제 범위. 없는 가정도 확인한 범위와 이유를 명시한다.
- interpretations: 안정 id, facet_ids, result_scope, basis(원문/맥락/추론/미확인),
  assumptions, difference, decision_impact, uncertainties, consumer_refs(현재 정확한 참조),
  disposition, rationale, reopen_condition. 복수 수는 강제하지 않는다.
- support 및 omission: 각각 target/scope/source_locator/rationale/facet_ids/evidence_refs.
  현재 목표의 중요한 facets를 보존하고 실제 대조 대상·읽은 위치를 별도로 연결한다.
  동일 자료/근거를 쓸 수 있지만 동일 지지 기록을 누락 대조로 복제하지 않는다.
- omission에는 source_to_result, result_to_source, counterfactual_scope,
  observed_structures, remaining_uncertainty_assessment와 difference_ids를 둔다.
  앞의 다섯 값은 실제 대조 범위·결과를 설명한다. counterfactual_scope는 후보 성공에도
  원문 목적을 놓칠 조건을 검토한 내용이며 반례의 발명을 요구하지 않는다.
  difference_ids는 canonical expansion.discoveries의 안정 ID 목록이며 차이가 없을
  수도 있다. 해당 발견의 중요성·공백·후속 처리는 기존 학습 계약으로 관리한다.
- handling은 CURRENT/COMMON/CONDITIONAL/UNRESOLVED라는 평가 내용이다. 새 실행 상태가
  아니며 미처리 UNRESOLVED는 종료할 수 없다. CONDITIONAL은 실제 conditional_results가 필요하다.
- treatment와 termination_scope: 현재 해석/복수 해석 처리/미처리 내용, 근거·종료 범위.
  조건부 처리가 있으면 conditional_results에 condition/result/method/roles/work/
  verification/fact_assessment/unresolved_preference_authority/evidence_refs를 기록한다.
  현재 판별 가능한 사실은 호스트가 판별하며 미확정 의도 자체를 해결한 것으로 쓰지 않는다.
- effects: target_ref/assessment/evidence_refs/rationale로 현재 소비자·실제 영향을 연결한다.
  기존 MAINTAIN/REVISE/INVALIDATE/NEEDS_OBSERVATION을 쓰며 실제 미반영은 종료를 막는다.
  기존 propagation_resolutions와 result_refs에도 실제 새 버전·유지·미완료를 연결한다.

이 근거를 claim/ability의 각각 실제 지지 범위에 연결한다. CLOSED/ANSWERED는
SUPPORTED/SUFFICIENT/ACCOUNTED와 현재 basis, 필요한 실제 학습·후속 처리 및 두 경로의
실제 관측 binding을 요구한다. binding은 현재 task의 실제 learning_results와
observe-result의 원본 파일/hash/source 및 각 경로 EvidenceRecord.source를 대조한다.
학습 결과는 기존 네 묶음을 따르며 Goal Compiler 또는 선택한 기존 연산에서 작성한다.
동일 원자료를 재사용해도 현재 대조/위치/소비·종료 근거를 다시 확인한다. 파일 동일성은
누락 검토의 의미적 적절성·완전성의 증거가 아니다.

§27.14의 예외는 원래 두 경로의 판단 내용이 그대로 유효하고 소비자 버전만
재대조하는 경우다. SIMPLIFY intent에 `interpretation_rebind` 객체를 둔다:
`task_ref`는 현재 CLOSED/IDLE 목표 해석의 정확한 참조, `rationale`은 재대조 이유다.
learning_task_refs/learning_results는 비워 두며 종료한 학습을 다시 선택하지 않는다.
현재 소비자 버전·적용을 실제 관측하고 새 파일을 observe-result로 보존한다.
새 EvidenceRecord는 measured이며 source를 이 receipt에 연결하고, extensions의
`consumer_comparison`에 `consumer_refs`(해석별 소비자와 effects 대상의 중복 제거·ID순
현재 참조 목록), `assessment: MAINTAIN`, `rationale`(실제 대조 범위·유지 이유)을 둔다.
이를 result.evidence_refs 및 각 현재 effect.evidence_refs에 연결한다.
호스트가 edit한 task는 interpretations.consumer_refs와 effects의 현재 참조·유지 근거만
변경한다. closure_assessment.basis는 새 task로 계산하고 rationale은 현재 종료 이유를
명시한다. task의 새 참조를 result_refs에 포함한다. 원래 goal·질문·맥락·능력·답·K·발견·
두 경로·출처·기타 내용과 소비자 정체성은 그대로여야 한다. 실제 의미 변경은 기존
material reassessment로 보낸다. 코어는 원래 학습 관측과 새 소비자 대조를 각각 검사한다.
옛 receipt 재등록·임의 참조 숫자 교정·새 학습 묶음 작성은 이 경로의 대체가 아니다.
preflight 후 현재 버전으로 apply하고 새 Review/Commit을 수행한다. 이 경로는 현재
패키지 identity의 같은 실행에 적용되며, 과거 다른 identity 실행을 자동 이식하지 않는다.

learning-basis에는 interpretation_review도 포함된다. 옛 종료 근거로 경로를 바꿔
닫힌 상태를 유지하지 않는다. 병합·재사용 시 안정 책임 앵커·일곱 능력·두 경로·현재
목표·부모·범위·미완료를 보존한다. 처음부터 등록하지 않은 책임도 goal에서 찾는다.

observe/status.goal_interpretation은 존재·현재 goal·답 상태·두 경로 기록의 투영이다.
READY/Commit/COMPLETED는 임의 Review 검사명과 별도로 책임·현재 버전·두 실제 경로를
검사한다. 선택에 중요한 미해결 후속과 상향 PENDING은 기존 Gate에서도 차단한다.
충분한 단일 해석 또는 실제 공통/조건별 처리는 허용한다. 독립 미래 활용의 존재만으로
검토를 계속하지 않는다. 의미적 판단은 단일 호스트가 수행하며 코어는 숨은 의도나
전 세계 미발견 관점을 자동 판정하지 않는다.
