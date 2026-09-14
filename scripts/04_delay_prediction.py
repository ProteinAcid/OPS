import pandas as pd
import numpy as np
from db_connection import get_engine

engine = get_engine()

orders_dist = pd.read_csv("../data/processed/orders_with_distance.csv")

order_features = pd.read_sql("""
    SELECT DISTINCT ON (order_id)
        order_id,
        order_purchase_timestamp,
        price,
        freight_value,
        pt.product_category_name_english AS category
    FROM order_journey oj
    JOIN products p ON oj.product_id = p.product_id
    LEFT JOIN product_category_translation pt ON p.product_category_name = pt.product_category_name
""", engine)

df = orders_dist.merge(order_features, on="order_id", how="left")

df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"])
df["order_month"] = df["order_purchase_timestamp"].dt.month
df["order_dayofweek"] = df["order_purchase_timestamp"].dt.dayofweek
df["is_peak_season"] = df["order_month"].isin([11, 12]).astype(int)

print("Total rows:", len(df))
print(df[["distance_km", "price", "freight_value", "category", "order_month", "is_late"]].head())
print("\nMissing values per column:")
print(df.isna().sum())

df = df.dropna(subset=["last_mile_days", "price", "freight_value"])

df["category"] = df["category"].fillna("unknown")

model_df = df[[
    "distance_km",
    "price",
    "freight_value",
    "category",
    "order_month",
    "order_dayofweek",
    "is_peak_season",
    "is_late"
]].copy()

print("\nFinal modeling dataset shape:", model_df.shape)
print(model_df["is_late"].value_counts(normalize=True))

from sklearn.model_selection import train_test_split

model_df = pd.get_dummies(model_df, columns=["category"], drop_first=True)

X = model_df.drop(columns=["is_late"])
y = model_df["is_late"]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

print("Training set size:", X_train.shape)
print("Test set size:", X_test.shape)
print("\nLate % in training set:", y_train.mean())
print("Late % in test set:", y_test.mean())

from sklearn.ensemble import RandomForestClassifier

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    class_weight="balanced",
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

print("Model trained.")

from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score

y_pred = model.predict(X_test)
y_pred_proba = model.predict_proba(X_test)[:, 1]

print("\n--- Classification Report ---")
print(classification_report(y_test, y_pred, target_names=["Not Late", "Late"]))

print("--- Confusion Matrix ---")
cm = confusion_matrix(y_test, y_pred)
print(cm)

print("\n--- ROC-AUC Score ---")
print(roc_auc_score(y_test, y_pred_proba))

importances = pd.Series(model.feature_importances_, index=X_train.columns)
top_features = importances.sort_values(ascending=False).head(15)

print("\n--- Top 15 Most Important Features ---")
print(top_features)