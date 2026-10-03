# Versioned Finance Core

공개된 회사·규제기관 자료를 시점별로 보존하고, 동일한 재무 코어에서 운영전망·가치평가·자본배분·신용 판단을 만드는 개인 연구 프로젝트다. 코드와 조사에는 AI 보조가 사용됐으며 독립적인 사람 검토는 완료되지 않았다.

**처음 보는 독자는 [포트폴리오 요약](PORTFOLIO.md)에서 검증 결과, 사례별 판단 경계와 재현 순서를 확인할 수 있다.**

P0의 첫 합성 검증 흐름(D0)은 실행 가능하다. 첫 실제 공개자료 후보는 ㈜오리온 진천센터, 공개정보 기준시점은 2026-08-18 23:59:59 KST다. DART 반기보고서 원공시·정정공시의 연결·별도 현금흐름표를 출처별로 기록했고, 모회사 별도 현금 대사를 재현했다. 프로젝트별 미집행액·집행 일정·이연 권리는 확인되지 않아 case 상태는 `FEASIBILITY_ONLY`이며 투자·대출·경영 판단이나 공개 release는 없다.

## P0 실행 상태

- D0: 원문 snapshot/receipt → raw fact → cutoff 기반 정규화 → 현금 대사 → 근거 ID가 있는 scenario → output ID를 참조하는 memo field → fail-closed manifest 경로를 구현했다.
- R0: 공통 계약·권리·시점·scope·version 검증 기반과 [오리온 case 차터](cases/orion_jincheon_2026h1/00_charter/decision_object.md)를 준비했다. 실제 DART 현금 24개 사실을 4개 접수본·범위로 보존하고 [공식 투자 근거](cases/orion_jincheon_2026h1/01_evidence_core/investment_evidence.md)와 대조했다. 현금 slice는 재현됐으나 R0의 투자 판단 자료 gate는 통과하지 않았다.
- R1~R3: 합성 데이터로 기간 연결 재무제표·versioned forecast path, M1 variance/근거 검토형 DCF, M2 증분 세후 FCFF·NPV·closing funding, M3 채무자 cash path·시설/만기·reverse stress·covenant·회수 제한 상태와 M2/M3 교차 판단을 검증했다. 오리온의 실제 운영 전망·투자 대안·신용 판단은 근거 부족으로 `WITHHELD`다.
- 모듈별 실제 공개자료 후보: [Walmart 실적 대조](cases/walmart_fy27q1_guidance_outcome/), [South West Arkansas 프로젝트 DFS](cases/standard_lithium_swa_2025dfs/), [Ford Credit 채무·유동성](cases/ford_credit_2025ye_m3/)을 각각의 cutoff와 법인·현금흐름 범위로 분리했다. 공개근거가 충분한 계산 slice만 재현하며 각 의사결정 release는 `WITHHELD`다.
- O1: 금융서비스 overlay는 오리온의 식품 제조업 사례에 적용하지 않는다.

## P1 가치평가 실행 상태

[Walmart P1 공개자료 pilot](cases/walmart_20260521_p1_valuation/)은 2026-05-21 기준의 별도 `CORPORATE_VALUE` 사례다. 공식 SEC 문서 3건에서 161개 연결 재무 fact를 추출해 source·시점·범위·단위를 고정했다. FY26 Core 현금 대사와 FY24–FY26/FY27 Q1 reported 손익·재무상태 11개 항등식의 잔차는 0이다. Core가 FCFE와 근거가 있을 때의 FCFF를 소유하고, M1은 Core 출력 ID를 받아 claim에 맞는 가치평가·민감도·검토 gate를 적용한다. 실제 Walmart의 linked forecast·무차입 현금세금·할인율·terminal·청구권 대사 및 독립 검토는 아직 없어 수치 기업가치와 release는 `WITHHELD`다. [P1 실행 상태](docs/p1_execution_status.md)에 재현 절차와 남은 근거를 기록한다.

세부 범위와 남은 gate는 [P0 실행 상태](docs/p0_execution_status.md), 사례 선택 이유는 [case 목록](cases/README.md)에 기록한다.

## 구현 경계

- `financial_core`가 정규화 재무, driver, P&L·BS·CF, cash·debt, scenario를 한 번만 계산한다.
- `M1`은 P1 가치평가와 P2 실적차이·재전망을 결합한다.
- `M2`는 status quo 대비 대안별 증분 세후현금흐름과 자본배분 판단을 담당한다.
- `M3`는 obligor·instrument·유동성·차환·covenant·claim 판단을 담당한다.
- 금융서비스 overlay는 대상 case에 실제로 필요한 경우에만 활성화한다.

## 저장소 구조

```text
outline/                         원본 설계서(P0~P4)
docs/                            구현 아키텍처와 데이터/release 계약
config/defaults/                 전 case 공통 enum·gate 기본값
src/versioned_finance_core/      계산·검증·release 코드
cases/_template/                 새 case를 시작할 때 복제할 구조
build/                           재생성 가능한 작업 결과
releases/                        hash와 gate가 고정된 공개 snapshot
tests/                           단위·통합·known-answer test
```

## 빠른 시작

```powershell
$env:PYTHONPATH = "src"
python -m versioned_finance_core init-case sample_case
python -m versioned_finance_core validate-case cases/sample_case
python -m pytest
```

`init-case`는 기존 경로를 덮어쓰지 않는다. 생성된 `case.json`의 의사결정 질문, 관점, 기준시점, 관할, 통화와 활성 모듈을 채운 뒤 데이터 수집을 시작한다.
근거·mapping·version·현금 대사 입력을 채운 case는 `python -m versioned_finance_core build-core cases/sample_case`로 `build/`에 계산 결과를 만들 수 있다. 같은 입력의 기존 build는 덮어쓰지 않는다. `stage-release`는 검토용 `WITHHELD` snapshot을 만들고, `publish-release`는 모든 필수 gate가 통과한 stage에만 적용된다.

오리온 pilot의 재현 순서와 제한사항은 [R0 상태 문서](docs/p0_execution_status.md)에 적었다. `ruff`는 설치된 Python 모듈을 `python -m ruff check src tests`로 실행한다.

## 구현 지침

- 에이전트·기여자 필수 규칙: [AGENTS.md](AGENTS.md)
- 상세 구현·최적화 방식: [Implementation Playbook](docs/implementation_playbook.md)
- 아키텍처 경계: [Architecture](docs/architecture.md)
- 데이터 계약: [Data Contract](docs/data_contract.md)
- release 절차: [Release Process](docs/release_process.md)

## 주장 경계

이 저장소는 개인 연구·학습·포트폴리오용이다. 결과를 실제 회사의 내부 계획, 승인된 예산, 투자·대출 승인, 외부 신용등급, 법률·회계·세무 자문으로 표현하지 않는다. 공개정보가 부족한 값은 `UNKNOWN`, `NOT_TESTABLE_FROM_PUBLIC_DATA` 또는 `WITHHELD`로 유지한다.
