from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from data_sources import get_daily_forecast, fetch_cptec_alerts, fetch_power_daily_variables, analyze_historical_probabilities, get_seasonal_patterns
from query_handler import generate_advice, chat_response
from utils import to_yyyymmdd, geocode_place, dataframe_to_csv_bytes, build_text_report, build_json_with_metadata


st.set_page_config(page_title="ProbCast • NASA Space Apps", page_icon="🌦️", layout="wide")


def init_state():
	if "messages" not in st.session_state:
		st.session_state.messages = []


def sidebar_controls():
    st.sidebar.header("Location & Date Range")
    place = st.sidebar.text_input("Enter a place (e.g., Cairo, Egypt)", value="")
    geocode_btn = st.sidebar.button("Search")
    if geocode_btn and place.strip():
        try:
            result = geocode_place(place)
            if result:
                lat, lon, label = result
                st.session_state["lat"] = lat
                st.session_state["lon"] = lon
                st.session_state["place_label"] = label
                st.sidebar.success(label)
            else:
                st.sidebar.warning("Place not found")
        except Exception as e:
            st.sidebar.warning(f"Geocoding failed: {e}")
    lat = st.session_state.get("lat", 0.0)
    lon = st.session_state.get("lon", 0.0)
    end_date = st.sidebar.date_input("End date", value=date.today())
    start_date = st.sidebar.date_input("Start date", value=date.today() - timedelta(days=14))
    language = st.sidebar.selectbox("Language", ["English", "Arabic", "Spanish", "French"]) 
    unit_system = st.sidebar.radio("Units", ["Metric", "Imperial"], horizontal=True)
    st.sidebar.divider()
    st.sidebar.header("Preferences")
    src = st.sidebar.selectbox("Data source", ["NASA POWER", "Mock"], index=0)
    variables = st.sidebar.multiselect("Variables", ["Precipitation", "Temperature", "Humidity", "Windspeed", "Pressure", "Snow Depth", "Cloud Cover", "Dust Concentration"], default=["Precipitation", "Temperature"])
    user_type = st.sidebar.selectbox("User type", ["General", "Farmer"], index=0)
    crop = None
    if user_type == "Farmer":
        crop = st.sidebar.selectbox("Crop", ["Wheat", "Maize", "Rice", "Other"], index=0)
    return lat, lon, start_date, end_date, language, unit_system, src, variables, user_type, crop


def render_header():
	st.title("ProbCast: Will It Rain on My Parade?")
	st.caption("AI-powered weather companion using NASA datasets for clear, actionable insights.")


def render_map(lat: float, lon: float):
    st.subheader("Location Preview")
    label = st.session_state.get("place_label")
    if label:
        st.caption(label)
    st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))


