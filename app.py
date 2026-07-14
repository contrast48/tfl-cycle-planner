import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd
import segno
from io import BytesIO

st.set_page_config(page_title="TfL Cycle Route Planner", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to Phone Generator")
st.write("Plan a route, view it, and scan the QR code to open it directly on your phone!")

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
    clean_query = query.strip().replace(" ", "").upper()
    
    # 1. Check if it looks like a postcode (postcodes.io)
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
                        # Create a universal map link using the start/end coordinates
                        # This avoids large data size limits, and lets you navigate instantly via phone apps
                        maps_url = f"https://www.google.com/maps/dir/?api=1&origin={start_coords[0]},{start_coords[1]}&destination={end_coords[0]},{end_coords[1]}&travelmode=bicycling"
                        
                        # Generate the native QR code image block
                        qr = segno.make(maps_url)
                        qr_buffer = BytesIO()
                        qr.save(qr_buffer, kind='png', scale=5)
                        qr_bytes = qr_buffer.getvalue()
                        
                        st.session_state.current_route = {
                            "summary_text": f"📍 Route: {start_coords[2]} ➡️ {end_coords[2]}",
                            "coords_df": pd.DataFrame(coords_list),
                            "qr_bytes": qr_bytes,
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
    
    # Display the native QR code cleanly in the layout center
    st.write("---")
    st.write("### 📲 Scan to Navigate")
    st.write("Scan this code with your mobile camera to launch the route with turn-by-turn cycling directions immediately:")
    
    col_left, col_mid, col_right = st.columns([1, 2, 1])
    with col_mid:
        st.image(route["qr_bytes"], width=280)
        
    st.write("---")
    st.write("### 💾 Backup Local Download")
    st.download_button(
        label="Download Raw GPX File",
        data=route["gpx_raw"],
        file_name="tfl_cycle_route.gpx",
        mime="application/gpx+xml"
    )
