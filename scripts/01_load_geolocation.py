import pandas as pd
from db_connection import get_engine

engine = get_engine()

geo_df = pd.read_sql("SELECT * FROM geolocation", engine)

print("Geolocation rows loaded:", len(geo_df))
print(geo_df.head())

geo_clean = geo_df.groupby("geolocation_zip_code_prefix").agg(
    lat=("geolocation_lat", "mean"),
    lng=("geolocation_lng", "mean")
).reset_index()

print("Unique zip prefixes:", len(geo_clean))
print(geo_clean.head())

orders_df = pd.read_sql("""
    SELECT DISTINCT ON (order_id)
        order_id, customer_state, customer_zip_code_prefix,
        seller_state, seller_zip_code_prefix,
        is_late, total_fulfillment_days, last_mile_days
    FROM order_journey
    WHERE order_delivered_customer_date IS NOT NULL
""", engine)

print("Orders loaded:", len(orders_df))
print(orders_df.head())

orders_geo = orders_df.merge(
    geo_clean.rename(columns={
        "geolocation_zip_code_prefix": "customer_zip_code_prefix",
        "lat": "customer_lat",
        "lng": "customer_lng"
    }),
    on="customer_zip_code_prefix",
    how="left"
)

orders_geo = orders_geo.merge(
    geo_clean.rename(columns={
        "geolocation_zip_code_prefix": "seller_zip_code_prefix",
        "lat": "seller_lat",
        "lng": "seller_lng"
    }),
    on="seller_zip_code_prefix",
    how="left"
)

print("Rows after merging geolocation:", len(orders_geo))
print("Missing customer lat/lng:", orders_geo["customer_lat"].isna().sum())
print("Missing seller lat/lng:", orders_geo["seller_lat"].isna().sum())


import numpy as np

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in kilometers

    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arcsin(np.sqrt(a))

    return R * c

orders_geo = orders_geo.dropna(subset=["customer_lat", "customer_lng", "seller_lat", "seller_lng"])

orders_geo["distance_km"] = haversine_distance(
    orders_geo["seller_lat"], orders_geo["seller_lng"],
    orders_geo["customer_lat"], orders_geo["customer_lng"]
)

print("Rows with valid distance:", len(orders_geo))
print(orders_geo[["order_id", "distance_km", "total_fulfillment_days", "last_mile_days", "is_late"]].head(10))

print("\n--- Distance vs Last-Mile Time (correlation) ---")
print(orders_geo[["distance_km", "last_mile_days"]].corr())

orders_geo["distance_bucket"] = pd.cut(
    orders_geo["distance_km"],
    bins=[0, 100, 300, 600, 1000, 5000],
    labels=["0-100km", "100-300km", "300-600km", "600-1000km", "1000km+"]
)

bucket_summary = orders_geo.groupby("distance_bucket").agg(
    total_orders=("order_id", "count"),
    avg_last_mile_days=("last_mile_days", "mean"),
    late_pct=("is_late", "mean")
).reset_index()

bucket_summary["late_pct"] = (bucket_summary["late_pct"] * 100).round(2)
bucket_summary["avg_last_mile_days"] = bucket_summary["avg_last_mile_days"].round(2)

print("\n--- Delay by Distance Bucket ---")
print(bucket_summary)

orders_geo.to_csv("../data/processed/orders_with_distance.csv", index=False)
print("\nSaved to data/processed/orders_with_distance.csv")