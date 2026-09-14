\copy customers FROM 'C:/Users/n5463/OPS/data/raw/olist_customers_dataset.csv' DELIMITER ',' CSV HEADER;

\copy sellers FROM 'C:/Users/n5463/OPS/data/raw/olist_sellers_dataset.csv' DELIMITER ',' CSV HEADER;

\copy products FROM 'C:/Users/n5463/OPS/data/raw/olist_products_dataset.csv' DELIMITER ',' CSV HEADER;

\copy product_category_translation FROM 'C:/Users/n5463/OPS/data/raw/product_category_name_translation.csv' DELIMITER ',' CSV HEADER;

\copy orders FROM 'C:/Users/n5463/OPS/data/raw/olist_orders_dataset.csv' DELIMITER ',' CSV HEADER;

\copy order_items FROM 'C:/Users/n5463/OPS/data/raw/olist_order_items_dataset.csv' DELIMITER ',' CSV HEADER;

\copy order_payments FROM 'C:/Users/n5463/OPS/data/raw/olist_order_payments_dataset.csv' DELIMITER ',' CSV HEADER;

psql -U postgres -d ops_project -c "\copy order_reviews FROM 'C:/Users/n5463/OPS/data/raw/olist_order_reviews_dataset.csv' DELIMITER ',' CSV HEADER ENCODING 'LATIN1';"

\copy geolocation FROM 'C:/Users/n5463/OPS/data/raw/olist_geolocation_dataset.csv' DELIMITER ',' CSV HEADER;