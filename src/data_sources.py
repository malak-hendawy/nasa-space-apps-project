import requests
import pandas as pd
import datetime as _dt
from typing import List, Dict

import feedparser


BASE_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def fetch_power_daily(latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
	params = {
		"parameters": "PRECTOT,T2M",
		"community": "AG",
		"latitude": latitude,
		"longitude": longitude,
		"start": start,
		"end": end,
		"format": "JSON",
	}
	resp = requests.get(BASE_URL, params=params, timeout=30)
	resp.raise_for_status()
	data = resp.json()
	params_data = data.get("properties", {}).get("parameter", {})
	prec = params_data.get("PRECTOT", {})
	tmp = params_data.get("T2M", {})
	dates = sorted(set(prec.keys()) | set(tmp.keys()))
	def _clean(v):
		try:
			fv = float(v)
			# POWER missing value flags are typically -999, -9999
			if fv <= -900:
				return None
			return fv
		except Exception:
			return None

	rows = []
	for d in dates:
		rows.append({
			"DATE": pd.to_datetime(d, format="%Y%m%d"),
			"PRECTOT": _clean(prec.get(d)),
			"T2M": _clean(tmp.get(d)),
		})
	return pd.DataFrame(rows).sort_values("DATE").reset_index(drop=True)


PARAM_MAP = {
	"Precipitation": "PRECTOT",   # mm/day
	"Temperature": "T2M",        # °C
	"Humidity": "RH2M",          # %
	"Windspeed": "WS10M",        # m/s
	"Pressure": "PS",            # Pa
	"Snow Depth": "SNOD",        # mm
	"Cloud Cover": "CLRSKY",     # %
	"Dust Concentration": "DUST", # mg/m³
}


def fetch_power_daily_variables(latitude: float, longitude: float, start: str, end: str, variables: list) -> pd.DataFrame:
	"""
	Generic POWER fetch for selected variables. Variables should be keys of PARAM_MAP.
	Falls back to mock data if POWER API fails.
	"""
	params_codes = [PARAM_MAP[v] for v in variables if v in PARAM_MAP]
	if not params_codes:
		return pd.DataFrame(columns=["DATE"])  # empty
	
	params = {
		"parameters": ",".join(params_codes),
		"community": "AG",
		"latitude": latitude,
		"longitude": longitude,
		"start": start,
		"end": end,
		"format": "JSON",
	}
	
	try:
		resp = requests.get(BASE_URL, params=params, timeout=30)
		resp.raise_for_status()
		data = resp.json()
		params_data = data.get("properties", {}).get("parameter", {})

		def _clean(v):
			try:
				fv = float(v)
				if fv <= -900:
					return None
				return fv
			except Exception:
				return None

		# gather all dates
		all_dates = set()
		for code in params_codes:
			all_dates |= set((params_data.get(code, {}) or {}).keys())
		dates = sorted(all_dates)
		rows = []
		for d in dates:
			row = {"DATE": pd.to_datetime(d, format="%Y%m%d")}
			for v in variables:
				code = PARAM_MAP.get(v)
				if code:
					row[code] = _clean((params_data.get(code, {}) or {}).get(d))
			rows.append(row)
		df = pd.DataFrame(rows).sort_values("DATE").reset_index(drop=True)
		# rename columns back to friendly names
		rename_map = {PARAM_MAP[k]: k for k in variables if k in PARAM_MAP}
		df = df.rename(columns=rename_map)

		# POWER is retrospective; extend naive forecast to requested end using recent means
		try:
			requested_end = _dt.datetime.strptime(end, "%Y%m%d").date()
			if not df.empty:
				last_date = df["DATE"].max().date()
				if last_date < requested_end:
					# Use last 7 days for trend analysis
					lookback = df.tail(7)
					future_dates = []
					cur = last_date + _dt.timedelta(days=1)
					while cur <= requested_end:
						future_dates.append(cur)
						cur += _dt.timedelta(days=1)
					
					fill_rows = []
					for i, d in enumerate(future_dates):
						row = {"DATE": pd.to_datetime(d)}
						
						# Add some realistic variation for future days
						day_offset = i + 1
						
						if "Precipitation" in df.columns:
							base_precip = float(lookback["Precipitation"].mean(skipna=True))
							# Add seasonal variation (higher in winter months)
							month_factor = 1.2 if d.month in [11, 12, 1, 2] else 0.8
							variation = (day_offset % 7) * 0.5  # Weekly pattern
							precip_value = max(0, base_precip * month_factor + variation)
							row["Precipitation"] = float(round(precip_value, 2))
						
						if "Temperature" in df.columns:
							base_temp = float(lookback["Temperature"].mean(skipna=True))
							# Add daily temperature variation
							daily_variation = 3 * ((day_offset % 3) - 1)  # -3, 0, +3 pattern
							temp_value = base_temp + daily_variation
							row["Temperature"] = float(round(temp_value, 2))
						
						if "Humidity" in df.columns:
							base_humidity = float(lookback["Humidity"].mean(skipna=True))
							# Humidity varies inversely with temperature
							humidity_variation = -5 if daily_variation > 0 else 5
							humidity_value = max(20, min(90, base_humidity + humidity_variation))
							row["Humidity"] = float(round(humidity_value, 1))
						
						if "Windspeed" in df.columns:
							base_wind = float(lookback["Windspeed"].mean(skipna=True))
							# Wind speed varies randomly
							wind_variation = (day_offset % 5) * 0.5
							wind_value = max(0, base_wind + wind_variation)
							row["Windspeed"] = float(round(wind_value, 1))
						
						fill_rows.append(row)
					
					if fill_rows:
						df = pd.concat([df, pd.DataFrame(fill_rows)], ignore_index=True)
						df = df.sort_values("DATE").reset_index(drop=True)
		except Exception as e:
			# If extension fails, just return what we have
			pass

		return df
		
	except Exception as e:
		# POWER API failed, fallback to mock data
		print(f"POWER API failed: {e}, falling back to mock data")
		return generate_mock_forecast_variables(latitude, longitude, start, end, variables)


def analyze_historical_probabilities(df: pd.DataFrame, variable: str, threshold: float, month: int = None) -> dict:
	"""
	Analyze historical probabilities for a specific weather variable and threshold.
	Returns probability statistics for the given conditions.
	"""
	if df.empty or variable not in df.columns:
		return {"error": "No data available"}
	
	# Filter by month if specified
	if month is not None:
		monthly_data = df[df["DATE"].dt.month == month]
		if monthly_data.empty:
			return {"error": f"No data for month {month}"}
	else:
		monthly_data = df
	
	# Calculate statistics
	values = monthly_data[variable].dropna()
	if values.empty:
		return {"error": "No valid data points"}
	
	# Calculate probability of exceeding threshold
	exceed_count = (values >= threshold).sum()
	total_count = len(values)
	probability = (exceed_count / total_count) * 100 if total_count > 0 else 0
	
	# Calculate percentiles
	percentiles = {
		"10th": values.quantile(0.1),
		"25th": values.quantile(0.25),
		"50th": values.quantile(0.5),
		"75th": values.quantile(0.75),
		"90th": values.quantile(0.9),
		"95th": values.quantile(0.95),
		"99th": values.quantile(0.99),
	}
	
	# Calculate trend over years (if data spans multiple years)
	trend = None
	if len(df["DATE"].dt.year.unique()) > 1:
		yearly_means = df.groupby(df["DATE"].dt.year)[variable].mean()
		if len(yearly_means) >= 3:  # Need at least 3 years for trend
			trend_slope = yearly_means.polyfit(degree=1)[0]
			trend = {
				"slope": trend_slope,
				"direction": "increasing" if trend_slope > 0 else "decreasing",
				"years_analyzed": len(yearly_means)
			}
	
	return {
		"variable": variable,
		"threshold": threshold,
		"month": month,
		"total_days": total_count,
		"days_exceeding": exceed_count,
		"probability_percent": round(probability, 1),
		"mean": round(values.mean(), 2),
		"std": round(values.std(), 2),
		"min": round(values.min(), 2),
		"max": round(values.max(), 2),
		"percentiles": {k: round(v, 2) for k, v in percentiles.items()},
		"trend": trend
	}


def get_seasonal_patterns(df: pd.DataFrame, variable: str) -> dict:
	"""
	Analyze seasonal patterns for a weather variable.
	"""
	if df.empty or variable not in df.columns:
		return {"error": "No data available"}
	
	# Group by month
	monthly_stats = df.groupby(df["DATE"].dt.month)[variable].agg([
		'mean', 'std', 'min', 'max', 'count'
	]).round(2)
	
	# Calculate seasonal averages
	seasons = {
		"Winter": [12, 1, 2],
		"Spring": [3, 4, 5],
		"Summer": [6, 7, 8],
		"Fall": [9, 10, 11]
	}
	
	seasonal_means = {}
	for season, months in seasons.items():
		season_data = df[df["DATE"].dt.month.isin(months)][variable].dropna()
		if not season_data.empty:
			seasonal_means[season] = round(season_data.mean(), 2)
	
	return {
		"variable": variable,
		"monthly_stats": monthly_stats.to_dict(),
		"seasonal_means": seasonal_means,
		"peak_month": monthly_stats['mean'].idxmax(),
		"lowest_month": monthly_stats['mean'].idxmin()
	}


def generate_mock_forecast_variables(latitude: float, longitude: float, start: str, end: str, variables: list) -> pd.DataFrame:
	"""
	Generate mock forecast for selected variables with realistic patterns.
	"""
	start_dt = _dt.datetime.strptime(start, "%Y%m%d").date()
	end_dt = _dt.datetime.strptime(end, "%Y%m%d").date()
	delta_days = (end_dt - start_dt).days
	if delta_days < 0:
		return pd.DataFrame(columns=["DATE"])
	
	# Use lat/lon for seeding to get location-specific patterns
	seed = int((abs(latitude) * 100 + abs(longitude) * 100)) % 97
	rows = []
	
	for i in range(delta_days + 1):
		day = start_dt + _dt.timedelta(days=i)
		row = {"DATE": pd.to_datetime(day)}
		
		# Generate realistic values based on day and location
		day_of_year = day.timetuple().tm_yday
		
		if "Precipitation" in variables:
			# Seasonal pattern: higher in winter months
			seasonal_factor = 1.5 if day.month in [11, 12, 1, 2] else 0.5
			# Weekly pattern
			weekly_pattern = (i % 7) * 0.3
			# Random component
			random_factor = (seed + i) % 10 * 0.2
			precip = max(0, seasonal_factor + weekly_pattern + random_factor)
			row["Precipitation"] = float(round(precip, 2))
		
		if "Temperature" in variables:
			# Seasonal temperature variation
			base_temp = 20 + 10 * (latitude / 90)  # Latitude-based base temp
			seasonal_variation = 15 * (day_of_year / 365)  # Annual cycle
			daily_variation = 5 * ((i % 3) - 1)  # Daily pattern
			temp = base_temp + seasonal_variation + daily_variation
			row["Temperature"] = float(round(temp, 1))
		
		if "Humidity" in variables:
			# Humidity inversely related to temperature
			base_humidity = 60 - (latitude / 3)  # Latitude effect
			temp_effect = -0.5 * (temp - 20) if "Temperature" in variables else 0
			daily_variation = 10 * ((i % 4) - 1.5)
			humidity = max(20, min(90, base_humidity + temp_effect + daily_variation))
			row["Humidity"] = float(round(humidity, 1))
		
		if "Windspeed" in variables:
			# Wind speed with seasonal and daily patterns
			base_wind = 3 + (seed % 5) * 0.5
			seasonal_factor = 1.5 if day.month in [3, 4, 10, 11] else 1.0  # Spring/fall winds
			daily_pattern = 2 * ((i % 6) - 2.5)
			wind = max(0, base_wind * seasonal_factor + daily_pattern)
			row["Windspeed"] = float(round(wind, 1))
		
		if "Pressure" in variables:
			# Atmospheric pressure (higher in winter)
			base_pressure = 101325  # Standard atmospheric pressure in Pa
			seasonal_variation = 2000 if day.month in [12, 1, 2] else -1000
			daily_variation = 500 * ((i % 4) - 1.5)
			pressure = base_pressure + seasonal_variation + daily_variation
			row["Pressure"] = float(round(pressure, 0))
		
		if "Snow Depth" in variables:
			# Snow depth (only in cold months)
			if day.month in [11, 12, 1, 2, 3]:
				base_snow = 50 + (seed % 20) * 5
				monthly_factor = 1.5 if day.month in [1, 2] else 1.0
				snow = base_snow * monthly_factor
			else:
				snow = 0
			row["Snow Depth"] = float(round(snow, 1))
		
		if "Cloud Cover" in variables:
			# Cloud cover percentage
			base_clouds = 40 + (seed % 30)
			seasonal_factor = 1.3 if day.month in [11, 12, 1, 2] else 0.8
			daily_variation = 20 * ((i % 5) - 2)
			clouds = max(0, min(100, base_clouds * seasonal_factor + daily_variation))
			row["Cloud Cover"] = float(round(clouds, 1))
		
		if "Dust Concentration" in variables:
			# Dust concentration (higher in dry seasons)
			base_dust = 50 + (seed % 30)
			seasonal_factor = 2.0 if day.month in [6, 7, 8] else 0.5  # Summer dust storms
			daily_variation = 20 * ((i % 7) - 3)
			dust = max(0, base_dust * seasonal_factor + daily_variation)
			row["Dust Concentration"] = float(round(dust, 1))
		
		rows.append(row)
	
	return pd.DataFrame(rows)


def generate_mock_forecast(latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
	"""
	Generate a deterministic mock daily forecast DataFrame with columns DATE, PRECTOT, T2M.
	The values vary smoothly and are seeded by the lat/lon for repeatability.
	"""
	start_dt = _dt.datetime.strptime(start, "%Y%m%d").date()
	end_dt = _dt.datetime.strptime(end, "%Y%m%d").date()
	delta_days = (end_dt - start_dt).days
	if delta_days < 0:
		return pd.DataFrame(columns=["DATE", "PRECTOT", "T2M"])
	seed = int((abs(latitude) * 100 + abs(longitude) * 100)) % 97
	rows = []
	for i in range(delta_days + 1):
		day = start_dt + _dt.timedelta(days=i)
		# Smooth oscillations for demo
		prec = max(0.0, (seed % 13) + 8 * ((i % 7) / 7))  # mm/day
		temp = 18.0 + (seed % 7) + 10.0 * ((i % 10) / 10)  # °C
		rows.append({
			"DATE": pd.to_datetime(day),
			"PRECTOT": float(round(prec, 2)),
			"T2M": float(round(temp, 2)),
		})
	return pd.DataFrame(rows)


def fetch_cptec_alerts() -> List[Dict[str, str]]:
	"""
	Fetch CPTEC/INPE severe weather alerts via RSS.
	Returns a list of dicts with title and link. If feed fails, returns empty list.
	"""
	# Example public CPTEC RSS; if unavailable, we'll return empty
	feed_url = "https://servicos.cptec.inpe.br/XML/cidade/alertas/"  # placeholder endpoint
	try:
		parsed = feedparser.parse(feed_url)
		alerts = []
		for entry in parsed.entries[:5]:
			alerts.append({
				"title": entry.get("title", "CPTEC Alert"),
				"link": entry.get("link", ""),
			})
		return alerts
	except Exception:
		return []


def get_daily_forecast(source: str, latitude: float, longitude: float, start: str, end: str) -> pd.DataFrame:
	"""
	Return a daily forecast DataFrame from the requested source.
	- "NASA POWER": uses POWER API
	- "Mock": uses deterministic mock generator
	Falls back to mock if the primary source fails.
	"""
	src = (source or "NASA POWER").lower()
	if src.startswith("nasa"):
		try:
			return fetch_power_daily(latitude=latitude, longitude=longitude, start=start, end=end)
		except Exception:
			return generate_mock_forecast(latitude=latitude, longitude=longitude, start=start, end=end)
	return generate_mock_forecast(latitude=latitude, longitude=longitude, start=start, end=end)

