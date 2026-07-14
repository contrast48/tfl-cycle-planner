import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd
import time
import random

st.set_page_config(page_title="TfL Cycle Route to GPX", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to GPX Generator")
st.write("Plan a route, view it, and send it straight to BikeGPX to scan the QR code!")

# Permanent UI memory state
if "current_route" not in st.session_state:
    st.session_state.current_route = None

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
    clean_query = query.strip().replace(" ", "").upper()
    
    # 1. Postcodes.io fast-path
    if len(clean_query) >= 5 and len(clean_query) <= 8:
        postcode_url = f"https://api.postcodes.io/postcodes/{clean_query}"
        try:
            res = requests.get(postcode_url, timeout=5)
            if res.status_code == 200:
                pdata = res.json()["result"]
                return float(pdata["latitude"]), float(pdata["longitude"]), f"{pdata['postcode']}, London, UK"
        except Exception:
            pass

    # 2. OpenStreetMap path
    random_agent = f"tfl_planner_user_{random.randint(100000, 999999)}"
    headers = {"User-Agent": random_agent}
    search_query = f"{query}, London, UK" if "london" not in query.lower() else query
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(search_query)}&format=json&limit=1"
    
    try:
        time.sleep(0.6)
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            results = response.json()
            if len(results) > 0:
                data = results[0]
                return float(data["lat"]), float(data["lon"]), data["display_name"]
            else:
                st.error(f"🔍 No map results found for '{query}'.")
        else:
            st.warning(f"⚠️ Map Server returned code {response.status_code}.")
    except Exception as e:
        st.error(f"❌ Geocoding system error: {str(e)}")
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
            start_coords = geocode_location(start_loc)
            end_coords = geocode_location(end_loc)
            
        if start_coords and end_coords:
            st.info(f"📍 Route: {start_coords[2].split(',')[0]} ➡️ {end_coords[2].split(',')[0]}")
            
            with st.spinner("Fetching route from TfL..."):
                response = get_tfl_route_by_coords((start_coords[0], start_coords[1]), (end_coords[0], end_coords[1]), bike_proficiency, tfl_key)
                
                if response.status_code == 200:
                    gpx_data, coords_list = convert_to_gpx(response.json())
                    
                    if gpx_data:
                        # --- SECURE TEMPORARY EXPORT TRANSIT ---
                        with st.spinner("Preparing secure link for BikeGPX..."):
                            try:
                                # We upload the GPX file anonymously to file.io. It auto-deletes immediately after being downloaded once.
                                files = {'file': ('route.gpx', gpx_data, 'application/gpx+xml')}
                                upload_res = requests.post("https://file.io/?expires=1d", files=files, timeout=10)
                                if upload_res.status_code == 200 and upload_res.json().get("success"):
                                    direct_gpx_url = upload_res.json().get("link")
                                else:
                                    direct_gpx_url = None
                            except Exception:
                                direct_gpx_url = None

                        if direct_gpx_url:
                            bikegpx_url = f"https://bikegpx.com/?url={urllib.parse.quote(direct_gpx_url)}"
                        else:
                            bikegpx_url = None
                        
                        st.session_state.current_route = {
                            "summary_text": f"📍 Route: {start_coords[2].split(',')[0]} ➡️ {end_coords[2].split(',')[0]}",
                            "coords_df": pd.DataFrame(coords_list),
                            "bikegpx_url": bikegpx_url,
                            "gpx_raw": gpx_data
                        }
                    else:
                        st.error("Could not parse coordinates structure.")
                else:
                    st.error("TfL couldn't map a cycling path between those locations.")
        else:
            st.error("Could not trace one or both of those addresses. Check warnings above.")

# --- RENDER UI FROM CACHE MEMORY ---
if st.session_state.current_route:
    route = st.session_state.current_route
    
    st.info(route["summary_text"])
    st.success("Route generated successfully!")
    st.map(route["coords_df"])
    
    st.write("### 📲 Export Options")
    if route["bikegpx_url"]:
        st.link_button("🚀 Send Directly to BikeGPX (Opens QR Code)", route["bikegpx_url"])
    else:
        st.warning("⚠️ Secure transfer setup failed. Please use manual download below instead.")
        
    st.download_button(
        label="💾 Download GPX File Locally",
        data=route["gpx_raw"],
        file_name="tfl_cycle_route.gpx",
        mime="application/gpx+xml"
    )
