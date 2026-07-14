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
    Resolves locations safely without using Nominatim/OpenStreetMap to avoid 429 rate limits.
    1. Uses postcodes.io for UK postcodes (highly reliable, no limits).
    2. Uses TfL's native Place Search API for London landmarks, stations, and addresses.
    """
    clean_query = query.strip().replace(" ", "").upper()
    
    # --- Step 1: Check if it's a postcode (postcodes.io) ---
    if len(clean_query) >= 5 and len(clean_query) <= 8:
        postcode_url = f"https://api.postcodes.io/postcodes/{clean_query}"
        try:
            res = requests.get(postcode_url, timeout=5)
            if res.status_code == 200:
                pdata = res.json()["result"]
                return float(pdata["latitude"]), float(pdata["longitude"]), f"{pdata['postcode']}, London"
        except Exception:
            pass

    # --- Step 2: Use TfL's native Place Search (Free, highly optimized for London, never blocks) ---
    tfl_search_url = "https://api.tfl.gov.uk/Place/Search"
    params = {"name": query}
    if key:
        params["app_key"] = key
        
    try:
        response = requests.get(tfl_search_url, params=params, timeout=8)
        if response.status_code == 200:
            results = response.json()
            if len(results) > 0:
                # Grab the first matched result from TfL's database
                match = results[0]
                return float(match["lat"]), float(match["lon"]), match.get("name", query)
            else:
                st.error(f"🔍 TfL could not find any locations matching '{query}'.")
        else:
            st.error(f"❌ TfL Location Search failed (Code {response.status_code}).")
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
            start_coords = geocode_location(start_loc, tfl_key)
            end_coords = geocode_location(end_loc, tfl_key)
            
        if start_coords and end_coords:
            st.info(f"📍 Route: {start_coords[2]} ➡️ {end_coords[2]}")
            
            with st.spinner("Fetching route from TfL..."):
                response = get_tfl_route_by_coords((start_coords[0], start_coords[1]), (end_coords[0], end_coords[1]), bike_proficiency, tfl_key)
                
                if response.status_code == 200:
                    gpx_data, coords_list = convert_to_gpx(response.json())
                    
                    if gpx_data:
                        # --- SECURE TEMPORARY EXPORT TRANSIT ---
                        with st.spinner("Preparing secure link for BikeGPX..."):
                            try:
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
                            "summary_text": f"📍 Route: {start_coords[2]} ➡️ {end_coords[2]}",
                            "coords_df": pd.DataFrame(coords_list),
                            "bikegpx_url": bikegpx_url,
                            "gpx_raw": gpx_data
                        }
                    else:
                        st.error("Could not parse coordinates structure.")
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