def render_timeseries(df: pd.DataFrame, unit_system: str):
	st.subheader("Weather Time Series")
	if df.empty:
		st.info("No data returned for the selected range.")
		return
	
	plot_df = df.copy()
	
	# Check if DATE column exists
	if "DATE" not in plot_df.columns:
		st.error("No DATE column found in data")
		return
		
	# Convert DATE to datetime and sort
	plot_df["DATE"] = pd.to_datetime(plot_df["DATE"], errors="coerce")
	plot_df = plot_df.dropna(subset=["DATE"]).sort_values("DATE").reset_index(drop=True)
	
	if plot_df.empty:
		st.error("No valid dates found")
		return
	
	# Show forecast notice if data extends beyond today
	today = pd.Timestamp.now().date()
	future_data = plot_df[plot_df["DATE"].dt.date > today]
	if not future_data.empty:
		st.info(f"📅 **Forecast Data**: Data after {today.strftime('%Y-%m-%d')} is projected based on recent patterns (not actual measurements)")
	
	# Determine column names depending on source
	precip_col = "PRECTOT" if "PRECTOT" in plot_df.columns else ("Precipitation" if "Precipitation" in plot_df.columns else None)
	temp_col = "T2M" if "T2M" in plot_df.columns else ("Temperature" if "Temperature" in plot_df.columns else None)
	
	# Convert numeric columns safely
	if precip_col and precip_col in plot_df.columns:
		plot_df[precip_col] = pd.to_numeric(plot_df[precip_col], errors="coerce")
	if temp_col and temp_col in plot_df.columns:
		plot_df[temp_col] = pd.to_numeric(plot_df[temp_col], errors="coerce")
	if "Humidity" in plot_df.columns:
		plot_df["Humidity"] = pd.to_numeric(plot_df["Humidity"], errors="coerce")
	if "Windspeed" in plot_df.columns:
		plot_df["Windspeed"] = pd.to_numeric(plot_df["Windspeed"], errors="coerce")

	# Unit conversion
	if unit_system == "Imperial":
		if temp_col and temp_col in plot_df.columns:
			plot_df["T2M_plot"] = plot_df[temp_col] * 9 / 5 + 32
		if precip_col and precip_col in plot_df.columns:
			plot_df["PRECTOT_plot"] = plot_df[precip_col] / 25.4
		temp_unit = "°F"
		precip_unit = "in/day"
	else:
		if temp_col and temp_col in plot_df.columns:
			plot_df["T2M_plot"] = plot_df[temp_col]
		if precip_col and precip_col in plot_df.columns:
			plot_df["PRECTOT_plot"] = plot_df[precip_col]
		temp_unit = "°C"
		precip_unit = "mm/day"

	# Remove extreme outliers
	if "T2M_plot" in plot_df.columns:
		plot_df["T2M_plot"] = plot_df["T2M_plot"].clip(lower=-50, upper=60)
	if "PRECTOT_plot" in plot_df.columns:
		plot_df["PRECTOT_plot"] = plot_df["PRECTOT_plot"].clip(lower=0, upper=100)

	# Create figure based on available data
	has_precip = precip_col and precip_col in plot_df.columns
	has_temp = temp_col and temp_col in plot_df.columns
	has_humidity = "Humidity" in plot_df.columns
	has_wind = "Windspeed" in plot_df.columns
	
	# Determine subplot layout
	if has_precip and has_temp:
		fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], 
						   specs=[[{"secondary_y": True}], [{}]], 
						   subplot_titles=("Temperature & Precipitation", "Humidity & Wind Speed"))
	elif has_precip or has_temp:
		fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])
	else:
		fig = make_subplots(rows=1, cols=1)
	
	# Add traces
	if has_precip:
		prec_series = plot_df.get("PRECTOT_plot", plot_df.get("Precipitation"))
		if prec_series is not None:
			fig.add_trace(go.Bar(x=plot_df["DATE"], y=prec_series, 
							   name=f"Precipitation ({precip_unit})", 
							   marker_color="#4C78A8", opacity=0.7), 
						 row=1, col=1, secondary_y=False)
	
	if has_temp:
		temp_series = plot_df.get("T2M_plot", plot_df.get("Temperature"))
		if temp_series is not None:
			fig.add_trace(go.Scatter(x=plot_df["DATE"], y=temp_series, 
								   name=f"Temperature ({temp_unit})", 
								   mode="lines+markers", 
								   line=dict(color="#F58518", width=2),
								   marker=dict(size=4)), 
						 row=1, col=1, secondary_y=True)
	
	if has_humidity:
		fig.add_trace(go.Scatter(x=plot_df["DATE"], y=plot_df["Humidity"], 
							   name="Humidity (%)", 
							   mode="lines", 
							   line=dict(color="#54A24B", width=2)), 
					 row=2 if (has_precip and has_temp) else 1, col=1)
	
	if has_wind:
		fig.add_trace(go.Scatter(x=plot_df["DATE"], y=plot_df["Windspeed"], 
							   name="Wind Speed (m/s)", 
							   mode="lines", 
							   line=dict(color="#E45756", width=2)), 
					 row=2 if (has_precip and has_temp) else 1, col=1)
	
	# Update layout
	fig.update_layout(
		margin=dict(l=20, r=20, t=60, b=20),
		height=600,
		legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
		title_text="Weather Data Over Time",
		title_x=0.5
	)
	
	# Update axes
	if has_precip or has_temp:
		fig.update_xaxes(title_text="Date", row=1, col=1)
		fig.update_yaxes(title_text=f"Precipitation ({precip_unit})", row=1, col=1, secondary_y=False)
		fig.update_yaxes(title_text=f"Temperature ({temp_unit})", row=1, col=1, secondary_y=True)
	
	if has_humidity or has_wind:
		fig.update_xaxes(title_text="Date", row=2, col=1)
	
	st.plotly_chart(fig, use_container_width=True)

	# Show data preview
	with st.expander("Data Preview (Last 10 Rows)"):
		display_cols = ["DATE"]
		if has_precip:
			display_cols.append(precip_col or "Precipitation")
		if has_temp:
			display_cols.append(temp_col or "Temperature")
		if has_humidity:
			display_cols.append("Humidity")
		if has_wind:
			display_cols.append("Windspeed")
		
		st.dataframe(plot_df[display_cols].tail(10), use_container_width=True)


