"""원본 Olist CSV → DuckDB SQL → Power BI용 마트 CSV + 데이터 품질 리포트.

실행: python pipeline/build_mart.py
결과: data/mart/*.csv, docs/data_quality.md
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MART = ROOT / "data" / "mart"
SQL_FILES = [ROOT / "sql" / "01_staging.sql", ROOT / "sql" / "02_mart.sql"]
TABLES = ["fact_order_seller", "dim_seller", "dim_date", "seller_scorecard"]


def run_sql(con: duckdb.DuckDBPyConnection) -> None:
    raw = RAW.as_posix()
    for f in SQL_FILES:
        con.execute(f.read_text(encoding="utf-8").replace("{RAW}", raw))


def quality_checks(con: duckdb.DuckDBPyConnection) -> list[tuple[str, str, bool]]:
    """(검사 항목, 결과 값, 통과 여부) 목록."""
    q = lambda s: con.execute(s).fetchone()[0]
    checks: list[tuple[str, str, bool]] = []

    dup = q("select count(*) - count(distinct order_id || seller_id) from fact_order_seller")
    checks.append(("팩트 키(주문×판매자) 중복", f"{dup}건", dup == 0))

    orphan = q("select count(*) from fact_order_seller f left join dim_seller d using (seller_id) where d.seller_id is null")
    checks.append(("판매자 차원에 없는 팩트 행", f"{orphan}건", orphan == 0))

    raw_gmv = q("""select sum(i.price) from stg_items i join stg_orders o using (order_id)
                   where o.purchased_at >= timestamp '2017-01-01' and o.purchased_at < timestamp '2018-09-01'""")
    mart_gmv = q("select sum(gmv) from fact_order_seller")
    diff = abs(raw_gmv - mart_gmv)
    checks.append(("매출(GMV) 원본 대비 차이", f"{diff:,.2f} (원본 {raw_gmv:,.0f})", diff < 1.0))

    miss_deliv = q("""select count(*) from fact_order_seller
                      where order_status = 'delivered' and lead_time_days is null""")
    checks.append(("배송완료인데 수령일 없음", f"{miss_deliv}건 (지연율 계산에서 제외)", True))

    neg = q("select count(*) from fact_order_seller where lead_time_days < 0 or handoff_days < 0")
    checks.append(("음수 리드타임 남은 행", f"{neg}건", neg == 0))
    flipped = q("""select count(*) from fact_order_seller f join stg_orders o using (order_id)
                   where o.carrier_at < o.approved_at""")
    checks.append(("택배 인계가 결제 승인보다 앞선 원본 오류", f"{flipped:,}건 (출고 소요일만 결측 처리)", True))

    no_review = q("select avg(case when review_score is null then 1.0 else 0 end) from fact_order_seller")
    checks.append(("리뷰 없는 주문 비율", f"{no_review:.1%}", True))

    multi = q("select avg(is_multi_seller_order) from fact_order_seller")
    checks.append(("여러 판매자 주문 비율", f"{multi:.1%} (리뷰가 주문 단위라 판매자별로 같은 점수 귀속)", True))

    covered = q("""select avg(case when complaint_type not in ('기타','코멘트 없음') then 1.0 else 0 end)
                   from fact_order_seller where complaint_type is not null and complaint_type <> '코멘트 없음'""")
    checks.append(("불만 유형 규칙 분류율(코멘트 있는 저평점 중)", f"{covered:.1%}", covered >= 0.6))
    return checks


def export(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    MART.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in TABLES:
        out = (MART / f"{t}.csv").as_posix()
        con.execute(f"copy {t} to '{out}' (header, delimiter ',', dateformat '%Y-%m-%d')")
        counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
    return counts


def write_report(counts: dict[str, int], checks: list[tuple[str, str, bool]], con) -> None:
    lines = [
        "# 데이터 품질 리포트",
        "",
        f"생성: {dt.datetime.now():%Y-%m-%d %H:%M} · `python pipeline/build_mart.py` 실행 시 자동 갱신",
        "",
        "## 마트 테이블 행 수",
        "| 테이블 | 행 수 |",
        "|---|---|",
        *[f"| {t} | {n:,} |" for t, n in counts.items()],
        "",
        "## 검사 결과",
        "| 항목 | 결과 | 상태 |",
        "|---|---|---|",
        *[f"| {name} | {val} | {'통과' if ok else '확인 필요'} |" for name, val, ok in checks],
        "",
        "## 불만 유형 분포 (저평점 1~2점)",
        "| 유형 | 건수 | 비율 |",
        "|---|---|---|",
    ]
    rows = con.execute("""select complaint_type, count(*) n, count(*) * 1.0 / sum(count(*)) over () r
                          from fact_order_seller where complaint_type is not null group by 1 order by 2 desc""").fetchall()
    lines += [f"| {t} | {n:,} | {r:.1%} |" for t, n, r in rows]
    rows = con.execute("select seller_grade, count(*) from seller_scorecard group by 1 order by 1").fetchall()
    lines += ["", "## 판매자 등급 분포 (2018-06~08, 주문 10건 이상)", "| 등급 | 판매자 수 |", "|---|---|"]
    lines += [f"| {g} | {n:,} |" for g, n in rows]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "data_quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    con = duckdb.connect()
    run_sql(con)
    checks = quality_checks(con)
    counts = export(con)
    write_report(counts, checks, con)
    failed = [c for c in checks if not c[2]]
    for name, val, ok in checks:
        print(("OK  " if ok else "FAIL"), name, val)
    print("rows:", counts)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
