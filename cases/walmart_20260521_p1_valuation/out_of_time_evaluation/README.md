# 기준시점 이후 outcome 검증

**Forecast origin:** 2026-05-21 23:59:59 EDT. FY27 Q2에 관해 이때 공개된 것은 [Q1 발표의 Q2 가이던스 범위](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)다. 이를 분석가가 만든 전망 또는 P1 DCF의 검증값으로 부르지 않는다.

**나중에 관측된 결과:** [2026-08-20 FY27 Q2 8-K와 EX-99.1](https://www.sec.gov/Archives/edgar/data/104169/000010416926000145/0000104169-26-000145-index.htm)은 origin 이후 자료다. 수집할 때 별도 source ledger/version으로 보존하고 main case의 2026-05-21 역사적 사실·가정으로 소급하지 않는다. [2026-08-28 FY27 Q2 10-Q](https://www.sec.gov/Archives/edgar/data/104169/000010416926000154/0000104169-26-000154-index.html)도 origin 이후다.

별도 [Q2 수신 영수증](source_receipt.json)에 SEC 접수번호, 보수적인 공개 경계, 수집시각과 수신 HTML SHA-256을 기록했다. 원문은 저장하거나 재배포하지 않는다. 9월에 수신한 바이트가 8월 공개 첫 순간의 바이트와 같다는 증거는 없다.

## 같은 정의로 한정한 결과 점검

| Q2 FY27 연결 지표 | 5월 21일 회사 가이던스 | 8월 20일 발표 실제 | 범위 대비 |
|---|---:|---:|---|
| 순매출 고정환율 전년비 성장률 | +4.0~+5.0% | +5.0% | 상단과 동일 |
| 조정 희석 EPS | USD 0.72~0.74 | USD 0.81 | 상단보다 USD 0.07 높음 |

`[F]` 가이던스는 [5월 21일 발표자료의 Q2 전망표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)에, 실제는 [8월 20일 발표자료의 연결 고정환율 순매출 조정표와 EPS 조정표](https://www.sec.gov/Archives/edgar/data/104169/000010416926000145/earningsreleasefy27q2.htm)에 있다. `[D]` USD 0.07은 표시된 실제 EPS에서 가이던스 상단을 뺀 값이다. 순매출은 공시 표시 정밀도에서만 상단과 같다. 회사 전망의 범위 중간값을 사후 분석가 예측으로 만들지 않는다. 조정 영업이익 전망의 본문과 표가 서로 다른 표현을 사용해 이 점검에서는 제외했다.

비교는 같은 연결 그룹·회계분기·통화·고정환율/조정 정의의 범위 끝점에 대해서만 수행한다. Q2 공개 가이던스의 순매출 고정환율 성장률, 영업이익 고정환율 성장률, 조정 EPS는 각기 정의가 다르므로 reported 매출·GAAP 영업이익·GAAP EPS를 실제치로 치환하지 않는다. 범위 중간값을 사전 전망으로 만들지 않으며 차이의 원인을 근거 없이 귀속하지 않는다.

이 검증은 **공개 가이던스의 제한된 outcome analysis**다. 독립적인 분석가 operating forecast, FCF 또는 DCF value의 out-of-time 정확도는 그 경로가 5월 21일 입력으로 freeze되고 이후 같은 정의의 실제치가 나와야 측정할 수 있다. 현재 그 forecast origin이 없으므로 P1 valuation validation gate는 `WITHHELD`다.
