"""Power BI 프로젝트(PBIP: TMDL 의미 모델 + PBIR 보고서) 생성기.

실행: python pipeline/gen_pbip.py
결과: powerbi/SellerDashboard.pbip (Power BI Desktop에서 열고 '새로 고침')
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "powerbi"
NAME = "SellerDashboard"
MART_DIR = str((ROOT / "data" / "mart").resolve())
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
NS = uuid.UUID("6f1c2b4e-1d2a-4c3b-9e8f-0a1b2c3d4e5f")


def gid(key: str) -> str:
    """재실행해도 같은 lineageTag가 나오도록 이름 기반 UUID."""
    return str(uuid.uuid5(NS, key))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def wjson(path: Path, obj) -> None:
    write(path, json.dumps(obj, ensure_ascii=False, indent=2))


# ───────────────────────── 의미 모델 (TMDL) ─────────────────────────
# (컬럼명, 데이터형, 형식, 요약, 숨김)
TABLES = {
    "fact_order_seller": [
        ("order_id", "string", None, "none", True),
        ("seller_id", "string", None, "none", True),
        ("customer_unique_id", "string", None, "none", True),
        ("customer_state", "string", None, "none", False),
        ("purchase_date", "dateTime", "yyyy-mm-dd", "none", True),
        ("order_status", "string", None, "none", False),
        ("item_cnt", "int64", "#,0", "sum", True),
        ("gmv", "double", "#,0", "sum", True),
        ("freight", "double", "#,0", "sum", True),
        ("main_category", "string", None, "none", False),
        ("lead_time_days", "double", "0.0", "none", True),
        ("handoff_days", "double", "0.0", "none", True),
        ("is_late_delivery", "int64", "0", "none", True),
        ("is_late_handoff", "int64", "0", "none", True),
        ("delivery_status", "string", None, "none", False),
        ("is_canceled", "int64", "0", "none", True),
        ("review_score", "int64", "0", "none", False),
        ("is_low_review", "int64", "0", "none", True),
        ("complaint_type", "string", None, "none", False),
        ("is_multi_seller_order", "int64", "0", "none", True),
    ],
    "dim_seller": [
        ("seller_id", "string", None, "none", True),
        ("seller_code", "string", None, "none", False),
        ("seller_city", "string", None, "none", False),
        ("seller_state", "string", None, "none", False),
        ("first_order_date", "dateTime", "yyyy-mm-dd", "none", False),
        ("cohort_month", "dateTime", "yyyy-mm", "none", False),
        ("total_orders", "int64", "#,0", "sum", False),
    ],
    "dim_date": [
        ("date", "dateTime", "yyyy-mm-dd", "none", False),
        ("year", "int64", "0", "none", False),
        ("month", "int64", "0", "none", False),
        ("year_month", "string", None, "none", False),
        ("month_start", "dateTime", "yyyy-mm", "none", False),
        ("quarter", "string", None, "none", False),
        ("week_start", "dateTime", "yyyy-mm-dd", "none", False),
    ],
    "seller_scorecard": [
        ("seller_id", "string", None, "none", True),
        ("orders_3m", "int64", "#,0", "sum", False),
        ("gmv_3m", "double", "#,0", "sum", False),
        ("late_handoff_rate", "double", "0.0%", "none", False),
        ("late_delivery_rate", "double", "0.0%", "none", False),
        ("avg_review", "double", "0.00", "none", False),
        ("low_review_rate", "double", "0.0%", "none", False),
        ("cancel_rate", "double", "0.0%", "none", False),
        ("gmv_rank", "int64", "0", "none", False),
        ("seller_grade", "string", None, "none", False),
    ],
}

# 측정값: (이름, DAX, 형식, 표시 폴더)  — 모두 fact_order_seller 테이블에 둔다
F = "fact_order_seller"
MEASURES = [
    ("매출", "SUM(fact_order_seller[gmv])", "#,0", "1 규모"),
    ("주문 건수", "COUNTROWS(fact_order_seller)", "#,0", "1 규모"),
    ("활성 판매자 수", "DISTINCTCOUNT(fact_order_seller[seller_id])", "#,0", "1 규모"),
    ("신규 판매자 수",
     "CALCULATE(COUNTROWS(dim_seller), TREATAS(VALUES(dim_date[month_start]), dim_seller[cohort_month]))",
     "#,0", "1 규모"),
    ("객단가", "DIVIDE([매출], [주문 건수])", "#,0", "1 규모"),
    ("매출 전월 대비",
     "VAR cur = [매출]\nVAR prev = CALCULATE([매출], DATEADD(dim_date[date], -1, MONTH))\nRETURN DIVIDE(cur - prev, prev)",
     "+0.0%;-0.0%;0.0%", "1 규모"),
    ("배송 지연율", "AVERAGE(fact_order_seller[is_late_delivery])", "0.0%", "2 운영 품질"),
    ("출고 지연율", "AVERAGE(fact_order_seller[is_late_handoff])", "0.0%", "2 운영 품질"),
    ("평균 리드타임(일)", "AVERAGE(fact_order_seller[lead_time_days])", "0.0", "2 운영 품질"),
    ("평균 출고 소요(일)", "AVERAGE(fact_order_seller[handoff_days])", "0.0", "2 운영 품질"),
    ("취소율", "AVERAGE(fact_order_seller[is_canceled])", "0.0%", "2 운영 품질"),
    ("평균 평점", "AVERAGE(fact_order_seller[review_score])", "0.00", "3 고객 반응"),
    ("저평점 비율", "AVERAGE(fact_order_seller[is_low_review])", "0.0%", "3 고객 반응"),
    ("불만 건수",
     "CALCULATE(COUNTROWS(fact_order_seller), KEEPFILTERS(NOT ISBLANK(fact_order_seller[complaint_type])))",
     "#,0", "3 고객 반응"),
    ("1천 주문당 불만", "DIVIDE([불만 건수], [주문 건수]) * 1000", "0.0", "3 고객 반응"),
    ("지연 배송 저평점 비율",
     "CALCULATE([저평점 비율], fact_order_seller[delivery_status] = \"지연 배송\")", "0.0%", "3 고객 반응"),
    ("정시 배송 저평점 비율",
     "CALCULATE([저평점 비율], fact_order_seller[delivery_status] = \"정시 배송\")", "0.0%", "3 고객 반응"),
    ("성과표 판매자 수", "COUNTROWS(seller_scorecard)", "#,0", "4 성과표"),
    ("성과표 출고 지연율", "AVERAGE(seller_scorecard[late_handoff_rate])", "0.0%", "4 성과표"),
    ("성과표 저평점 비율", "AVERAGE(seller_scorecard[low_review_rate])", "0.0%", "4 성과표"),
    ("성과표 매출", "SUM(seller_scorecard[gmv_3m])", "#,0", "4 성과표"),
]

M_TYPE = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date"}


def m_partition(table: str, cols) -> str:
    types = ", ".join(f'{{"{c}", {M_TYPE[t]}}}' for c, t, *_ in cols)
    allcols = ", ".join(f'"{c}"' for c, *_ in cols)
    lines = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "\\{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f"    Blanks = Table.ReplaceValue(Promoted, \"\", null, Replacer.ReplaceValue, {{{allcols}}}),",
        f'    Typed = Table.TransformColumnTypes(Blanks, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]
    return "\n".join("\t\t\t\t" + ln for ln in lines)


def table_tmdl(table: str, cols) -> str:
    out = [f"table {table}", f"\tlineageTag: {gid(table)}"]
    if table == "dim_date":
        out.append("\tdataCategory: Time")
    out.append("")
    if table == F:
        for name, dax, fmt, folder in MEASURES:
            body = dax.split("\n")
            if len(body) == 1:
                out.append(f"\tmeasure '{name}' = {body[0]}")
            else:
                out.append(f"\tmeasure '{name}' =")
                out += [f"\t\t\t{ln}" for ln in body]
            out += [f"\t\tformatString: {fmt}", f"\t\tdisplayFolder: {folder}",
                    f"\t\tlineageTag: {gid(table + '/m/' + name)}", ""]
    for c, t, fmt, summ, hidden in cols:
        out.append(f"\tcolumn {c}")
        out.append(f"\t\tdataType: {t}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        if hidden:
            out.append("\t\tisHidden")
        if table == "dim_date" and c == "date":
            out.append("\t\tisKey")
        out += [f"\t\tlineageTag: {gid(table + '/' + c)}", f"\t\tsummarizeBy: {summ}",
                f"\t\tsourceColumn: {c}", "", "\t\tannotation SummarizationSetBy = Automatic", ""]
    out += [f"\tpartition {table} = m", "\t\tmode: import", "\t\tsource =", m_partition(table, cols), ""]
    return "\n".join(out) + "\n"


RELATIONSHIPS = [
    ("fact_order_seller.seller_id", "dim_seller.seller_id"),
    ("fact_order_seller.purchase_date", "dim_date.date"),
    ("seller_scorecard.seller_id", "dim_seller.seller_id"),
]


def semantic_model(base: Path) -> None:
    sm = base / f"{NAME}.SemanticModel"
    wjson(sm / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                    "version": "4.2", "settings": {}})
    wjson(sm / ".platform", {"$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
                             "metadata": {"type": "SemanticModel", "displayName": NAME},
                             "config": {"version": "2.0", "logicalId": gid("sm")}})
    d = sm / "definition"
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    model = ["model Model", "\tculture: ko-KR", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: ko-KR", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
             "", "	annotation __PBI_TimeIntelligenceEnabled = 0", "",
             f"	annotation PBI_QueryOrder = {json.dumps(['DataFolder', *TABLES.keys()])}", ""]
    model += [f"ref table {t}" for t in TABLES] + [""]
    write(d / "model.tmdl", "\n".join(model))
    folder = MART_DIR.replace('"', '""')
    write(d / "expressions.tmdl",
          f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
          f"\tlineageTag: {gid('DataFolder')}\n\n\tannotation PBI_ResultType = Text\n")
    rel = []
    for frm, to in RELATIONSHIPS:
        rel += [f"relationship {gid(frm + '>' + to)}", f"\tfromColumn: {frm}", f"\ttoColumn: {to}", ""]
    write(d / "relationships.tmdl", "\n".join(rel))
    for t, cols in TABLES.items():
        write(d / "tables" / f"{t}.tmdl", table_tmdl(t, cols))


# ───────────────────────── 보고서 (PBIR) ─────────────────────────
def lit(v) -> dict:
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def fld(ref: str) -> tuple[dict, str]:
    """'T.col' → 열, 'T.[측정값]' → 측정값."""
    table, prop = ref.split(".", 1)
    if prop.startswith("["):
        prop = prop[1:-1]
        return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}, f"{table}.{prop}"
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}, f"{table}.{prop}"


COLORS = {"bg": "#FFFFFF", "accent": "#E8392B", "dark": "#1F2937", "muted": "#6B7280"}


def visual(name, vtype, x, y, w, h, roles: dict, title=None, sort=None, objects=None, z=0):
    qs = {}
    for role, refs in roles.items():
        projs = []
        for r in refs:
            r, _, disp = r.partition("|")
            f, qr = fld(r)
            proj = {"field": f, "queryRef": qr, "nativeQueryRef": qr.split(".", 1)[1]}
            if disp:
                proj["displayName"] = disp
            projs.append(proj)
        qs[role] = {"projections": projs}
    v = {"visualType": vtype, "query": {"queryState": qs}, "drillFilterOtherVisuals": True}
    if sort:
        f, _ = fld(sort[0])
        v["query"]["sortDefinition"] = {"sort": [{"field": f, "direction": sort[1]}], "isDefaultSort": False}
    vco = {}
    if title:
        vco["title"] = [{"properties": {"show": lit(True), "text": lit(title), "fontSize": lit(12),
                                        "fontColor": {"solid": {"color": lit(COLORS["dark"])}}}}]
    vco["border"] = [{"properties": {"show": lit(True), "color": {"solid": {"color": lit("#E5E7EB")}}, "radius": lit(8)}}]
    v["visualContainerObjects"] = vco
    if objects:
        v["objects"] = objects
    return {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
            "name": name, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
            "visual": v}


def textbox(name, x, y, w, h, text, size=20, bold=True, color=None, z=0):
    run = {"value": text, "textStyle": {"fontSize": f"{size}pt", "fontWeight": "bold" if bold else "normal",
                                        "color": color or COLORS["dark"]}}
    return {"$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
            "name": name, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z},
            "visual": {"visualType": "textbox",
                       "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [run]}]}}]},
                       "drillFilterOtherVisuals": True}}


def slicer(name, x, y, w, h, ref, title):
    obj = {"data": [{"properties": {"mode": lit("Dropdown")}}],
           "header": [{"properties": {"show": lit(False)}}]}
    return visual(name, "slicer", x, y, w, h, {"Values": [ref]}, title=title, objects=obj)


def cards(prefix, refs_titles, y, x0=20, w=240, gap=12):
    out = []
    for i, (ref, t) in enumerate(refs_titles):
        obj = {"labels": [{"properties": {"labelDisplayUnits": lit(1), "fontSize": lit(26)}}],
               "categoryLabels": [{"properties": {"show": lit(False)}}]}
        out.append(visual(f"{prefix}{i}", "card", x0 + i * (w + gap), y, w, 100, {"Values": [ref]}, title=t, objects=obj))
    return out


PAGES = [
    ("p1overview", "1 판매자 현황", [
        textbox("p1title", 20, 10, 860, 50, "판매자 현황  ·  2017.01 ~ 2018.08 (Olist 공개 데이터)"),
        slicer("p1s1", 900, 10, 175, 60, "dim_date.year_month", "기간"),
        slicer("p1s2", 1085, 10, 175, 60, "dim_seller.seller_state", "판매자 지역"),
        *cards("p1c", [(f"{F}.[매출]", "매출 (R$)"), (f"{F}.[주문 건수]", "주문 건수"),
                       (f"{F}.[활성 판매자 수]", "활성 판매자"), (f"{F}.[배송 지연율]", "배송 지연율"),
                       (f"{F}.[평균 평점]", "평균 평점")], y=80),
        visual("p1v1", "lineChart", 20, 195, 615, 255,
               {"Category": ["dim_date.month_start"], "Y": [f"{F}.[매출]"]}, title="월별 매출"),
        visual("p1v2", "clusteredColumnChart", 645, 195, 615, 255,
               {"Category": ["dim_date.month_start"], "Y": [f"{F}.[활성 판매자 수]", f"{F}.[신규 판매자 수]"]},
               title="월별 활성·신규 판매자"),
        visual("p1v3", "clusteredBarChart", 20, 460, 615, 250,
               {"Category": ["dim_seller.seller_state"], "Y": [f"{F}.[매출]"]}, title="판매자 지역별 매출",
               sort=(f"{F}.[매출]", "Descending")),
        visual("p1v4", "lineChart", 645, 460, 615, 250,
               {"Category": ["dim_date.month_start"], "Y": [f"{F}.[배송 지연율]", f"{F}.[출고 지연율]"]},
               title="월별 배송·출고 지연율"),
    ]),
    ("p2scorecard", "2 판매자 성과 관리", [
        textbox("p2title", 20, 10, 860, 50, "판매자 성과표  ·  최근 3개월(2018.06~08), 주문 10건 이상"),
        slicer("p2s1", 900, 10, 175, 60, "seller_scorecard.seller_grade", "등급"),
        slicer("p2s2", 1085, 10, 175, 60, "dim_seller.seller_state", "판매자 지역"),
        *cards("p2c", [("fact_order_seller.[성과표 판매자 수]", "대상 판매자"),
                       ("fact_order_seller.[성과표 매출]", "3개월 매출 (R$)"),
                       ("fact_order_seller.[성과표 출고 지연율]", "평균 출고 지연율"),
                       ("fact_order_seller.[성과표 저평점 비율]", "평균 저평점 비율")], y=80, w=302),
        visual("p2v1", "donutChart", 20, 195, 400, 515,
               {"Category": ["seller_scorecard.seller_grade"], "Y": [f"{F}.[성과표 판매자 수]"]},
               title="등급별 판매자 수",
               objects={"labels": [{"properties": {"show": lit(True), "labelStyle": lit("Category, data value")}}]}),
        visual("p2v2", "tableEx", 430, 195, 830, 515,
               {"Values": ["dim_seller.seller_code|판매자", "seller_scorecard.seller_grade|등급",
                           "seller_scorecard.orders_3m|주문(3개월)", "seller_scorecard.gmv_3m|매출(3개월)",
                           "seller_scorecard.late_handoff_rate|출고 지연율", "seller_scorecard.low_review_rate|저평점 비율",
                           "seller_scorecard.avg_review|평균 평점", "seller_scorecard.cancel_rate|취소율"]},
               title="판매자별 성과 (매출 순)", sort=("seller_scorecard.gmv_3m", "Descending")),
    ]),
    ("p3complaint", "3 불만·리뷰 트렌드", [
        textbox("p3title", 20, 10, 860, 50, "불만·리뷰 트렌드  ·  저평점(1~2점) 리뷰를 불만 신호로 사용"),
        slicer("p3s1", 900, 10, 175, 60, "dim_date.year_month", "기간"),
        slicer("p3s2", 1085, 10, 175, 60, "fact_order_seller.main_category", "카테고리"),
        *cards("p3c", [(f"{F}.[저평점 비율]", "저평점 비율"), (f"{F}.[1천 주문당 불만]", "1천 주문당 불만"),
                       (f"{F}.[지연 배송 저평점 비율]", "지연 배송 시 저평점"),
                       (f"{F}.[정시 배송 저평점 비율]", "정시 배송 시 저평점")], y=80, w=302),
        visual("p3v1", "columnChart", 20, 195, 800, 515,
               {"Category": ["dim_date.month_start"], "Series": ["fact_order_seller.complaint_type|불만 유형"],
                "Y": [f"{F}.[불만 건수]"]}, title="월별 불만 유형 (건수)"),
        visual("p3v2", "clusteredBarChart", 830, 195, 430, 250,
               {"Category": ["fact_order_seller.complaint_type"], "Y": [f"{F}.[불만 건수]"]},
               title="불만 유형 순위", sort=(f"{F}.[불만 건수]", "Descending"),
               objects={"labels": [{"properties": {"show": lit(True)}}]}),
        visual("p3v3", "clusteredColumnChart", 830, 455, 430, 255,
               {"Category": ["fact_order_seller.delivery_status"], "Y": [f"{F}.[평균 평점]"]},
               title="배송 상태별 평균 평점", objects={"labels": [{"properties": {"show": lit(True)}}]}),
    ]),
]


def report(base: Path) -> None:
    rp = base / f"{NAME}.Report"
    wjson(rp / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                   "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    wjson(rp / ".platform", {"$schema": f"{SCHEMA}/gitIntegration/platformProperties/2.0.0/schema.json",
                             "metadata": {"type": "Report", "displayName": NAME},
                             "config": {"version": "2.0", "logicalId": gid("report")}})
    d = rp / "definition"
    wjson(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                               "version": "2.0.0"})
    wjson(d / "report.json", {"$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
                              "themeCollection": {}})
    wjson(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": [p[0] for p in PAGES], "activePageName": PAGES[0][0]})
    for pname, display, visuals in PAGES:
        pd = d / "pages" / pname
        wjson(pd / "page.json", {"$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
                                 "name": pname, "displayName": display, "displayOption": "FitToPage",
                                 "height": 720, "width": 1280})
        for v in visuals:
            wjson(pd / "visuals" / v["name"] / "visual.json", v)


def main() -> None:
    target = OUT
    for p in [target / f"{NAME}.SemanticModel" / "definition", target / f"{NAME}.Report" / "definition"]:
        if p.exists():
            shutil.rmtree(p)
    wjson(target / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                    "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                    "settings": {"enableAutoRecovery": True}})
    semantic_model(target)
    report(target)
    print("written:", target / f"{NAME}.pbip")


if __name__ == "__main__":
    main()
