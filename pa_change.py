# import pandas as pd


# def detect_violations_pandas(assignments_file, policies_file):
#     # 1. Load Data
#     df_assignments = pd.read_csv(assignments_file)
#     df_policies = pd.read_csv(policies_file)

#     # 2. Filter Active Users
#     # Filter a) Filter user_id only who are active
#     active_users_df = df_assignments[df_assignments["status"] == "active"].copy()

#     # 3. Aggregate Roles per User
#     # Creates a Series where index is user_id and value is a python set of roles
#     # e.g. {'u1': {'PaymentsAdmin', 'TradingDesk'}, 'u2': ...}
#     user_roles_map = active_users_df.groupby("user_id")["role"].apply(set)

#     # 4. Prepare User Metadata (for the final report)
#     # Drop duplicates to get one row per user with their details
#     user_meta = (
#         active_users_df[["user_id", "name", "department"]]
#         .drop_duplicates()
#         .set_index("user_id")
#     )

#     results = []

#     # 5. Check Violations (Iterate Policies)
#     # Note: Iterating policies (usually < 1000) is much faster than iterating users (millions)
#     for _, policy in df_policies.iterrows():
#         # Parse roles string '["A", "B"]' into a Python set
#         # using eval is unsafe in prod, usually use json.loads if valid JSON
#         import json

#         try:
#             policy_roles = set(json.loads(policy["roles"]))
#         except:
#             continue  # Skip malformed

#         # Vectorized Check? Hard with sets.
#         # List comprehension is often fastest here for set operations against a Series.

#         # Find all users where policy_roles is a subset of their user_roles
#         # This logic checks: policy_roles <= user_roles
#         violating_users = user_roles_map[
#             user_roles_map.apply(lambda x: policy_roles.issubset(x))
#         ].index

#         for user_id in violating_users:
#             user_info = user_meta.loc[user_id]

#             # b) Create required text output
#             violation_text = (
#                 f"User violates { ' + '.join(policy_roles)} ({policy['policy_id']})"
#             )

#             results.append(
#                 {
#                     "user_id": user_id,
#                     "name": user_info["name"],
#                     "department": user_info["department"],
#                     "violation": violation_text,
#                     "policy_id": policy["policy_id"],
#                 }
#             )

#     # Convert results to DataFrame
#     return pd.DataFrame(results)


# # Usage
# # final_df = detect_violations_pandas("assignments.csv", "toxic_policies.csv")
# # print(final_df)
