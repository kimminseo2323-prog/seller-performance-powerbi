-- 01_staging.sql : 원본 CSV → 정제 뷰 (DuckDB)
-- {RAW} 는 build_mart.py 가 data/raw 경로로 치환한다.

create or replace view stg_orders as
select order_id, customer_id, order_status,
       cast(order_purchase_timestamp as timestamp)       as purchased_at,
       cast(order_approved_at as timestamp)              as approved_at,
       cast(order_delivered_carrier_date as timestamp)   as carrier_at,
       cast(order_delivered_customer_date as timestamp)  as delivered_at,
       cast(order_estimated_delivery_date as timestamp)  as estimated_at
from read_csv_auto('{RAW}/olist_orders_dataset.csv', header = true);

create or replace view stg_items as
select order_id, order_item_id, product_id, seller_id,
       cast(shipping_limit_date as timestamp) as shipping_limit_at,
       price, freight_value
from read_csv_auto('{RAW}/olist_order_items_dataset.csv', header = true);

create or replace view stg_products as
select p.product_id,
       coalesce(p.product_category_name, 'unknown') as category_pt,
       coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as category_en
from read_csv_auto('{RAW}/olist_products_dataset.csv', header = true) p
left join read_csv_auto('{RAW}/product_category_name_translation.csv', header = true) t
  on p.product_category_name = t.product_category_name;

create or replace view stg_sellers as
select seller_id, seller_city, seller_state
from read_csv_auto('{RAW}/olist_sellers_dataset.csv', header = true);

create or replace view stg_customers as
select customer_id, customer_unique_id, customer_state
from read_csv_auto('{RAW}/olist_customers_dataset.csv', header = true);

-- 한 주문에 리뷰가 여러 개인 경우 가장 최근 응답 1건만 사용
create or replace view stg_reviews as
select * exclude (rn) from (
  select review_id, order_id, review_score,
         lower(coalesce(review_comment_title, '') || ' ' || coalesce(review_comment_message, '')) as review_text,
         review_comment_message is not null as has_comment,
         row_number() over (partition by order_id
                            order by cast(review_answer_timestamp as timestamp) desc, review_id) as rn
  from read_csv_auto('{RAW}/olist_order_reviews_dataset.csv', header = true)
) where rn = 1;