def render_advice(df: pd.DataFrame, language: str, unit_system: str):
	st.subheader("Assistant Insights")
	advice = generate_advice(df, language=language)
	st.success(advice)


def render_chatbot(language: str):
	st.subheader("Chatbot")
	for m in st.session_state.messages:
		with st.chat_message(m["role"]):
			st.markdown(m["content"])
	prompt = st.chat_input("Ask about the forecast, risks, or recommendations…")
	if prompt:
		st.session_state.messages.append({"role": "user", "content": prompt})
		with st.chat_message("user"):
			st.markdown(prompt)
		response = chat_response(prompt, language=language)
		st.session_state.messages.append({"role": "assistant", "content": response})
		with st.chat_message("assistant"):
			st.markdown(response)


def render_probability_analysis(df: pd.DataFrame, variables: list, language: str, unit_system: str):
	"""
	Render historical probability analysis section.
	"""
	st.subheader("📊 Historical Probability Analysis")
	st.caption("Based on NASA Earth observation data - probabilities of weather conditions exceeding specific thresholds")
	
	# Create tabs for different analyses
	tab1, tab2, tab3 = st.tabs(["🎯 Threshold Probabilities", "📈 Seasonal Patterns", "📊 Distribution Analysis"])
	
	with tab1:
		st.markdown("### Probability of Exceeding Thresholds")
		
		# Select variable and threshold
		col1, col2 = st.columns(2)
		with col1:
			selected_var = st.selectbox("Select Variable", variables, key="prob_var")
		with col2:
			if selected_var == "Temperature":
				threshold = st.number_input("Temperature Threshold (°C)", value=30.0, step=1.0, key="temp_thresh")
			elif selected_var == "Precipitation":
				threshold = st.number_input("Precipitation Threshold (mm/day)", value=10.0, step=1.0, key="precip_thresh")
			elif selected_var == "Windspeed":
				threshold = st.number_input("Wind Speed Threshold (m/s)", value=10.0, step=1.0, key="wind_thresh")
			elif selected_var == "Humidity":
				threshold = st.number_input("Humidity Threshold (%)", value=80.0, step=5.0, key="humidity_thresh")
			else:
				threshold = st.number_input(f"{selected_var} Threshold", value=50.0, step=5.0, key="other_thresh")
		
		# Analyze probability
		if st.button("Calculate Probability", key="calc_prob"):
			prob_result = analyze_historical_probabilities(df, selected_var, threshold)
			
			if "error" not in prob_result:
				col1, col2, col3 = st.columns(3)
				with col1:
					st.metric("Probability", f"{prob_result['probability_percent']}%")
				with col2:
					st.metric("Days Exceeding", f"{prob_result['days_exceeding']}/{prob_result['total_days']}")
				with col3:
					st.metric("Mean Value", f"{prob_result['mean']}")
				
				# Show trend if available
				if prob_result.get('trend'):
					trend = prob_result['trend']
					if trend['direction'] == 'increasing':
						st.success(f"📈 **Trend**: {selected_var} has been increasing over {trend['years_analyzed']} years")
					else:
						st.info(f"📉 **Trend**: {selected_var} has been decreasing over {trend['years_analyzed']} years")
				
				# Show percentiles
				st.markdown("#### Percentile Distribution")
				percentiles = prob_result['percentiles']
				col1, col2, col3, col4 = st.columns(4)
				with col1:
					st.metric("25th Percentile", f"{percentiles['25th']}")
				with col2:
					st.metric("50th Percentile", f"{percentiles['50th']}")
				with col3:
					st.metric("75th Percentile", f"{percentiles['75th']}")
				with col4:
					st.metric("95th Percentile", f"{percentiles['95th']}")
			else:
				st.error(prob_result['error'])
	
	with tab2:
		st.markdown("### Seasonal Weather Patterns")
		
		selected_var_seasonal = st.selectbox("Select Variable for Seasonal Analysis", variables, key="seasonal_var")
		
		if st.button("Analyze Seasonal Patterns", key="calc_seasonal"):
			seasonal_result = get_seasonal_patterns(df, selected_var_seasonal)
			
			if "error" not in seasonal_result:
				# Show seasonal means
				st.markdown("#### Seasonal Averages")
				seasonal_means = seasonal_result['seasonal_means']
				col1, col2, col3, col4 = st.columns(4)
				seasons = ["Winter", "Spring", "Summer", "Fall"]
				for i, season in enumerate(seasons):
					with [col1, col2, col3, col4][i]:
						if season in seasonal_means:
							st.metric(season, f"{seasonal_means[season]}")
				
				# Show peak and lowest months
				st.markdown("#### Peak and Lowest Months")
				col1, col2 = st.columns(2)
				with col1:
					st.metric("Peak Month", f"Month {seasonal_result['peak_month']}")
				with col2:
					st.metric("Lowest Month", f"Month {seasonal_result['lowest_month']}")
				
				# Create seasonal chart
				monthly_stats = seasonal_result['monthly_stats']
				if 'mean' in monthly_stats:
					months = list(range(1, 13))
					means = [monthly_stats['mean'].get(month, 0) for month in months]
					
					fig = go.Figure()
					fig.add_trace(go.Scatter(
						x=months, y=means,
						mode='lines+markers',
						name=f'{selected_var_seasonal} Monthly Average',
						line=dict(width=3)
					))
					fig.update_layout(
						title=f"Monthly {selected_var_seasonal} Pattern",
						xaxis_title="Month",
						yaxis_title=f"{selected_var_seasonal}",
						height=400
					)
					st.plotly_chart(fig, use_container_width=True)
			else:
				st.error(seasonal_result['error'])
	
	with tab3:
		st.markdown("### Probability Distribution Analysis")
		
		selected_var_dist = st.selectbox("Select Variable for Distribution", variables, key="dist_var")
		
		if st.button("Generate Distribution", key="calc_dist"):
			if selected_var_dist in df.columns:
				values = df[selected_var_dist].dropna()
				if not values.empty:
					# Create histogram
					fig = go.Figure()
					fig.add_trace(go.Histogram(
						x=values,
						nbinsx=30,
						name=f'{selected_var_dist} Distribution',
						opacity=0.7
					))
					fig.update_layout(
						title=f"{selected_var_dist} Probability Distribution",
						xaxis_title=f"{selected_var_dist}",
						yaxis_title="Frequency",
						height=400
					)
					st.plotly_chart(fig, use_container_width=True)
					
					# Show statistics
					st.markdown("#### Distribution Statistics")
					col1, col2, col3, col4 = st.columns(4)
					with col1:
						st.metric("Mean", f"{values.mean():.2f}")
					with col2:
						st.metric("Median", f"{values.median():.2f}")
					with col3:
						st.metric("Std Dev", f"{values.std():.2f}")
					with col4:
						st.metric("Range", f"{values.max() - values.min():.2f}")
				else:
					st.error("No data available for distribution analysis")
			else:
				st.error("Selected variable not found in data")


