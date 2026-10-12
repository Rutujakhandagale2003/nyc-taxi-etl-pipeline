import pandas as pd

rejected = pd.read_parquet("data/staging/rejected/rejected_yellow_2024-01.parquet")
print(rejected["reject_reason"].value_counts())
print(rejected.groupby("reject_reason")[["fare_amount", "trip_distance", "trip_duration_minutes"]].median())