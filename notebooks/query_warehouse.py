import duckdb

con = duckdb.connect("data/warehouse/nyc_taxi.duckdb", read_only=True)

print("\n===== ROWS PER TABLE =====")
for table in ["fact_trips", "dim_zone", "dim_date", "dim_weather", "dim_payment_type",
              "etl_load_log", "dq_results"]:
    count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table:<18} {count:>12,}")

print("\n===== IDEMPOTENCY CHECK: rows per month (must NOT double after re-runs) =====")
con.sql("""
    SELECT source_month, COUNT(*) AS trips
    FROM fact_trips
    GROUP BY source_month
    ORDER BY source_month
""").show()

print("\n===== LOAD HISTORY =====")
con.sql("SELECT * FROM etl_load_log ORDER BY loaded_at").show()

print("\n===== REVENUE BY PICKUP BOROUGH =====")
con.sql("""
    SELECT
        z.borough,
        COUNT(*)                         AS trips,
        ROUND(SUM(f.total_amount), 0)    AS revenue,
        ROUND(AVG(f.fare_amount), 2)     AS avg_fare,
        ROUND(AVG(f.trip_distance), 2)   AS avg_miles
    FROM fact_trips f
    JOIN dim_zone z ON f.pickup_location_id = z.location_id
    GROUP BY z.borough
    ORDER BY revenue DESC
""").show()

print("\n===== WEEKDAY vs WEEKEND =====")
con.sql("""
    SELECT
        d.is_weekend,
        COUNT(*) / COUNT(DISTINCT d.date_key)   AS avg_trips_per_day,
        ROUND(AVG(f.tip_pct), 1)                AS avg_tip_pct
    FROM fact_trips f
    JOIN dim_date d ON f.pickup_date_key = d.date_key
    GROUP BY d.is_weekend
""").show()

print("\n===== SAME QUESTION AS PANDAS Q1: avg trips per day by weather (January) =====")
con.sql("""
    SELECT
        w.weather_category,
        ROUND(COUNT(*) / COUNT(DISTINCT f.pickup_date_key), 0) AS avg_trips_per_day
    FROM fact_trips f
    JOIN dim_weather w ON f.pickup_date_key = w.date_key
    WHERE f.source_month = '2024-01'
    GROUP BY w.weather_category
    ORDER BY avg_trips_per_day
""").show()

con.close()