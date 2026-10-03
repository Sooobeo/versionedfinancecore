# Walmart P1 official evidence pilot

2026-05-21 23:59:59 EDT 정보집합에 해당하는 세 SEC 제출 문서에서 최초 pilot 때 연결 재무제표 수치 161개를 추출했다. `ingest_sec_financials.py`는 아래 고정 URL의 문서 bytes와 당시 SHA-256을 검증한다. FY27 Q1 HTML 응답에 SEC 전송 계층이 요청별 Akamai script/pixel을 삽입하는 경우 그 지정된 요소만 제거한 **문서 본문**의 SHA-256을 사용한다. 숫자나 공시 표는 바꾸지 않는다. 원문은 repository에 저장하지 않으며, 숫자와 locator/hash만 append-only CSV에 남긴다.

`source_ledger.csv::content_sha256`은 문서 본문 SHA-256이며, 각 receipt의 `notes`에 해당 최초 조회의 `raw_response_sha256`을 별도로 기록했다. 최초 조회 때는 삽입물이 없어 세 건 모두 두 hash가 같다. 이후 다른 User-Agent로 FY27 Q1 HTML을 재조회했을 때 raw HTTP 응답 hash `43e4ca4f945184dd3ed9db975357d701241bb2fccc83d452b22bbe5e19bdaaaf`는 삽입물 때문에 달랐지만 이를 제거한 문서 본문 hash는 표의 `0107dd5f...`와 일치했다. 그 후속 응답 hash를 최초 source receipt의 raw hash인 것처럼 대체하지 않는다.

| Source ID | SEC 원천 | 확인된 공개시점 | SHA-256 | 적재 사실 |
|---|---|---|---|---:|
| `wmt_fy25_10k_xbrl_20250314` | [FY25 10-K 접수](https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/0000104169-25-000021-index.html), [XBRL instance](https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/wmt-20250131_htm.xml) | 2025-03-14 16:40:52 EDT, SEC accepted | `5fcf3e216138d1e38cd8365f789f7f76a083295f5424fa0b4e1794c43f2a40ff` | 13 — FY24 BS |
| `wmt_fy26_10k_xbrl_20260313` | [FY26 10-K 접수](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/0000104169-26-000055-index.htm), [XBRL instance](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131_htm.xml) | 2026-03-13 16:06:24 EDT, SEC accepted | `07c72faa90cf8515eb1ff1ca264361ca8741c2663202d2f5a25ff9c694f4ef67` | 70 — FY24–26 P&L/CF, FY25–26 BS |
| `wmt_fy27q1_8k_ex991_20260521` | [FY27 Q1 8-K 접수](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/0000104169-26-000095-index.htm), [EX-99.1](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm) | 2026-05-21 07:00:00 EDT; SEC accepted 06:59:53, 07:00은 보수적 공개 경계 | `0107dd5fe2d6677d96f95b409c9a59d420da337eba515e4204fc34ea0e66b93d` | 78 — FY27 Q1·전년 동기 미감사 P&L/CF와 3개 시점 BS |

