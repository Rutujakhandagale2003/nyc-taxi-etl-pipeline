"""Quick look at the raw data before writing cleaning rules."""
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

df = pd.read_parquet("data/raw/trips/yellow_tripdata_2024-01.parquet")

print("\n===== SHAPE (rows, columns) =====")
print(df.shape)

print("\n===== COLUMNS, TYPES, MEMORY =====")
df.info(memory_usage="deep")

print("\n===== FIRST 5 ROWS =====")
print(df.head())

print("\n===== NULL COUNTS =====")
print(df.isna().sum())

print("\n===== NUMERIC SUMMARY =====")
print(df.describe().T)

print("\n===== DATA PROBLEMS =====")
print("Negative fares:        ", (df["fare_amount"] < 0).sum())
print("Zero distance trips:   ", (df["trip_distance"] == 0).sum())
print("Dropoff before pickup: ", (df["tpep_dropoff_datetime"] < df["tpep_pickup_datetime"]).sum())
print("Pickup outside Jan 2024:",
      (~df["tpep_pickup_datetime"].between("2024-01-01", "2024-02-01")).sum())

zones = pd.read_csv("data/raw/zones/taxi_zone_lookup.csv")
print("\n===== ZONE LOOKUP =====")
print(zones.head())
print(zones.shape)