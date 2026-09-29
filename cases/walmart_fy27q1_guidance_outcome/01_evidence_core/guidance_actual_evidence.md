# 공식 근거·정의·시점

## 원천과 공개 시점

| source_id | 공식 locator | 용도 |
|---|---|---|
| `wmt_guidance_fy27q1_20260219` | [회사 FY26 Q4 release PDF p5](https://corporate.walmart.com/content/dam/corporate/documents/newsroom/2026/02/19/walmart-releases-q4-fy26-earnings/q4-fy26-earnings-release.pdf), [SEC 8-K accession 0000104169-26-000032](https://www.sec.gov/Archives/edgar/data/104169/000010416926000032/0000104169-26-000032-index.htm) | FY27 Q1 실적 발표 전 연결 가이던스 |
| `wmt_actual_fy27q1_presentation_20260521` | [회사 FY27 Q1 presentation PDF pp7, 29](https://corporate.walmart.com/content/dam/corporate/documents/newsroom/2026/05/21/walmart-releases-q1-fy27-earnings/q1-fy27-earnings-presentation.pdf), [SEC 8-K accession 0000104169-26-000095](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/0000104169-26-000095-index.htm) | 같은 정의의 실제치 및 non-GAAP 대사 |
| `wmt_actual_fy27q1_release_20260521` | [회사 FY27 Q1 release PDF p1](https://corporate.walmart.com/content/dam/corporate/documents/newsroom/2026/05/21/walmart-releases-q1-fy27-earnings/q1-fy27-earnings-release.pdf), 같은 SEC accession | 회사가 설명한 실적 맥락, 정의 충돌 점검 |

SEC의 접수 기록은 2월 19일 06:59:55 EST와 5월 21일 06:59:53 EDT를 보여준다. 회사의 5월 [사전 발표 안내](https://corporate.walmart.com/news/2026/05/14/walmart-to-host-first-quarter-earnings-conference-call-may-21-2026.html)는 06:00 CDT 자료 공개를 예고했다. Ledger의 `first_public_at` 07:00 ET는 **보수적 예정 공개시각 경계**다. 공개된 정확한 초를 관찰한 값이라고 주장하지 않는다. 판단 cutoff는 두 날짜의 발표 이후다. 2월 당시 비교 기준에는 5월 실제치를 포함하지 않는다.

SHA-256은 2026-09-29에 공식 회사 PDF의 수신 바이트로 계산했다. `source_ledger.csv`가 각각의 `retrieved_at`·hash·`snapshot_id`를 보존한다. 9월 수신 PDF와 2월·5월 최초 공개 PDF의 바이트 동일성은 별도로 증명하지 못했다. 같은 숫자와 기간·지표 정의는 SEC에 furnished된 당시 각 8-K exhibit locator에서 대조했다. 원문 PDF나 웹 HTML은 저장소에 보관·재배포하지 않는다. [회사 사이트 이용약관](https://corporate.walmart.com/terms-of-use)은 콘텐츠의 개인·비상업 사용과 제3자 제공 제한을 두므로, 이 case는 원문 locator와 적은 수의 숫자 사실만 기록한다. `transformation_right=YES`는 수치 사실의 개인 연구용 전사 범위로만 해석하며 원문 콘텐츠 재배포 허가를 뜻하지 않는다.

## 같은 정의의 비교

`basis_consolidated_net_sales_yoy_cc_pct_v1`: 2월 문서의 **consolidated net sales (cc)** 성장률 범위 +3.5~+4.5%와 5월 presentation의 같은 순매출 (cc) 실제 +5.7%를 대조한다. 5월 release 헤드라인의 **total revenue (cc) +5.9%**는 범위가 다르므로 제외한다.

`basis_consolidated_operating_income_yoy_cc_pct_v1`: 2월 문서의 **operating income (cc)** 성장률 +4.0~+6.0%와 5월 presentation의 **비조정 operating income (cc) +2.5%**를 대조한다. 보고 기준 +5.0%와 **조정** 고정환율 +5.1%는 다른 지표다. 2월 문서의 가이던스는 non-GAAP 기준이며 전년 비교 기준을 조정할 수 있다고 밝힌다. 이 지표의 FY26 Q1 전년 분모는 presentation에서 보고 및 조정 모두 USD 7,135m로 일치한다. 실제의 비조정 cc 표를 사용한다.

`basis_consolidated_adjusted_diluted_eps_usd_per_share_v1`: 2월 문서의 **adjusted EPS** USD 0.63~0.65와 5월 실제 **adjusted EPS** USD 0.66을 대조한다. GAAP EPS USD 0.67은 제외한다.

모두 2026-02-01~2026-04-30의 Walmart 연결 범위다. `PCT`는 100배 표시된 성장률이고 차이는 percentage point다. `USD_PER_SHARE`는 달러/주다. 원천의 표시 반올림을 보존하며 더 세밀한 실제값을 역산하지 않는다.

2월 19일 가이던스는 FY27 Q1이 **시작한 뒤** 공개됐다. 따라서 분기 시작 전 고정 예측이라고 부르지 않는다. 5월 21일 결과보다 먼저 공개된 company guidance vintage라는 범위에서만 비교한다.

각 가이던스 하단·상단 행은 `forecast_versions.csv`의 `driver_or_assumption_id`로 원천 `source_id`를, `source_snapshot_id`·`source_content_sha256`·`source_first_public_at`으로 ledger의 정확한 receipt를 참조한다. `version_id`는 `versions.csv`의 `PUBLIC_TARGET_OR_GUIDANCE`와 연결된다. `created_at`은 가이던스 행을 분석 case에 입력한 정확한 시각을 보존하지 못해 공란이다. 원천 공개시각으로 대체하지 않는다. 세 실제값은 `raw_facts.csv`의 source fact ID와 receipt를 통해 Core의 `normalized_actuals.csv`까지 연결한다. 재현 스크립트가 이 관계를 검사한다.

5월 release는 연료비 상승이 보고 영업이익 성장률에 약 250bp 부담을 주었다고 설명한다. 2월 당시 연료비 예상치와 실제 차이가 공개되지 않았으므로, 이 250bp를 가이던스 대비 미달의 원인효과로 대입하지 않는다. 순매출·영업이익·EPS의 범위 밖 차이는 전액 **미설명 잔차**로 둔다.
