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

  ## Module 2 — Delivery Performance & SLA Analysis

**Date:** 2026-09-14

**What we built:**
- `orders_summary` view: collapses `order_journey` from order-item grain to one row 
  per order, aggregating price/freight, counting distinct sellers/products, and 
  picking a "primary" seller/category (by highest-value item) for orders with 
  multiple items.
- Five analysis queries: overall on-time %, delay by customer state, worst-performing 
  sellers (with minimum order threshold), processing-vs-transit root cause split, and 
  monthly delay trend.

**Key findings:**
- 8.11% of delivered orders are late; 2,190 orders (out of 98,666) were never 
  delivered at all — tracked as a separate "undelivered" metric rather than folded 
  into "late," since it's a different failure mode.
- Delay is heavily transit-driven system-wide: average processing time (approval → 
  carrier handoff) is 2.80 days vs. average transit time (carrier → customer) of 
  9.33 days — over 3x longer. This means the dominant lever for improving delivery 
  speed is logistics/distance (Modules 3-4), not seller packing speed.
- Regional lateness is concentrated in states farther from the São Paulo seller hub 
  (AL: 23.93% late, MA: 19.67%, PI: 15.97%), consistent with the transit-time finding.
- However, the worst individual sellers by late % are mostly SP-based despite SP 
  having strong regional averages — meaning a subset of sellers have a genuine 
  processing problem distinct from the system-wide transit problem. Both issues 
  exist simultaneously and need different fixes.
- Clear seasonal spikes: Nov 2017 (14.31% late, Black Friday demand surge) and March 
  2018 (21.36% late, coincides with Brazil's 2018 truck drivers' strike — a known 
  external shock, not an internally-fixable ops failure). Flagging this distinction 
  matters: not every spike reflects an operational weakness.

**Key decisions & why:**
- Used a VIEW (not a table) for `orders_summary` since it's a lightweight 
  re-aggregation of `order_journey` with no need for separate physical storage.
- For multi-item/multi-seller orders, aggregated with `SUM` for price/freight, 
  `COUNT(DISTINCT ...)` for seller/product diversity, and picked a "primary" 
  seller/category by highest-value item using `ARRAY_AGG(...ORDER BY price DESC)[1]`.
- Applied a minimum order threshold (`HAVING COUNT(*) >= 20`) when ranking sellers by 
  late %, to avoid small-sample sellers (e.g., 1 order, 100% late) distorting the 
  ranking.
- Excluded undelivered orders from all rate-based denominators (late %, avg days) 
  rather than treating them as "late," since "never delivered" is a distinct failure 
  mode from "delivered slowly."

**Known limitations carried forward:**
- We still don't have actual distance between seller and customer — the state-level 
  regional pattern is suggestive but not proof that distance drives transit time. 
  Module 3 will compute real distances using `geolocation` to confirm/quantify this.
- "Primary seller/category" logic means multi-seller orders' minority items are 
  invisible in seller-level and category-level breakdowns — acceptable for now since 
  most orders are single-seller, but worth remembering if seller-level numbers ever 
  look inconsistent with item-level Module 1 numbers.

  ## Module 3 — Last-Mile Logistics Analysis

**Date:** 2026-09-14

**What we built:**
- Python environment (`venv`) with `pandas`, `sqlalchemy`, `psycopg2-binary`, 
  `python-dotenv` for DB credentials.
- `scripts/db_connection.py`: reusable Postgres connection using `.env` for secrets 
  (never committed to Git).
- `scripts/01_load_geolocation.py`: cleans `geolocation` (deduplicates ~1M lat/long 
  pings down to 19,015 unique zip-prefix centroids via averaging), joins seller and 
  customer coordinates onto each order, computes real Haversine distance (in km) 
  between seller and customer for ~96k orders, buckets distance into ranges, and 
  saves the result to `data/processed/orders_with_distance.csv`.

**Key findings:**
- Distance and last-mile delivery time have a moderate positive correlation (0.42) — 
  distance is a real, quantifiable driver of delivery speed, not just a hypothesis.
- Clear, near-linear scaling by distance bucket: avg last-mile time goes from 2.90 
  days (0-100km) to 15.31 days (1000km+) — roughly a 5x increase. Late % roughly 
  doubles over the same range (6.38% -> 11.84%).
- This quantifies and confirms Module 2's regional finding (states far from the SP 
  seller hub had higher late %) — distance is a concrete, measurable mechanism behind 
  that pattern, not just a correlation with state labels.

**Key decisions & why:**
- Deduplicated geolocation to one lat/long per zip prefix by averaging all pings in 
  that prefix, since Brazilian CEP prefixes only identify a small area, not an exact 
  address — an average is the best available regional estimate given the data's 
  actual precision limit.
- Used `python-dotenv` + a gitignored `.env` file for DB credentials instead of 
  hardcoding them, following standard secret-management practice.
- Used `DISTINCT ON (order_id)` in the Postgres query (simpler than `orders_summary`'s 
  full multi-seller aggregation) since this analysis only needs one seller/customer 
  zip pair per order — accepted a minor inconsistency (uses first item's seller, not 
  the "primary by value" seller) as an acceptable simplification for this module.
- Used a left join when attaching lat/long, and explicitly counted + dropped rows 
  with missing coordinates (264 customer, 215 seller, out of 96,476) rather than 
  silently losing them via an inner join.
- Saved the enriched order-distance dataset to `data/processed/` as a CSV so later 
  modules (territory alignment, ML) can reuse it without recomputing distances.

**Known limitations carried forward:**
- Zip-prefix-level distance is an approximation, not exact address-to-address 
  distance — acceptable for regional-level analysis, not precise enough for 
  individual delivery routing.
- Averaging lat/long per prefix could be distorted for prefixes covering wide/sparse 
  rural areas with scattered pings — not corrected for here.
- ~96k of the original ~98.6k delivered orders have distance data (some lost to 
  missing zips or the DISTINCT ON simplification) — a small, acceptable coverage gap.