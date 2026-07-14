import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd
import time

st.set_page_config(page_title="TfL Cycle Route to GPX", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to GPX Generator")
st.write("Enter any London postcode or address. We will automatically resolve the location and get your cycle path!")

col1, col2 = st.columns(2)
with col1:
    start_loc = st.text_input("Start Location", placeholder="e.g., WC1B 3DG or Waterloo")
with col2:
    end_loc = st.text_input("End Location", placeholder="e.g., SW11 4NJ or Battersea Park")

cycle_preference = st.selectbox(
    "Cycling Preference",
    options=["all", "easy", "moderate", "fast"],
    format_func=lambda x: x.capitalize()
)

tfl_key = st.text_input("TfL API Primary Key (Optional)", type="password")

def geocode_location(query):
    """
    Converts a postcode or address to latitude, longitude using OpenStreetMap (Free, no key needed).
    Ensures search is biased towards London, UK.
    """
    headers = {"User-Agent": "tfl-cycle-route-planner-app"}
    # Append 'London, UK' to keep results localized if a generic address is typed
    search_query = f"{query}, London, UK" if "london" not in query.lower() else query
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(search_query)}&format=json&limit=1"
    
    try:
        # Respect OSM usage policy (slight delay)
        time.sleep(0.5) 
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and len(response.json()) > 0:
            data = response.json()[0]
            return float(data["lat"]), float(data["lon"]), data["display_name"]
    except Exception as e:
        st.write(f"Geocoding error: {e}")
    return None

def get_tfl_route_by_coords(start_coords, end_coords, preference, key=None):
    """
    Queries TfL using guaranteed coordinates, bypassing the 300 Multiple Choices error.
    """
    start_str = f"{start_coords[0]},{start_coords[1]}"
    end_str = f"{end_coords[0]},{end_coords[1]}"
    
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{start_str}/to/{end_str}"
    
    params = {
        "mode": "cycle",
        "cyclePreference": preference,
    }
    if key:
        params["app_key"] = key
        
    res = requests.get(url, params=params)
    return res

def convert_to_gpx(journey_data):
    try:
        journey = journey_data["journeys"][0]
        legs = journey["legs"]
    except (KeyError, IndexError):
        return None, None
        
    gpx = ET.Element("gpx", attrib={
        "version": "1.1",
        "creator": "TfL Cycle Planner Tool",
        "xmlns": "http://www.topografix.com/GPX/1/1"
    })
    trk = ET.SubElement(gpx, "trk")
    name = ET.SubElement(trk, "name")
    name.text = f"TfL Cycle: {legs[0]['instruction']['summary']}"
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
    gpx_string = ET.tostring(gpx, encoding="utf-8", xml_declaration=True).decode("utf-8")
    
    return gpx_string, coordinates

if st.button("Generate Cycle Route", type="primary"):
    if not start_loc or not end_loc:
        st.error("Please enter both a start and end location.")
    else:
        with st.spinner("Finding coordinates for your locations..."):
            start_coords = geocode_location(start_loc)
            end_coords = geocode_location(end_loc)
            
        if not start_coords:
            st.error(f"Could not find coordinates for: '{start_loc}'. Please try a different postcode or station name.")
        elif not end_coords:
            st.error(f"Could not find coordinates for: '{end_loc}'. Please try a different postcode or station name.")
        else:
            st.info(f"📍 Route: {start_coords[2].split(',')[0]} ➡️ {end_coords[2].split(',')[0]}")
            
            with st.spinner("Requesting cycle route from TfL..."):
                response = get_tfl_route_by_coords(
                    (start_coords[0], start_coords[1]), 
                    (end_coords[0], end_coords[1]), 
                    cycle_preference, 
                    tfl_key
                )
                
                if response.status_code == 200:
                    data = response.json()
                    gpx_data, coords_list = convert_to_gpx(data)
                    
                    if gpx_data and coords_list:
                        st.success("Route generated successfully!")
                        
                        df = pd.DataFrame(coords_list)
                        st.subheader("Route Preview")
                        st.map(df)
                        
                        st.download_button(
                            label="💾 Download GPX File",
                            data=gpx_data,
                            file_name="tfl_cycle_route.gpx",
                            mime="application/gpx+xml"
                        )
                    else:
                        st.error("TfL successfully found the locations, but couldn't generate a cycling route between them.")
                else:
                    st.error(f"TfL API returned an error ({response.status_code}). Details: {response.text}")
