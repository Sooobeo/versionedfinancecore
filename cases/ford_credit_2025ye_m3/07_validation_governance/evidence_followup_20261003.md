# Ford Credit 공개 신용근거 보강 — 2026-10-03

상태: 자동 재현·근거 탐색. 독립적인 사람의 검토가 아니며, `FEASIBILITY_ONLY` / `WITHHELD` 유지.

## 이번에 닫은 실행 공백

공통 `build-case`의 M3 출력이 Core가 정규화한 원래 36개 사실을 소비한다. 회사 공시상 liquidity bridge, debt face-to-carrying bridge, principal maturity 합계를 독립적으로 대사하며 원 fact ID를 보존한다. 이는 원문 산술 검증을 위한 재계산이지 별도 baseline 생성이 아니다. 연간 bucket은 지급일로 바뀌지 않고, 시설 잔여약정은 가용현금으로 바뀌지 않는다.

법인·시설 register와 추가 `public_terms.csv`도 출력에 포함한다. 비어 있는 금액은 `UNKNOWN`이며 통화·단위가 없는 금액행, 중복 ID, 미등록 source/entity/instrument, cutoff 이후 근거를 거부한다. 공개조건은 채무자 가용현금·drawability 수치의 입력으로 자동 승격되지 않는다.

## 원문 재확보와 vintage 한계

확인한 공식 원문은 [Ford Credit 2025 10-K](https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/fmcc-20251231.htm)의 MD&A Liquidity 및 Note 6/9다. [동일 accession의 filing index](https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/0000038009-26-000010-index.htm)를 통해 원 filing을 식별한다.

2026-10-03 재조회 HTML의 SHA-256은 `4292198aa84f10883ce8e903a704b06a4123e6fdf70844cdfd4fc2fc9a8fa513`으로 기존 receipt와 다르다. 원래 HTML을 보관하지 않았으므로 byte 차이 원인을 단정하거나 과거 본문 불변을 증명할 수 없다. 새 locator receipt만 append하고 기존 receipt와 36개 raw fact는 그대로 보존했다. 최초공개 bound는 원 filing에 대한 기존 보수적 시각이고, 새 조회·재확인 시각과 구분된다. 이는 완전한 historical-content 검증을 뜻하지 않는다. 추가 term마다 이 한계를 남겼고 원문 전체는 저장하지 않았다.

기존 note와 register에는 ABS 만기 집중, 자회사 시설 규모·가용액, 순자산 조건과 보증·recourse 구분이 이미 있었다. 이번에 추가한 eligible-asset 부족 및 시설 만기연도는 같은 accession에서 확인한 보충 관측이며 과거 byte identity 미검증 상태다.

## 사람 검토와 별개로 남는 근거 제약

- 법적 모회사 cash account별 잔액·upstream 제한이 없어 consolidated cash를 obligor accessible cash로 치환할 수 없다.
- 채권 회수·신규 취급·만기지급의 실제 날짜와 최소 운영현금이 없어 2026 CFADS, 최초 부족일, refinancing gap을 만들 수 없다.
- 시설별 eligible assets, hedge, 성과 threshold, draw·cure 조건을 합칠 자료가 부족하다. 발표된 가용액이 parent의 확정 인출액은 아니다.
- 담보권 순위·집행·법인별 value pool과 allowed claim 전체가 없어 recovery 수치도 만들지 않는다.

테스트는 오프라인 registered fact 및 별도 합성 산술 fixture만 사용한다. 이후 공시를 현재 cutoff로 소급하지 않으며 이번 보강은 승인·외부등급·법률의견이 아니다.
