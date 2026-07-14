import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd
import time
import uuid

st.set_page_config(page_title="TfL Cycle Route to GPX", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to GPX Generator")
st.write("Plan a route, view it, and send it straight to BikeGPX to scan the QR code!")

# Initialize session state to hold temporary live GPX paths
if "gpx_storage" not in st.session_state:
    st.session_state.gpx_storage = {}

# Listen for incoming download requests from BikeGPX
query_params = st.query_params
if "get_file" in query_params:
    file_id = query_params["get_file"]
    if file_id in st.session_state.gpx_storage:
        # Serve the raw GPX XML string directly to BikeGPX
        st.text(st.session_state.gpx_storage[file_id])
        st.stop()
    else:
        st.error("File expired or not found.")
        st.stop()

col1, col2 = st.columns(2)
with col1:
    start_loc = st.text_input("Start Location", placeholder="e.g., WC1B 3DG")
with col2:
    end_loc = st.text_input("End Location", placeholder="e.g., SW11 4NJ")

bike_proficiency = st.selectbox(
    "Route Type / Cycling Pace",
    options=["easy", "moderate", "fast"],
    format_func=lambda x: x.capitalize()
)

tfl_key = st.text_input("TfL API Primary Key (Optional)", type="password")

def geocode_location(query):
    headers = {"User-Agent": "tfl-cycle-route-planner-app"}
    search_query = f"{query}, London, UK" if "london" not in query.lower() else query
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(search_query)}&format=json&limit=1"
    try:
        time.sleep(0.5)
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and len(response.json()) > 0:
            data = response.json()[0]
            return float(data["lat"]), float(data["lon"]), data["display_name"]
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

if st.button("Generate Cycle Route", type="primary"):
    if not start_loc or not end_loc:
        st.error("Please enter both locations.")
    else:
        with st.spinner("Finding coordinates..."):
            start_coords = geocode_location(start_loc)
            end_coords = geocode_location(end_loc)
            
        if start_coords and end_coords:
            st.info(f"📍 Route: {start_coords[2].split(',')[0]} ➡️ {end_coords[2].split(',')[0]}")
            
            with st.spinner("Fetching route from TfL..."):
                response = get_tfl_route_by_coords((start_coords[0], start_coords[1]), (end_coords[0], end_coords[1]), bike_proficiency, tfl_key)
                
                if response.status_code == 200:
                    gpx_data, coords_list = convert_to_gpx(response.json())
                    
                    if gpx_data:
                        st.success("Route generated successfully!")
                        st.map(pd.DataFrame(coords_list))
                        
                        # Generate unique file identifier
                        unique_id = str(uuid.uuid4())
                        st.session_state.gpx_storage[unique_id] = gpx_data
                        
                        # DYNAMICALLY RESOLVE CURRENT PUBLIC DOMAIN
                        try:
                            # Pull active session context headers
                            active_sessions = st.runtime.get_instance()._session_mgr.list_active_sessions()
                            session_info = st.runtime.get_instance()._session_mgr.get_active_session_info(active_sessions[0])
                            current_host = session_info.request.host
                            
                            # Safely check if we are on HTTP or HTTPS
                            protocol = "https" if "localhost" not in current_host else "http"
                            file_public_url = f"{protocol}://{current_host}/?get_file={unique_id}"
                        except Exception:
                            # Ultimate structural fallback if runtime inspection fails
                            file_public_url = f"http://localhost:8501/?get_file={unique_id}"
                        
                        # Build out the BikeGPX deep link
                        bikegpx_url = f"https://bikegpx.com/?url={urllib.parse.quote(file_public_url)}"
                        
                        st.write("### 📲 Export Options")
                        st.link_button("🚀 Send Directly to BikeGPX (Opens QR Code)", bikegpx_url)
                        
                        st.download_button(
                            label="💾 Download GPX File Locally",
                            data=gpx_data,
                            file_name="tfl_cycle_route.gpx",
                            mime="application/gpx+xml"
                        )
                    else:
                        st.error("Could not trace path mapping structures.")
                else:
                    st.error("TfL couldn't map a cycling path here.")
