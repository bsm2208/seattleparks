"""load seattle parksdata, create a folium map with markers, and publish to streamlit app"""

from pathlib import Path
import pandas as pd
import json
import folium
import streamlit as st
from streamlit_folium import st_folium

# ======================================================================
# PROJECT PATHS
# ======================================================================
project_root =  Path(__file__).resolve().parents[1]
parks_df = pd.read_csv(project_root / "data" / "parks_with_neighborhoods.csv")

#print(parks_df.head())

#create a map centered on Seattle
seattle_map = folium.Map(location = [47.6062, -122.3320], zoom_start=11)

#add park markers on the map
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

# ======================================================================
# STREAMLIT APP DESIGN
# ======================================================================

st.header("Seattle Parks")
st_data = st_folium(seattle_map, width=700, height=500)

project_root = Path(__file__).resolve().parents[1]
parks_df = pd.read_csv(project_root / "data" / "parks_with_neighborhoods.csv")

seattle_map = folium.Map(location=[47.6062, -122.3320], zoom_start=11)

# Serialize park data to JSON for JS to consume
parks_data = []
for _, row in parks_df.iterrows():
    parks_data.append({
        "name":         row["Name"],
        "lat":          row["Y Coord"],
        "lon":          row["X Coord"],
        "rating":       float(row["rating"]) if pd.notna(row["rating"]) else 0,
        "neighborhood": str(row.get("L_HOOD", "Unknown")),
        "summary":      str(row["summary"]),
        "address":      str(row["Address"]),
    })

neighborhoods = sorted(parks_df["L_HOOD"].dropna().unique().tolist())

# Inject data + filter UI + logic as raw HTML/JS
filter_html = f"""
<div id="filter-panel" style="
    position: fixed; top: 80px; right: 10px; z-index: 9999;
    background: white; padding: 15px; border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.3); min-width: 200px;
    font-family: Arial, sans-serif; font-size: 13px;">

    <b>🌿 Filter Parks</b><hr style="margin:8px 0">

    <label>⭐ Min Rating:</label><br>
    <input type="range" id="rating-slider" min="0" max="5" step="0.5" value="0"
           style="width:100%" oninput="updateFilters()">
    <span id="rating-label">0+</span><br><br>

    <label>📍 Neighborhood:</label><br>
    <select id="neighborhood-select" style="width:100%; padding:4px"
            onchange="updateFilters()">
        <option value="all">All Neighborhoods</option>
        {"".join(f'<option value="{n}">{n}</option>' for n in neighborhoods)}
    </select><br><br>

    <div id="park-count" style="color:#666; font-size:12px"></div>
</div>

<script>
const parksData = {json.dumps(parks_data)};
const markers = [];

function getRatingColor(r) {{
    if (r >= 4.5) return "#2ecc71";
    if (r >= 4.0) return "#27ae60";
    if (r >= 3.0) return "#f39c12";
    return "#e74c3c";
}}

// Wait for map to initialise
document.addEventListener("DOMContentLoaded", function() {{
    const mapObj = Object.values(window).find(
        v => v && v._leaflet_id && v.addLayer
    );

    parksData.forEach(function(p) {{
        const color = getRatingColor(p.rating);
        const icon = L.divIcon({{
            html: `<div style="font-size:12px;color:${{color}}">
                       <i class="fa-solid fa-tree"></i></div>`,
            className: ""
        }});
        const marker = L.marker([p.lat, p.lon], {{icon: icon}})
            .bindPopup(
                `<b>${{p.name}}</b><br>
                 ⭐ ${{p.rating}}<br>
                 📍 ${{p.neighborhood}}<br>
                 📝 ${{p.summary}}<br>
                 🏠 ${{p.address}}`,
                {{maxWidth: 300}}
            )
            .bindTooltip(p.name);
        marker._parkData = p;
        marker.addTo(mapObj);
        markers.push(marker);
    }});

    updateFilters();  // set initial count label

    function updateFilters() {{
        const minRating    = parseFloat(document.getElementById("rating-slider").value);
        const neighborhood = document.getElementById("neighborhood-select").value;
        document.getElementById("rating-label").textContent = minRating + "+";

        let visible = 0;
        markers.forEach(function(m) {{
            const p  = m._parkData;
            const ok = p.rating >= minRating &&
                       (neighborhood === "all" || p.neighborhood === neighborhood);
            if (ok) {{ m.addTo(mapObj);  visible++; }}
            else   {{ mapObj.removeLayer(m); }}
        }});
        document.getElementById("park-count").textContent =
            `Showing ${{visible}} of ${{markers.length}} parks`;
    }}

    // Expose to global scope so the inline oninput/onchange handlers can call it
    window.updateFilters = updateFilters;
}});
</script>
"""

seattle_map.get_root().html.add_child(folium.Element(filter_html))
seattle_map.save("seattle_parks_map.html")
print("Map saved!")
