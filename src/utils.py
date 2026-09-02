from datetime import date
from typing import Optional, Tuple
import io
import requests
import pandas as pd
import json


def to_yyyymmdd(d: date) -> str:
	return d.strftime("%Y%m%d")


def geocode_place(query: str) -> Optional[Tuple[float, float, str]]:
	"""
	Return (lat, lon, display_name) for a place name using OpenStreetMap Nominatim.
	"""
	q = (query or "").strip()
	if not q:
		return None
	resp = requests.get(
		"https://nominatim.openstreetmap.org/search",
		params={"q": q, "format": "json", "limit": 1},
		headers={"User-Agent": "ProbCast/1.0"},
		timeout=15,
	)
	resp.raise_for_status()
	arr = resp.json() or []
	if not arr:
		return None
	item = arr[0]
	lat = float(item.get("lat"))
	lon = float(item.get("lon"))
	display = item.get("display_name") or q
	return lat, lon, display



def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
	"""
	Return a UTF-8 CSV representation of the DataFrame as bytes for download.
	"""
	buffer = io.StringIO()
	df.to_csv(buffer, index=False)
	return buffer.getvalue().encode("utf-8")


def build_text_report(place_label: str, df: pd.DataFrame, unit_system: str) -> str:
	"""
	Create a simple human-readable summary for download as a text file.
	"""
	lines = []
	if place_label:
		lines.append(f"Report for: {place_label}")
	lines.append(f"Rows: {len(df)}")
	if not df.empty:
		# Support both POWER codes and friendly names
		precip_col = "PRECTOT" if "PRECTOT" in df.columns else ("Precipitation" if "Precipitation" in df.columns else None)
		temp_col = "T2M" if "T2M" in df.columns else ("Temperature" if "Temperature" in df.columns else None)
		p_avg = float(df[precip_col].mean(skipna=True)) if precip_col else 0.0
		t_max = float(df[temp_col].max(skipna=True)) if temp_col else 0.0
		if unit_system == "Imperial":
			p_avg_out = p_avg / 25.4
			t_max_out = t_max * 9 / 5 + 32
			lines.append(f"Average precipitation: {p_avg_out:.2f} in/day")
			lines.append(f"Max temperature: {t_max_out:.1f} °F")
		else:
			lines.append(f"Average precipitation: {p_avg:.2f} mm/day")
			lines.append(f"Max temperature: {t_max:.1f} °C")
	return "\n".join(lines)


def build_json_with_metadata(place_label: str, df: pd.DataFrame, unit_system: str, source: str) -> str:
	"""
	Return JSON string including data rows and metadata (units and source links).
	"""
	if unit_system == "Imperial":
		units = {"PRECTOT": "in/day", "T2M": "°F"}
	else:
		units = {"PRECTOT": "mm/day", "T2M": "°C"}
	source_links = {
		"NASA POWER": "https://power.larc.nasa.gov/",
		"Mock": "about:mock",
	}
	payload = {
		"metadata": {
			"place": place_label,
			"units": units,
			"source": source,
			"source_link": source_links.get(source, ""),
		},
		"data": df.to_dict(orient="records"),
	}
	return json.dumps(payload, ensure_ascii=False, default=str)

