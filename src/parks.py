"""load seattle parksdata, create a folium map with markers, and publish to streamlit app"""

from pathlib import Path
import pandas as pd
import folium
from streamlit_folium import st_folium

# ======================================================================
# PROJECT PATHS
# ======================================================================
project_root =  Path(__file__).resolve().parents[1]
parks_df = pd.read_csv(project_root / "data" / "parks_with_ratings.csv")

#print(parks_df.head())

#create a map centered on Seattle
seattle_map = folium.Map(location = [47.6062, -122.3320], zoom_start=11)

for row in parks_df.iterrows():
    row_values = row[1]
    location=[row_values["Y Coord"], row_values["X Coord"]]
    popup = folium.Popup("Name: {}<br>Rating: {}<br>Summary: {}<br>Address: {}".format(
        row_values["Name"],
        row_values["rating"],
        row_values["summary"],
        row_values["Address"]
    ), max_width=300)
    marker = folium.Marker(location=location, 
                            popup=popup,
                            icon=folium.DivIcon(html="""
                            <div style="font-size: 10px; color: green;">
                            <i class="fa-solid fa-tree"></i></div>""")
                            )
    marker.add_to(seattle_map)

seattle_map.save("seattle_parks_map.html")

st_data = st_folium(seattle_map, width=700, height=500)