def render_resources():
	with st.expander("NASA Data & Resources"):
		st.markdown(
			"- **GES DISC OPeNDAP (Hyrax)**: Access and subset many variables via [GES DISC OPeNDAP](https://disc.gsfc.nasa.gov/information/tools?title=OPeNDAP).\n"
			"- **Giovanni**: Data maps and time series via [Giovanni](https://giovanni.gsfc.nasa.gov/giovanni/).\n"
			"- **Data Rods for Hydrology**: Point time series via [Data Rods](https://disc.gsfc.nasa.gov/information/tools?title=Data%20Rods).\n"
			"- **Worldview**: Explore imagery in [Worldview](https://worldview.earthdata.nasa.gov/).\n"
			"- **Earthdata Search**: Search NASA Earth science data in [Earthdata Search](https://search.earthdata.nasa.gov/).\n"
			"- **Data Access Tutorials**: Step-by-step notebooks in [GES DISC Tutorials](https://disc.gsfc.nasa.gov/information/howto)."
		)
	with st.expander("Space Agency Partner Resources"):
		st.markdown(
			"- **Brazilian Space Agency (AEB)**: [AEB portal](https://www.gov.br/aeb/pt-br).\n"
			"- **CPTEC/INPE**: High-resolution forecasts, alerts, and climate monitoring via [CPTEC/INPE](https://www.cptec.inpe.br/)."
		)


