import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

weather = pd.read_parquet("data/staging/weather/weather_2024-01.parquet")
print(weather.head(10))
print(weather.dtypes)
print(weather.describe().T)