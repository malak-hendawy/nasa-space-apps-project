## ProbCast (NASA Space Apps)

An AI-powered weather companion that turns NASA datasets into clear, actionable insights with a simple dashboard and chatbot.

### Features
- NASA POWER integration for daily precipitation and temperature
- Plotly time-series charts
- Location map preview
- Rule-based advice engine with multilingual support (English, Arabic, Spanish, French)
- Chatbot stub for quick Q&A

### Quickstart
1. Create a virtual environment (recommended) and install dependencies:
```bash
pip install -r requirements.txt
```
2. Run the app:
```bash
streamlit run main.py
```
3. Choose latitude/longitude and date range in the sidebar.

### Notes
- Data source: NASA POWER Daily Point API (AG community) for `PRECTOT` (mm/day) and `T2M` (°C).
- This MVP focuses on POWER; future steps can add OPeNDAP, Data Rods, Giovanni, Worldview overlays, and CPTEC cross-checks.
- For Mapbox custom maps, configure Plotly Mapbox with a token or use Streamlit's map.

### Next Steps
- Add Data Rods time-series for humidity and richer variables
- Overlay Giovanni/Worldview imagery
- Expand chatbot with retrieval-augmented answers and local language support
- Export to CSV/PDF