SEC 접수일과 보고기간 말일을 혼동하지 않는다. `first_public_at`은 FY25/FY26 10-K의 SEC 접수시각, Q1 8-K는 접수 이후인 07:00 EDT를 사용한다. 이 시각이 수치의 최초 공개 초 단위까지 독립적으로 입증한다는 주장은 하지 않는다. 세 문서 모두 cutoff 전 공개임은 확인된다. [2026-05-29 접수 FY27 Q1 10-Q](https://www.sec.gov/Archives/edgar/data/104169/000010416926000102/0000104169-26-000102-index.htm)는 제외한다. 2026-09-29 이후 retrieval은 공개 vintage가 아니라 수집 시점이다.

## Q1 재무상태표 추가 수집 vintage

2026-10-01 SEC의 같은 EX-99.1 URL에서 새 Akamai 경로 스크립트를 확인했다. 기존 `ingest_sec_financials.py`의 digest 고정은 그대로 두고 `ingest_sec_q1_balance_supplement.py`가 새 transport 패턴만 추가로 제거한다. 새 canonical body SHA-256은 `1da651ebab33b75f8057857ddc7c75d01ef3bf20642d169ac94321a311e49a1a`, 새 receipt ID는 `snap_49c5c3648bce32e436e8351fb8e66c300be5377bac06180d8fca8d3c590dba3f`다. 이전 body SHA-256과 다르므로 동일 문서의 새 수집 vintage로 별도 기록했다. 원래 78개 Q1 추출값을 현재 응답에서 모두 다시 읽어 비교했고 일치했다. 이것이 문서의 모든 비수치 문구가 과거와 동일했다는 증명은 아니다.

새 receipt에는 누락됐던 연결 재무상태표 계정 15종의 44개 비교기간 사실만 추가했다. 기존 161개 fact·3개 receipt는 덮어쓰지 않아 총 205개 fact·4개 receipt다. 2026-04-30 자산 289,607 million USD는 유동자산, 유형자산, 두 종류 사용권자산, 영업권, 기타 장기자산의 합계와 일치한다. 같은 날 유동부채 세부 합계 114,583 million USD, 부채·상환가능 비지배지분·자본 합계 289,607 million USD도 공시 합계와 일치한다. 2026-01-31 배당금 미지급 행은 대시로 표시되어 숫자 0 fact로 바꾸지 않았다. 2025-04-30 및 2026-01-31 비교값의 공개시점은 해당 보고기간 말일이 아니라 2026-05-21 EX-99.1 공개시점이다.

평가 가정 출처 20개는 `assumption_evidence.csv`에 locator와 관측값을 별도로 적었다. Nasdaq 종가, NYU ERP·업종 beta는 최초 공개시각·권리가 확인되지 않아 원천 fact ledger에 합치지 않고 screening 전용으로 둔다. `observation_sha256`은 선택 관측값의 해시이며 원천 전체의 SHA-256이 아니다.

## Scope, unit, and rights

- 범위는 Walmart Inc.와 자회사의 **연결** 재무제표다. `walmart_inc_us_de`는 제출 법인 식별자이며 부모법인 단독 현금으로 해석하지 않는다. 세 source의 `scope_bridges.csv`에 그 관계를 고정했다. Q1 자료는 미감사이며 `source_ledger.csv` title/notes와 extraction method에 기록했다.
- 10-K XBRL 원시값은 USD이고, EX-99.1 표시는 **USD millions**다. Q1 표의 정수 금액을 `×1,000,000`으로 USD에 정확히 변환하는 승인된 기계적 추출 규칙을 `ingest_sec_financials.py::canonical_usd_value`, `raw_facts.csv::extraction_method`, `mappings.csv::mapping_reason`에 명시했다. `raw_facts.csv::raw_value`는 이 명시적 변환 뒤 USD 값이다. Q1 capex 표시는 현금 유출 `(6,684)`이고 mapping `sign_multiplier=-1`로 양의 투자지출 6,684 million USD를 만들었다. 다른 부호는 그대로 유지한다. 일반적인 암묵적 단위·환율 변환 기능은 없다.
- 원문 재보존·재배포 권리는 확인되지 않아 source receipt의 `retention_right=NO`, `redistribution_right=NO`이고 raw snapshots는 없다. `transformation_right=YES`는 [Walmart 이용약관](https://corporate.walmart.com/terms-of-use)과 공개 SEC 수치의 최소한 개인 연구 전사를 위한 pilot 설정이다. 외부 데이터 feed나 원문 사본을 공개하지 않는다. 별도 법률 판단이나 독립 권리 검토는 완료되지 않았다.
- 자동 생성된 mapping/metric/bridge의 `review_status=APPROVED`는 Core가 사용할 수 있는 **기술적 매핑 상태**를 뜻한다. 독립 사람 검토를 뜻하지 않는다. normalized facts는 `PENDING_REVIEW`다.

## 재현과 검사

Repository root에서 다음을 실행한다.

```powershell
python cases/walmart_20260521_p1_valuation/01_evidence_core/ingest_sec_q1_balance_supplement.py
$env:PYTHONPATH='src'
python -c "from pathlib import Path; from versioned_finance_core.orchestration.core_build import build_core; print(build_core(Path('cases/walmart_20260521_p1_valuation'), Path('build/p1_pilot')))"
python -m pytest -q tests/integration/test_walmart_p1_evidence.py
```

추가 수집 스크립트는 새 canonical digest의 동일 URL bytes로 재실행하면 새 raw fact 0개다. 최초 스크립트는 원래 digest와 receipt 수를 고정하므로 현재 전송 응답으로는 실패하며, 이를 조용히 갱신하지 않는다. `build_core`는 immutable staging path를 새로 만들므로 이미 존재하는 동일 path에는 다시 쓰지 않는다. canonical `normalized_actuals.csv`는 `build/.../core_<content hash>/`에 있다. Case의 `02_financial_core/normalized_actuals.csv`는 output 계약 header이며 수기 값 저장소가 아니다. `summarize_core_build.py`는 staging의 fact/output ID를 `02_financial_core/historical_source_summary.json`으로 투영하며 재무 계산은 하지 않는다.

Case별 SEC 추출기는 D0 `build_core`의 공통 code hash 대상에 포함되지 않으므로 추출기 SHA-256 `db0f5afdd5cc4c88c3a2ee161090ce42d0e67cd5297e1927fd6dd42d8444df10`을 `historical_source_summary.json::sec_parser_sha256`에 별도 고정한다. 205개 사실의 현재 입력 hash는 `29e08663b59d649cc7d1a47da462c4c235b693050b5f76fdca3d330a35382812`, 색인 ID는 `source_summary_2c2b2e365d2b7ac21432b90706e71c33b97af7106c75fb5ce1818c9de16b76d4`다. 이후 추출기 수정 시 새 추출 버전·검토가 필요하다.

현재 FY26 cash roll-forward의 6개 원천 fact는 `02_financial_core/cash_identity_checks.csv`에 고정된다. Core output `cash_ee694f6c02541a5b6182456278b7cbc7f605dbc4391561be99cbe82f8b29f521`은 **현금·현금성자산·제한현금 합계**의 9,536 + 41,565 − 26,350 − 13,553 + 123 = 11,321 (USD millions), residual 0이다. FY27 Q1 [EX-99.1 현금흐름표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)는 같은 정의로 11,321 + 4,738 − 6,737 + 2,328 − 331 = 11,319, residual 0이다. Q1 대사는 오프라인 integration test의 독립 check이며 현재 `build_core` 계약이 하나의 cash identity만 출력하므로 별도 Core output ID는 없다.

현금흐름표의 제한현금 포함 잔액을 재무상태표 현금·현금성자산으로 대체하지 않는다. FY26 말 두 공시 수치는 각각 11,321 / 10,727 million USD, FY27 Q1 말은 11,319 / 10,729 million USD다. 차액 594 / 590 million USD는 표제 정의 차이의 산술 잔액이다. 이를 미국 부모법인이 자유롭게 쓸 수 있는 현금이라고 주장하지 않는다. FY26 10-K는 3.9 billion USD의 연결 현금·현금성자산이 법률 등 이유로 미국에 자유롭게 이전되지 않을 수 있다고 별도로 밝힌다.

**현재 경계:** 원천 적재·연결 scope·단위·cash identity의 자료 pilot이다. P1의 linked forecast, FCFF–WACC, terminal, EV→equity, 비교기업, 독립 검토와 투자 판단은 이 자료만으로 확정하지 않는다. Release는 `WITHHELD`다.