def main():
	init_state()
	render_header()
	lat, lon, start_date, end_date, language, unit_system, src, variables, user_type, crop = sidebar_controls()

	# Always show map and chatbot UI even if data fetch fails
	col_map, col_series = st.columns([1, 2])
	with col_map:
		render_map(lat, lon)

	data_df = pd.DataFrame(columns=["DATE"])  # default empty
	with st.spinner("Fetching data…"):
		try:
			start = to_yyyymmdd(start_date)
			end = to_yyyymmdd(end_date)
			if src.startswith("NASA"):
				data_df = fetch_power_daily_variables(latitude=lat, longitude=lon, start=start, end=end, variables=variables)
				if not data_df.empty:
					st.success(f"✅ Data loaded successfully ({len(data_df)} days)")
				else:
					st.warning("⚠️ No data returned from NASA POWER")
			else:
				mock_df = get_daily_forecast(source=src, latitude=lat, longitude=lon, start=start, end=end)
				data_df = mock_df.rename(columns={"PRECTOT": "Precipitation", "T2M": "Temperature"})
				st.info(f"📊 Using mock data ({len(data_df)} days)")
		except Exception as e:
			st.error(f"❌ Data fetch failed: {e}")
			st.info("🔄 Falling back to mock data...")
			try:
				mock_df = get_daily_forecast(source="Mock", latitude=lat, longitude=lon, start=start, end=end)
				data_df = mock_df.rename(columns={"PRECTOT": "Precipitation", "T2M": "Temperature"})
				st.success(f"✅ Mock data loaded ({len(data_df)} days)")
			except Exception as mock_error:
				st.error(f"❌ Mock data also failed: {mock_error}")
				data_df = pd.DataFrame(columns=["DATE"])

	with col_series:
		render_timeseries(data_df, unit_system)

	render_advice(data_df, language, unit_system)

	# Historical Probability Analysis
	if not data_df.empty and len(variables) > 0:
		render_probability_analysis(data_df, variables, language, unit_system)

	# CPTEC alerts
	with st.expander("CPTEC Alerts (beta)"):
		alerts = fetch_cptec_alerts()
		if alerts:
			for a in alerts:
				st.warning(f"{a.get('title')}  ")
		else:
			st.caption("No alerts or feed unavailable.")

	# Exports
	st.subheader("Export")
	left_dl, right_dl = st.columns(2)
	with left_dl:
		st.download_button("Download CSV", data=dataframe_to_csv_bytes(data_df), file_name="probcast_daily.csv", mime="text/csv")
	with right_dl:
		txt = build_text_report(st.session_state.get("place_label", ""), data_df, unit_system)
		st.download_button("Download Text Report", data=txt, file_name="probcast_report.txt", mime="text/plain")
	json_payload = build_json_with_metadata(st.session_state.get("place_label", ""), data_df, unit_system, src)
	st.download_button("Download JSON + Metadata", data=json_payload, file_name="probcast_data.json", mime="application/json")

	# Resources
	render_resources()
	render_chatbot(language)


if __name__ == "__main__":
	main()


