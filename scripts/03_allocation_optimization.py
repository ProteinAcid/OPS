import pandas as pd
import pulp

orders_dist = pd.read_csv("../data/processed/orders_with_distance.csv")

state_distance_matrix = orders_dist.groupby(
    ["customer_state", "seller_state"]
)["distance_km"].mean().reset_index()

print("State-pair distance rows:", len(state_distance_matrix))
print(state_distance_matrix.head())

demand = orders_dist.groupby("customer_state")["order_id"].count().reset_index()
demand.columns = ["customer_state", "order_count"]

supply = orders_dist.groupby("seller_state")["order_id"].count().reset_index()
supply.columns = ["seller_state", "historical_orders"]

supply["capacity"] = (supply["historical_orders"] * 1.15).round().astype(int)

print("\nDemand (top 5):")
print(demand.sort_values("order_count", ascending=False).head())
print("\nSupply/capacity (top 5):")
print(supply.sort_values("capacity", ascending=False).head())

customer_states = demand["customer_state"].tolist()
seller_states = supply["seller_state"].tolist()

demand_dict = dict(zip(demand["customer_state"], demand["order_count"]))
capacity_dict = dict(zip(supply["seller_state"], supply["capacity"]))

distance_dict = {}
for _, row in state_distance_matrix.iterrows():
    distance_dict[(row["customer_state"], row["seller_state"])] = row["distance_km"]

fallback_distance = state_distance_matrix["distance_km"].max()

model = pulp.LpProblem("Fulfillment_Allocation", pulp.LpMinimize)

x = {}
for c in customer_states:
    for s in seller_states:
        x[(c, s)] = pulp.LpVariable(f"x_{c}_{s}", lowBound=0)

model += pulp.lpSum(
    x[(c, s)] * distance_dict.get((c, s), fallback_distance)
    for c in customer_states for s in seller_states
)

for c in customer_states:
    model += pulp.lpSum(x[(c, s)] for s in seller_states) == demand_dict[c]

for s in seller_states:
    model += pulp.lpSum(x[(c, s)] for c in customer_states) <= capacity_dict[s]

model.solve()

print("Solver status:", pulp.LpStatus[model.status])
print("Total optimal distance (order-km):", pulp.value(model.objective))

actual_total_distance = orders_dist["distance_km"].sum()

optimal_total_distance = pulp.value(model.objective)

savings_km = actual_total_distance - optimal_total_distance
savings_pct = (savings_km / actual_total_distance) * 100

print(f"\nActual total distance:   {actual_total_distance:,.0f} km")
print(f"Optimal total distance:  {optimal_total_distance:,.0f} km")
print(f"Potential savings:       {savings_km:,.0f} km ({savings_pct:.1f}%)")

allocation_results = []
for c in customer_states:
    for s in seller_states:
        qty = x[(c, s)].varValue
        if qty and qty > 0.5:
            allocation_results.append({
                "customer_state": c,
                "seller_state": s,
                "orders_allocated": round(qty),
                "distance_km": distance_dict.get((c, s), fallback_distance)
            })

allocation_df = pd.DataFrame(allocation_results)
allocation_df = allocation_df.sort_values("orders_allocated", ascending=False)

print("\n--- Top 15 Optimal Allocations ---")
print(allocation_df.head(15).to_string(index=False))

allocation_df.to_csv("../data/processed/optimal_allocation.csv", index=False)