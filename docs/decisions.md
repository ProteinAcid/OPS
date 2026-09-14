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

  ## Module 4 — Territory Alignment / Seller-Region Mapping

**Date:** 2026-09-14

**What we built:**
- `scripts/02_territory_alignment.py`: for each order, finds the distance to the 
  nearest seller who sells the same product category (using vectorized Haversine 
  distance via NumPy broadcasting across ~71 categories), and compares it to the 
  actual seller distance from Module 3.
- State-level breakdown of the gap between actual and theoretically-nearest seller 
  distance, saved to `data/processed/territory_gap_by_state.csv` and 
  `orders_with_territory_gap.csv`.

**Key findings:**
- On average, orders travel 600.7 km to their actual seller, vs. 105.6 km to the 
  nearest qualifying (same-category) seller — an average unnecessary distance of 
  ~495.7 km per order (median gap: 383.4 km).
- The gap is heavily concentrated in Brazil's Northeast: Paraíba (PB), Rio Grande do 
  Norte (RN), Pernambuco (PE), and Ceará (CE) each show gaps of 1,600+ km — meaning 
  customers there are served by sellers ~2,000km away on average when equivalent 
  sellers exist only 300-600km away.
- This finding directly explains Module 2's regional lateness pattern (same states 
  had the highest late %) and Module 3's distance-delay correlation — it's not just 
  that these regions are far from everything, it's that Olist's current seller 
  assignment isn't using the closer options that already exist in its own network.
- SP (the seller hub) has both the lowest actual distance and the smallest gap 
  (236.1 km) — most SP customers are already served efficiently by nearby SP sellers, 
  so there's little realignment opportunity there. This is a clean core-vs-periphery 
  logistics pattern.

**Key decisions & why:**
- Restricted "nearest seller" search to sellers who actually sell the same product 
  category (via a seller-category catalog built from historical order_items) rather 
  than nearest seller overall — a customer can't be usefully served by a nearby 
  seller who doesn't carry the product they want.
- Used NumPy broadcasting (reshaping customer/seller coordinate arrays into a 
  row/column pair to form a full distance matrix, then taking the row-wise minimum) 
  instead of a nested loop over orders and sellers, for performance across ~71 
  categories and ~95k orders.
- Framed the distance-gap finding as a theoretical ceiling, not a guaranteed 
  achievable saving — it assumes same-category sellers are interchangeable in price/
  inventory/quality, and ignores that customers actively choose which specific 
  seller/listing to buy from. The honest claim is "maximum possible geography-driven 
  efficiency gain," not "guaranteed savings if implemented."

**Known limitations carried forward:**
- Some orders (1,345 out of 95,998) couldn't be matched to a category and were 
  excluded from this analysis.
- A small number of orders show a slightly negative gap (min: -73.5 km) due to 
  zip-prefix-centroid approximation noise from Module 3's geolocation averaging — 
  not a real "nearest seller was farther than actual" case, just floating-point/
  approximation noise.
- This analysis assumes every same-category seller has equivalent inventory 
  availability and pricing — a real territory-redesign recommendation would need to 
  factor in seller capacity, price competitiveness, and customer choice, not just 
  geographic distance.