# Decisions Log

## Module 1 — Data Foundation

**Date:** 2026-09-14

**What we built:**
- Loaded the 9 raw Olist CSV tables into a local PostgreSQL database (`ops_project`).
- Built `order_journey`, a flattened fact table joining orders, customers, sellers, 
  products, order_items, and category translations, with derived fields: `is_late`, 
  `days_late`, `last_mile_days`, `total_fulfillment_days`.

**Key decisions & why:**
- Used `\copy` instead of `COPY` to load CSVs, since the Postgres service account 
  didn't have filesystem permission to read files directly — `\copy` runs client-side 
  under our own user account instead.
- `order_reviews` required `ENCODING 'LATIN1'` on load — the source file wasn't valid 
  UTF8 (common with this dataset). Also dropped its primary key constraint on 
  `review_id`, since the raw data contains a small number of genuine duplicate IDs, 
  and reviews aren't central to this project's core fulfillment/logistics analysis.
- `order_journey` is built at the **order-item grain** (one row per item, not per 
  order), because joining `order_items` is what brings in seller/product info. Orders 
  with multiple items will have multiple rows. This is intentional — Module 2 will 
  explicitly deduplicate back to order-level where lateness/SLA metrics require it, 
  but item-level rows are useful as-is for product/category-level analysis.
- Used `LEFT JOIN` (not inner join) for `product_category_translation`, since some 
  categories have no English translation — an inner join here would have silently 
  dropped those orders entirely.
- Stored money columns as `NUMERIC(10,2)`, not floating point, to avoid rounding 
  errors on currency values.

**Sanity checks passed:**
- Row counts match source CSVs for all 9 tables.
- 7.74% of order-items flagged as late — consistent with published benchmarks for 
  this dataset (~7-10%).
- Seller-state distribution shows expected São Paulo (SP) concentration as the 
  dominant seller hub.

**Known limitations carried forward:**
- `order_journey` currently uses raw zip-code-prefix + city/state text for location — 
  it does NOT yet have lat/long attached. Module 3 (last-mile) will need to join in 
  `geolocation` (aggregated per zip prefix, since raw geolocation has duplicates) to 
  compute actual distances.