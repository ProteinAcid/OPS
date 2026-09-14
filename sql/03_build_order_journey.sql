DROP TABLE IF EXISTS order_journey;

CREATE TABLE order_journey AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_status,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,

    c.customer_state,
    c.customer_city,
    c.customer_zip_code_prefix,

    oi.seller_id,
    s.seller_state,
    s.seller_city,
    s.seller_zip_code_prefix,

    oi.product_id,
    p.product_category_name,
    pt.product_category_name_english,
    p.product_weight_g,

    oi.price,
    oi.freight_value,

    CASE 
        WHEN o.order_delivered_customer_date IS NOT NULL 
             AND o.order_delivered_customer_date > o.order_estimated_delivery_date 
        THEN TRUE 
        ELSE FALSE 
    END AS is_late,

    EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) AS days_late,

    EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_delivered_carrier_date)) AS last_mile_days,

    EXTRACT(DAY FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) AS total_fulfillment_days

FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN sellers s ON oi.seller_id = s.seller_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name;