import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

df = pd.read_parquet("data/staging/enriched/enriched_yellow_2024-01.parquet")

print("\n===== SAMPLE ROWS =====")
print(df[["pickup_datetime", "pickup_zone", "dropoff_zone", "payment_type_name",
          "time_of_day", "weather_category", "fare_amount", "tip_pct"]].head())

print("\n===== Q1: Do more people take taxis on rainy or snowy days? (avg trips per day) =====")
daily = df.groupby(["pickup_date", "weather_category"], observed=True).size().reset_index(name="trips")
print(daily.groupby("weather_category", observed=True)["trips"].mean().round(0).sort_values())

print("\n===== Q2: Do card users tip more in bad weather? (median tip %) =====")
print(df.groupby("weather_category", observed=True)["tip_pct"].median().round(1))

print("\n===== Q3: Top 10 pickup zones =====")
print(df["pickup_zone"].value_counts().head(10))

print("\n===== Q4: Trips, average fare and median speed by hour =====")
hourly = df.groupby("pickup_hour").agg(
    trips=("fare_amount", "size"),
    avg_fare=("fare_amount", "mean"),
    median_speed_mph=("avg_speed_mph", "median"),
).round(1)
print(hourly)

print("\n===== Q5: Payment method share (%) =====")
print((df["payment_type_name"].value_counts(normalize=True) * 100).round(1))