import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd

st.set_page_config(page_title="TfL Cycle Route Planner", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to BikeGPX Generator")
st.write("Plan a route, view it, and download your GPX route for free turn-by-turn navigation!")

# Permanent UI memory state
if "current_route" not in st.session_state:
    st.session_state.current_route = None

col1, col2 = st.columns(2)
with col1:
    start_loc = st.text_input("Start Location", placeholder="e.g., WC1B 3DG or British Museum")
with col2:
    end_loc = st.text_input("End Location", placeholder="e.g., SW11 4NJ or Battersea Park")

bike_proficiency = st.selectbox(
    "Route Type / Cycling Pace",
    options=["easy", "moderate", "fast"],
    format_func=lambda x: x.capitalize()
)

tfl_key = st.text_input("TfL API Primary Key (Optional)", type="password")

def geocode_location(query, key=None):
    """
    Robust hybrid geocoding system:
    1. postcodes.io for perfect UK postcodes.
    2. TfL native search for London landmarks/stations.
    """
    clean_query = query.strip().replace(" ", "").upper()
    
    # 1. Check if it looks like a postcode
    if len(clean_query) >= 5 and len(clean_query) <= 8:
        postcode_url = f"https://api.postcodes.io/postcodes/{clean_query}"
        try:
            res = requests.get(postcode_url, timeout=4)
            if res.status_code == 200:
                pdata = res.json()["result"]
                return float(pdata["latitude"]), float(pdata["longitude"]), f"{pdata['postcode']}, London"
        except Exception:
            pass

    # 2. TfL Native Place Search (landmarks, stations, streets)
    tfl_search_url = "https://api.tfl.gov.uk/Place/Search"
    params = {"name": query}
    if key:
        params["app_key"] = key
        
    try:
        response = requests.get(tfl_search_url, params=params, timeout=5)
        if response.status_code == 200:
            results = response.json()
            if len(results) > 0:
                match = results[0]
                return float(match["lat"]), float(match["lon"]), match.get("name", query)
    except Exception:
        pass
        
    return None

def get_tfl_route_by_coords(start_coords, end_coords, proficiency, key=None):
    start_str = f"{start_coords[0]},{start_coords[1]}"
    end_str = f"{end_coords[0]},{end_coords[1]}"
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{start_str}/to/{end_str}"
    params = {"mode": "cycle", "cyclePreference": "AllTheWay", "bikeProficiency": proficiency}
    if key:
        params["app_key"] = key
    return requests.get(url, params=params)

def convert_to_gpx(journey_data):
    try:
        journey = journey_data["journeys"][0]
        legs = journey["legs"]
    except (KeyError, IndexError):
        return None, None
        
    gpx = ET.Element("gpx", attrib={"version": "1.1", "creator": "TfL Cycle Planner", "xmlns": "http://www.topografix.com/GPX/1/1"})
    trk = ET.SubElement(gpx, "trk")
    name = ET.SubElement(trk, "name")
    name.text = f"TfL Cycle Route"
    trkseg = ET.SubElement(trk, "trkseg")
    
    coordinates = []
    for leg in legs:
        path_str = leg.get("path", {}).get("lineString")
        if path_str:
            coords = json.loads(path_str)
            for coord in coords:
                lat, lon = coord[0], coord[1]
                ET.SubElement(trkseg, "trkpt", attrib={"lat": str(lat), "lon": str(lon)})
                coordinates.append({"lat": lat, "lon": lon})
                
    ET.indent(gpx, space="  ", level=0)
    return ET.tostring(gpx, encoding="utf-8", xml_declaration=True).decode("utf-8"), coordinates

# --- ACTION: GENERATE CLICKED ---
if st.button("Generate Cycle Route", type="primary"):
    if not start_loc or not end_loc:
        st.error("Please enter both locations.")
    else:
        with st.spinner("Finding coordinates..."):
            start_coords = geocode_location(start_loc, tfl_key)
            end_coords = geocode_location(end_loc, tfl_key)
            
        if start_coords and end_coords:
            st.info(f"📍 Route: {start_coords[2]} ➡️ {end_coords[2]}")
            
            with st.spinner("Fetching route from TfL..."):
                response = get_tfl_route_by_coords((start_coords[0], start_coords[1]), (end_coords[0], end_coords[1]), bike_proficiency, tfl_key)
                
                if response.status_code == 200:
                    gpx_data, coords_list = convert_to_gpx(response.json())
                    
                    if gpx_data and coords_list:
                        st.session_state.current_route = {
                            "summary_text": f"📍 Route: {start_coords[2]} ➡️ {end_coords[2]}",
                            "coords_df": pd.DataFrame(coords_list),
                            "gpx_raw": gpx_data
                        }
                    else:
                        st.error("Could not parse coordinate tracking matrices.")
                else:
                    st.error("TfL couldn't map a cycling path between those locations.")
        else:
            st.error("Could not trace one or both of those locations.")

# --- RENDER UI FROM CACHE MEMORY ---
if st.session_state.current_route:
    route = st.session_state.current_route
    
    st.info(route["summary_text"])
    st.success("Route generated successfully!")
    st.map(route["coords_df"])
    
    st.write("---")
    st.write("### 📲 How to open this route in BikeGPX")
    
    # 1. Download GPX Locally
    st.write("**Step 1:** Download the GPX route file to your device:")
    st.download_button(
        label="💾 Download GPX File",
        data=route["gpx_raw"],
        file_name="tfl_cycle_route.gpx",
        mime="application/gpx+xml"
    )
    
    # 2. Upload / Import guide
    st.write("**Step 2:** Choose your import method:")
    
    tab1, tab2 = st.tabs(["💻 Desktop Upload", "📱 Mobile App Import"])
    
    with tab1:
        st.write("If you are on a computer:")
        st.write("1. Open [bikegpx.com](https://bikegpx.com) in your browser.")
        st.write("2. Drag and drop your downloaded `tfl_cycle_route.gpx` file onto their page.")
        st.write("3. Scan the generated QR code using your phone's camera.")
        
    with tab2:
        st.write("If you are on your phone:")
        st.write("1. Open the **BikeGPX** app.")
        st.write("2. Tap **Select Route** ➡️ **Add Route** ➡️ **Import File**.")
        st.write("3. Select your downloaded `tfl_cycle_route.gpx` file from your device downloads folder.")

    # 3. Code preview for quick reference
    with st.expander("📝 View Raw GPX Text"):
        st.code(route["gpx_raw"], language="xml")
