DROP VIEW IF EXISTS orders_summary;

CREATE VIEW orders_summary AS
SELECT
    order_id,
    MAX(order_status) AS order_status,
    MAX(order_purchase_timestamp) AS order_purchase_timestamp,
    MAX(order_approved_at) AS order_approved_at,
    MAX(order_delivered_carrier_date) AS order_delivered_carrier_date,
    MAX(order_delivered_customer_date) AS order_delivered_customer_date,
    MAX(order_estimated_delivery_date) AS order_estimated_delivery_date,
    MAX(customer_state) AS customer_state,
    MAX(customer_city) AS customer_city,

    COUNT(DISTINCT seller_id) AS distinct_sellers,
    COUNT(DISTINCT product_id) AS distinct_products,
    SUM(price) AS order_total_price,
    SUM(freight_value) AS order_total_freight,

    (ARRAY_AGG(product_category_name_english ORDER BY price DESC))[1] AS primary_category,
    (ARRAY_AGG(seller_id ORDER BY price DESC))[1] AS primary_seller_id,
    (ARRAY_AGG(seller_state ORDER BY price DESC))[1] AS primary_seller_state,

    BOOL_OR(is_late) AS is_late,
    MAX(days_late) AS days_late,
    MAX(last_mile_days) AS last_mile_days,
    MAX(total_fulfillment_days) AS total_fulfillment_days

FROM order_journey
GROUP BY order_id;