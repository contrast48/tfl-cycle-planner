import streamlit as st
import requests
import urllib.parse
import json
import xml.etree.ElementTree as ET
import pandas as pd

# Page Configuration
st.set_page_config(page_title="TfL Cycle Route to GPX", page_icon="🚲", layout="centered")

st.title("🚲 TfL Cycle Route to GPX Generator")
st.write("Plan your London cycle journey using the official TfL API, preview your route, and download the GPX file for free turn-by-turn navigation on your phone!")

# User inputs
col1, col2 = st.columns(2)
with col1:
    start_loc = st.text_input("Start Location", placeholder="e.g., WC1B 3DG or Waterloo Station")
with col2:
    end_loc = st.text_input("End Location", placeholder="e.g., SW11 4NJ or Battersea Park")

cycle_preference = st.selectbox(
    "Cycling Preference",
    options=["all", "easy", "moderate", "fast"],
    format_func=lambda x: x.capitalize()
)

# Optional API key input
tfl_key = st.text_input("TfL API Primary Key (Optional but recommended for heavy use)", type="password")

def get_tfl_route(start, end, preference, key=None):
    start_enc = urllib.parse.quote(start)
    end_enc = urllib.parse.quote(end)
    url = f"https://api.tfl.gov.uk/Journey/JourneyResults/{start_enc}/to/{end_enc}"
    
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
        
    # Build GPX XML
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
                
    # Format XML nicely
    ET.indent(gpx, space="  ", level=0)
    gpx_string = ET.tostring(gpx, encoding="utf-8", xml_declaration=True).decode("utf-8")
    
    return gpx_string, coordinates

if st.button("Generate Cycle Route", type="primary"):
    if not start_loc or not end_loc:
        st.error("Please enter both a start and end location.")
    else:
        with st.spinner("Calculating optimal cycling route from TfL..."):
            response = get_tfl_route(start_loc, end_loc, cycle_preference, tfl_key)
            
            if response.status_code == 200:
                data = response.json()
                gpx_data, coords_list = convert_to_gpx(data)
                
                if gpx_data and coords_list:
                    st.success("Route generated successfully!")
                    
                    # 1. Map preview
                    df = pd.DataFrame(coords_list)
                    st.subheader("Route Preview")
                    st.map(df)
                    
                    # 2. Download Button
                    st.download_button(
                        label="💾 Download GPX File",
                        data=gpx_data,
                        file_name="tfl_cycle_route.gpx",
                        mime="application/gpx+xml"
                    )
                    
                    st.info("💡 **How to use this:** Send this downloaded `.gpx` file to your mobile phone and open it with free turn-by-turn navigation apps like **BikeGPX** or **OsmAnd**.")
                else:
                    st.error("No route geometry could be found for this journey.")
            else:
                st.error(f"TfL API Error ({response.status_code}). Please double check your addresses/postcodes.")