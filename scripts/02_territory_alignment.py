import pandas as pd
import numpy as np
from db_connection import get_engine

engine = get_engine()

orders_dist = pd.read_csv("../data/processed/orders_with_distance.csv")

order_categories = pd.read_sql("""
    SELECT DISTINCT ON (order_id) order_id, seller_id,
           pt.product_category_name_english AS category
    FROM order_journey oj
    JOIN products p ON oj.product_id = p.product_id
    JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name
""", engine)

orders_dist = orders_dist.merge(order_categories, on="order_id", how="left")

print("Orders with category:", orders_dist["category"].notna().sum(), "out of", len(orders_dist))

seller_products = pd.read_sql("""
    SELECT DISTINCT oi.seller_id, pt.product_category_name_english AS category
    FROM order_items oi
    JOIN products p ON oi.product_id = p.product_id
    JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name
    WHERE p.product_category_name IS NOT NULL
""", engine)

print("Seller-category pairs:", len(seller_products))

seller_locations = pd.read_sql("""
    SELECT seller_id, seller_zip_code_prefix
    FROM sellers
""", engine)

geo_clean = pd.read_sql("""
    SELECT geolocation_zip_code_prefix, 
           AVG(geolocation_lat) AS lat, 
           AVG(geolocation_lng) AS lng
    FROM geolocation
    GROUP BY geolocation_zip_code_prefix
""", engine)

seller_locations = seller_locations.merge(
    geo_clean.rename(columns={"geolocation_zip_code_prefix": "seller_zip_code_prefix"}),
    on="seller_zip_code_prefix",
    how="left"
).dropna(subset=["lat", "lng"])

seller_cat_loc = seller_products.merge(seller_locations, on="seller_id", how="inner")

print("Sellers with location + category:", len(seller_cat_loc))

def haversine_vectorized(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_rad, lon2_rad = np.radians(lat2), np.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c

orders_dist["nearest_seller_distance_km"] = np.nan

categories = orders_dist["category"].dropna().unique()
print(f"Processing {len(categories)} categories...")

for cat in categories:
    order_mask = orders_dist["category"] == cat
    cat_orders = orders_dist.loc[order_mask]

    if cat_orders.empty:
        continue

    cat_sellers = seller_cat_loc.loc[seller_cat_loc["category"] == cat]

    if cat_sellers.empty:
        continue

    customer_lats = cat_orders["customer_lat"].to_numpy().reshape(-1, 1)
    customer_lngs = cat_orders["customer_lng"].to_numpy().reshape(-1, 1)

    seller_lats = cat_sellers["lat"].to_numpy().reshape(1, -1)
    seller_lngs = cat_sellers["lng"].to_numpy().reshape(1, -1)

    dist_matrix = haversine_vectorized(customer_lats, customer_lngs, seller_lats, seller_lngs)

    min_distances = np.nanmin(dist_matrix, axis=1)

    orders_dist.loc[order_mask, "nearest_seller_distance_km"] = min_distances

print("\nOrders with nearest-seller distance computed:", orders_dist["nearest_seller_distance_km"].notna().sum())

orders_dist["distance_gap_km"] = orders_dist["distance_km"] - orders_dist["nearest_seller_distance_km"]

print("\n--- Actual vs Nearest-Possible Distance ---")
print(orders_dist[["distance_km", "nearest_seller_distance_km", "distance_gap_km"]].describe())

orders_dist.to_csv("../data/processed/orders_with_territory_gap.csv", index=False)
print("\nSaved to data/processed/orders_with_territory_gap.csv")

state_gap = orders_dist.groupby("customer_state").agg(
    total_orders=("order_id", "count"),
    avg_actual_distance=("distance_km", "mean"),
    avg_nearest_distance=("nearest_seller_distance_km", "mean"),
    avg_gap=("distance_gap_km", "mean")
).round(1).sort_values("avg_gap", ascending=False).reset_index()

print("\n--- Territory Gap by Customer State ---")
print(state_gap)

state_gap.to_csv("../data/processed/territory_gap_by_state.csv", index=False)