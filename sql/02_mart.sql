-- 02_mart.sql : Power BI용 스타 스키마 (주문×판매자 팩트 + 차원 + 판매자 성과표)
-- 분석 기간: 2017-01-01 ~ 2018-08-31
-- (2016년과 2018-09 이후는 월 주문이 수백 건 이하라 추세를 왜곡해 제외)

-- 저평점(1~2점) 리뷰 불만 유형: 포르투갈어 키워드 규칙, 위에서부터 먼저 맞는 유형 1개
-- v2: 샘플 검수 후 순서 조정(부분 수령을 미수령보다 먼저), '정시 배송' 문맥 제외, 키워드 보강
create or replace macro complaint_type(txt, has_comment) as
  case
    when not has_comment then '코멘트 없음'
    when regexp_matches(txt, 'errad|diferente|outro produto|entregaram outro|entrega outro|veio outro|trocad|somente|apenas (um|uma|1|01|parte)|s[oó] (recebi|veio|foi entregue|chegou)|metade|uma parte|faltou|faltando|falta (o|a|um|uma)|indevid|n[aã]o corresponde|n[aã]o [eé] original')
      then '오배송·구성 누락'
    when regexp_matches(txt, 'n[aã]o (recebi|recebo|chegou|foi entregue|veio)|ainda n[aã]o|aguardando|nunca chegou|n[aã]o entreg|cad[eê] (meu|o) produto')
      then '미수령'
    when regexp_matches(txt, 'atras|demor|lent|prazo') and not regexp_matches(txt, '(no|dentro do|antes do) prazo')
      then '배송 지연'
    when regexp_matches(txt, 'quebrad|defeito|danific|arranh|n[aã]o funciona|parou de funcionar|qualidade|ruim|fr[aá]gil|rasgad|furo|amassad')
      then '품질·파손'
    when regexp_matches(txt, 'cancel|estoque|esgotad|reembolso|estorno|devolu|dinheiro de volta|troca')
      then '취소·환불 요청'
    when regexp_matches(txt, 'resposta|respond|contato|contactar|atendimento|retorno|sem not[ií]cia|n[aã]o tenho not[ií]cia')
      then '판매자 응대 불만'
    else '기타'
  end;

create or replace table fact_order_seller as
with item_agg as (
  select i.order_id, i.seller_id,
         count(*)                         as item_cnt,
         sum(i.price)                     as gmv,
         sum(i.freight_value)             as freight,
         max(i.shipping_limit_at)         as shipping_limit_at,
         arg_max(p.category_en, i.price)  as main_category      -- 가장 비싼 상품의 카테고리
  from stg_items i left join stg_products p using (product_id)
  group by 1, 2
),
seller_cnt as (
  select order_id, count(distinct seller_id) as n_sellers from stg_items group by 1
)
select
  o.order_id, a.seller_id, c.customer_unique_id, c.customer_state,
  cast(o.purchased_at as date)                                   as purchase_date,
  o.order_status,
  a.item_cnt, round(a.gmv, 2) as gmv, round(a.freight, 2) as freight, a.main_category,
  -- 리드타임(일): 주문 → 고객 수령
  case when o.delivered_at is not null
       then round(date_diff('minute', o.purchased_at, o.delivered_at) / 1440.0, 2) end as lead_time_days,
  -- 판매자 출고 소요(일): 결제 승인 → 택배사 인계 (인계가 승인보다 앞선 원본 오류 1,371건은 결측 처리)
  case when o.carrier_at is not null and o.approved_at is not null and o.carrier_at >= o.approved_at
       then round(date_diff('minute', o.approved_at, o.carrier_at) / 1440.0, 2) end   as handoff_days,
  -- 배송 지연: 고객 수령일이 약속일보다 늦음 (배송 완료 건만)
  case when o.delivered_at is not null
       then cast(cast(o.delivered_at as date) > cast(o.estimated_at as date) as int) end as is_late_delivery,
  -- 출고 지연: 택배사 인계가 판매자 출고 기한(shipping_limit)보다 늦음 → 판매자 책임 지표
  case when o.carrier_at is not null
       then cast(o.carrier_at > a.shipping_limit_at as int) end                         as is_late_handoff,
  case when o.delivered_at is null then '미배송·취소'
       when cast(o.delivered_at as date) > cast(o.estimated_at as date) then '지연 배송'
       else '정시 배송' end                                                             as delivery_status,
  cast(o.order_status in ('canceled', 'unavailable') as int)                          as is_canceled,
  r.review_score,
  case when r.review_score is not null then cast(r.review_score <= 2 as int) end       as is_low_review,
  case when r.review_score <= 2 then complaint_type(r.review_text, r.has_comment) end  as complaint_type,
  cast(s.n_sellers > 1 as int)                                                         as is_multi_seller_order
from stg_orders o
join item_agg a using (order_id)
join seller_cnt s using (order_id)
left join stg_customers c using (customer_id)
left join stg_reviews r using (order_id)
where o.purchased_at >= timestamp '2017-01-01' and o.purchased_at < timestamp '2018-09-01';

-- 판매자 차원: 긴 해시 ID 대신 짧은 코드, 첫 판매월(코호트)
create or replace table dim_seller as
with first_sale as (
  select seller_id, min(purchase_date) as first_order_date, count(*) as total_orders
  from fact_order_seller group by 1
)
select s.seller_id,
       'S' || lpad(cast(row_number() over (order by f.first_order_date, s.seller_id) as varchar), 4, '0') as seller_code,
       s.seller_city, s.seller_state,
       f.first_order_date,
       cast(date_trunc('month', f.first_order_date) as date) as cohort_month,
       f.total_orders
from stg_sellers s join first_sale f using (seller_id);

-- 날짜 차원
create or replace table dim_date as
select cast(d as date)                         as date,
       year(d)                                 as year,
       month(d)                                as month,
       strftime(d, '%Y-%m')                    as year_month,
       cast(date_trunc('month', d) as date)    as month_start,
       'Q' || quarter(d)                       as quarter,
       cast(date_trunc('week', d) as date)     as week_start
from range(timestamp '2017-01-01', timestamp '2018-09-01', interval 1 day) t(d);

-- 판매자 성과표: 최근 3개월(2018-06~08), 주문 10건 이상 판매자 대상
create or replace table seller_scorecard as
with base as (
  select seller_id,
         count(*)                         as orders_3m,
         round(sum(gmv), 2)               as gmv_3m,
         avg(is_late_handoff)             as late_handoff_rate,
         avg(is_late_delivery)            as late_delivery_rate,
         avg(review_score)                as avg_review,
         avg(is_low_review)               as low_review_rate,
         avg(is_canceled)                 as cancel_rate
  from fact_order_seller
  where purchase_date >= date '2018-06-01'
  group by 1
  having count(*) >= 10
)
select *,
  rank() over (order by gmv_3m desc) as gmv_rank,
  case
    when late_handoff_rate >= 0.20 or low_review_rate >= 0.25 then 'D 집중 관리'
    when late_handoff_rate >= 0.10 or low_review_rate >= 0.15 then 'C 주의'
    when late_handoff_rate <= 0.05 and avg_review >= 4.3      then 'A 우수'
    else 'B 보통'
  end as seller_grade
from base;
