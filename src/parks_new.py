import pandas as pd
import json
from pathlib import Path
from shapely import wkt
from pyproj import Transformer

def build_parks_map():
    project_root = Path(__file__).resolve().parents[1]
    parks_df = pd.read_csv(project_root / "data" / "parks_with_safety.csv")

    transformer = Transformer.from_crs("EPSG:2926", "EPSG:4326", always_xy=True)

    def convert_boundary(wkt_str):
        if pd.isna(wkt_str):
            return None
        try:
            geom = wkt.loads(wkt_str)
            polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
            result = []
            for poly in polys:
                ring = []
                for x, y in poly.exterior.coords:
                    lon, lat = transformer.transform(x, y)
                    ring.append([lat, lon])
                result.append(ring)
            return result
        except:
            return None

    parks_list = []
    for _, row in parks_df.iterrows():
        if not isinstance(row["Name"], str):
            continue
        try:
            rating = float(row["rating"])
        except (ValueError, TypeError):
            rating = 0.0
        parks_list.append({
            "name":         row["Name"],
            "lat":          row["Y Coord"],
            "lon":          row["X Coord"],
            "rating":       rating,
            "neighborhood": row["L_HOOD"] if pd.notna(row["L_HOOD"]) else "Unknown",
            "summary":      row["summary"] if pd.notna(row["summary"]) else "",
            "address":      row["Address"] if pd.notna(row["Address"]) else "",
            "googlelink":   row["googlelink"] if pd.notna(row["googlelink"]) else "",
            "boundary":     convert_boundary(row["boundary"]),
            "safety_score": float(row["safety_score"]) if pd.notna(row.get("safety_score")) else None,
            "annual_person_crimes": int(row["annual_person_crimes"]) if pd.notna(row.get("annual_person_crimes")) else None
        })

    parks_json = json.dumps(parks_list, ensure_ascii=False)

    # Build neighborhood boundary polygons from geojson
    from collections import defaultdict
    hood_polys = defaultdict(list)
    geojson_path = project_root / "data" / "nma_nhoods_sub.geojson"
    with open(geojson_path) as f:
        gj = json.load(f)
    for feat in gj["features"]:
        lhood = feat["properties"]["L_HOOD"]
        geom = feat["geometry"]
        if geom["type"] == "Polygon":
            ring = [[c[1], c[0]] for c in geom["coordinates"][0]]
            hood_polys[lhood].append(ring)
        elif geom["type"] == "MultiPolygon":
            for poly in geom["coordinates"]:
                ring = [[c[1], c[0]] for c in poly[0]]
                hood_polys[lhood].append(ring)
    hood_json = json.dumps(dict(hood_polys), ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Seattle Parks</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500&display=swap" rel="stylesheet">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --white:#ffffff;
  --surface:#F9FAF8;
  --surface-2:#F2F4F0;
  --border:#E4E8DF;
  --border-strong:#C8D0C0;
  --text:#1C2018;
  --text-2:#6B7560;
  --text-3:#A0A898;
  --sage:#7A9E7E;
  --sage-light:#EBF2EC;
  --sage-mid:#C8DEC9;
  --moss:#4A7C59;
  --amber:#C98A2E;
  --amber-light:#FBF3E2;
  --amber-mid:#F0D49A;
  --rose:#B85C52;
  --rose-light:#FAEDEB;
  --rose-mid:#F0BDB9;
  --accent:#2C3B2D;
  --panel-w:300px;
  --radius:10px;
}}
body{{font-family:'Geist',system-ui,sans-serif;background:var(--surface-2);height:100vh;overflow:hidden}}
#map{{position:fixed;inset:0;z-index:0}}
.leaflet-tile-pane{{filter:saturate(0.7) brightness(1.01) contrast(0.97)}}
.leaflet-control-zoom{{border:1px solid var(--border)!important;border-radius:var(--radius)!important;overflow:hidden;box-shadow:0 1px 6px rgba(44,59,45,0.08)!important}}
.leaflet-control-zoom a{{background:var(--white)!important;color:var(--text)!important;border-bottom:1px solid var(--border)!important;font-weight:400!important;font-size:18px!important;line-height:28px!important;width:28px!important;height:28px!important}}
.leaflet-control-zoom a:last-child{{border-bottom:none!important}}
.leaflet-control-zoom a:hover{{background:var(--surface)!important}}
#header{{
  position:fixed;top:0;left:0;right:0;z-index:800;
  height:52px;background:var(--white);border-bottom:1px solid var(--border);
  display:flex;align-items:center;padding:0 20px;gap:16px;
  box-shadow:0 1px 0 var(--border);
}}
.logo{{display:flex;align-items:center;gap:9px;font-size:15px;font-weight:500;color:var(--text);letter-spacing:-0.3px}}
.logo-dot{{width:26px;height:26px;background:var(--moss);border-radius:8px;display:flex;align-items:center;justify-content:center;flex-shrink:0}}
.logo-dot svg{{width:13px;height:13px;fill:#fff}}
.header-divider{{width:1px;height:20px;background:var(--border);flex-shrink:0}}
#count-badge{{font-size:12px;color:var(--text-2);background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:3px 11px;white-space:nowrap}}
#count-badge strong{{color:var(--text);font-weight:500}}
.header-spacer{{flex:1}}
#panel{{
  position:fixed;top:52px;bottom:0;left:0;width:var(--panel-w);z-index:700;
  background:var(--white);border-right:1px solid var(--border);
  display:flex;flex-direction:column;overflow:hidden;
}}
.panel-top{{padding:18px 18px 0;flex-shrink:0}}
.panel-title{{font-size:10px;font-weight:500;color:var(--text-3);letter-spacing:1px;text-transform:uppercase;margin-bottom:11px}}
.search-box{{position:relative;margin-bottom:4px}}
.search-box svg{{position:absolute;left:11px;top:50%;transform:translateY(-50%);width:13px;height:13px;stroke:var(--text-3);fill:none;stroke-width:1.8;stroke-linecap:round;pointer-events:none}}
#search{{width:100%;padding:8px 10px 8px 32px;border:1px solid var(--border);border-radius:8px;font-family:inherit;font-size:13px;color:var(--text);background:var(--surface);transition:border-color .15s,background .15s;outline:none}}
#search:focus{{border-color:var(--sage);background:var(--white)}}
#search::placeholder{{color:var(--text-3)}}
.sep{{height:1px;background:var(--border);margin:16px -18px}}
.rating-btns{{display:flex;gap:6px;flex-wrap:wrap}}
.rbtn{{
  font-size:12px;padding:5px 11px;border-radius:20px;
  border:1px solid var(--border);cursor:pointer;
  font-family:inherit;font-weight:400;
  background:var(--surface);color:var(--text-2);
  transition:all .15s;white-space:nowrap;
}}
.rbtn:hover{{border-color:var(--border-strong);color:var(--text)}}
.rbtn.active-all{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.rbtn.active-high{{background:var(--sage-light);color:var(--moss);border-color:var(--sage-mid);font-weight:500}}
.rbtn.active-mid{{background:var(--amber-light);color:var(--amber);border-color:var(--amber-mid);font-weight:500}}
.rbtn.active-low{{background:var(--rose-light);color:var(--rose);border-color:var(--rose-mid);font-weight:500}}
.nbhd-select-wrap{{position:relative;margin-top:4px}}
.nbhd-select-wrap svg{{position:absolute;right:10px;top:50%;transform:translateY(-50%);width:12px;height:12px;stroke:var(--text-3);fill:none;stroke-width:2;stroke-linecap:round;pointer-events:none}}
#nbhd-select{{
  width:100%;padding:8px 30px 8px 12px;
  border:1px solid var(--border);border-radius:8px;
  font-family:inherit;font-size:13px;color:var(--text);
  background:var(--surface);appearance:none;-webkit-appearance:none;
  outline:none;cursor:pointer;transition:border-color .15s,background .15s;
}}
#nbhd-select:focus{{border-color:var(--sage);background:var(--white)}}
.panel-footer{{padding:10px 18px 16px;border-top:1px solid var(--border);flex-shrink:0;margin-top:auto}}
#reset{{width:100%;padding:8px;background:var(--surface);border:1px solid var(--border);border-radius:8px;font-family:inherit;font-size:13px;color:var(--text-2);cursor:pointer;transition:all .15s}}
#reset:hover{{background:var(--surface-2);border-color:var(--border-strong);color:var(--text)}}
#map-wrap{{position:fixed;top:52px;left:var(--panel-w);right:0;bottom:0;z-index:0}}
.leaflet-popup-content-wrapper{{border-radius:14px!important;border:1px solid var(--border)!important;box-shadow:0 4px 24px rgba(44,59,45,0.10)!important;padding:0!important;overflow:hidden}}
.leaflet-popup-content{{margin:0!important;width:auto!important}}
.leaflet-popup-tip-container{{margin-top:-1px}}
.leaflet-popup-tip{{background:var(--white)!important;box-shadow:none!important}}
.pop{{padding:15px 17px;min-width:210px;max-width:260px;font-family:'Geist',sans-serif}}
.pop-name{{font-size:14px;font-weight:500;color:var(--text);margin-bottom:7px;line-height:1.3}}
.pop-badge{{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:500;border-radius:20px;padding:3px 9px;margin-bottom:9px;letter-spacing:0.1px}}
.pop-row{{display:flex;align-items:flex-start;gap:6px;font-size:12px;color:var(--text-2);margin-bottom:4px;line-height:1.4}}
.pop-row svg{{width:12px;height:12px;stroke:var(--text-3);fill:none;stroke-width:1.8;stroke-linecap:round;flex-shrink:0;margin-top:1px}}
.pop-row a{{color:var(--moss);text-decoration:none;font-size:12px}}
.pop-row a:hover{{text-decoration:underline}}
.pop-divider{{height:1px;background:var(--border);margin:9px 0}}
.pop-summary{{font-size:12px;color:var(--text-2);line-height:1.55}}
.mk-dot{{
  width:11px;height:11px;
  border-radius:50%;
  border:2px solid currentColor;
  box-shadow:0 1px 4px rgba(44,59,45,0.2);
}}
.safety-badge{{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;border-radius:20px;padding:3px 9px;margin-bottom:9px;margin-left:5px;letter-spacing:0.1px}}
.safety-bar-wrap{{display:flex;align-items:center;gap:7px;margin-bottom:9px}}
.safety-bar-bg{{flex:1;height:4px;background:var(--border);border-radius:4px;overflow:hidden}}
.safety-bar-fill{{height:100%;border-radius:4px;transition:width .3s}}
</style>
</head>
<body>
<div id="header">
  <div class="logo">
    <div class="logo-dot">
      <svg viewBox="0 0 24 24"><path d="M12 2C8 2 5 5 5 9c0 5 7 13 7 13s7-8 7-13c0-4-3-7-7-7zm0 9.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z"/></svg>
    </div>
    Seattle Parks
  </div>
  <div class="header-divider"></div>
  <div id="count-badge">Loading…</div>
  <div class="header-spacer"></div>
</div>
<div id="panel">
  <div class="panel-top">
    <div class="panel-title">Search</div>
    <div class="search-box">
      <svg viewBox="0 0 16 16"><circle cx="6.5" cy="6.5" r="4.5"/><line x1="10.5" y1="10.5" x2="14" y2="14"/></svg>
      <input type="text" id="search" placeholder="Search parks…" oninput="applyFilters()">
    </div>
    <div class="sep"></div>
    <div class="panel-title">Rating</div>
    <div class="rating-btns">
      <button class="rbtn active-all" id="rbtn-all"  onclick="setRating('all')">All</button>
      <button class="rbtn"            id="rbtn-high" onclick="setRating('high')">4.5+ Excellent</button>
      <button class="rbtn"            id="rbtn-mid"  onclick="setRating('mid')">3–4.5 Good</button>
      <button class="rbtn"            id="rbtn-low"  onclick="setRating('low')">&lt;3 Fair</button>
    </div>
    <div class="sep"></div>
    <div class="panel-title">Safety</div>
    <div class="rating-btns">
      <button class="rbtn active-all" id="sbtn-all"  onclick="setSafety('all')">All</button>
      <button class="rbtn"            id="sbtn-high" onclick="setSafety('high')">7.5+ Low crime</button>
      <button class="rbtn"            id="sbtn-mid"  onclick="setSafety('mid')">5–7.5 Moderate</button>
      <button class="rbtn"            id="sbtn-low"  onclick="setSafety('low')">&lt;5 High crime</button>
    </div>
    <div class="sep"></div>
    <div class="panel-title">Neighborhood</div>
    <div class="nbhd-select-wrap">
      <svg viewBox="0 0 12 12"><polyline points="2,4 6,8 10,4"/></svg>
      <select id="nbhd-select" onchange="applyFilters()">
        <option value="all">All neighborhoods</option>
      </select>
    </div>
  </div>
  <div class="panel-footer">
    <button id="reset" onclick="resetAll()">Reset all filters</button>
  </div>
</div>
<div id="map-wrap">
  <div id="map"></div>
</div>
<script>
const map = L.map('map',{{zoomControl:false}}).setView([47.6062,-122.3320],12);
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png',{{
  attribution:'© OpenStreetMap © CARTO',subdomains:'abcd',maxZoom:19
}}).addTo(map);
L.control.zoom({{position:'bottomright'}}).addTo(map);

const parks = {parks_json};
const markers = [];
let activeRating = 'all';
let activeSafety = 'all';
let hoverLayer = null;
let pinnedLayer = null;
let pinnedMarker = null;

function rColor(r){{
  if(r>=4.5) return {{color:'#4A7C59',bg:'#EBF2EC',text:'#2D5C3A',mid:'#C8DEC9'}};
  if(r>=3.0) return {{color:'#C98A2E',bg:'#FBF3E2',text:'#8A5A10',mid:'#F0D49A'}};
  return {{color:'#B85C52',bg:'#FAEDEB',text:'#7A2E26',mid:'#F0BDB9'}};
}}

function sColor(s){{
  if(s>=7.5) return {{color:'#4A7C59',bg:'#EBF2EC',text:'#2D5C3A'}};
  if(s>=5.0) return {{color:'#C98A2E',bg:'#FBF3E2',text:'#8A5A10'}};
  return {{color:'#B85C52',bg:'#FAEDEB',text:'#7A2E26'}};
}}

function safetyLabel(s){{
  if(s>=7.5) return "Low crime";
  if(s>=5.0) return "Moderate";
  return "High crime";
}}

function ratingInRange(rating, range){{
  if(range==='all')  return true;
  if(range==='high') return rating>=4.5;
  if(range==='mid')  return rating>=3.0 && rating<4.5;
  if(range==='low')  return rating<3.0;
  return true;
}}

parks.forEach(p => {{
  const c = rColor(p.rating);
  const icon = L.divIcon({{
    html:`<div class="mk-dot" style="color:${{c.color}};border-color:${{c.color}};background:${{c.bg}}"></div>`,
    className:'',iconSize:[11,11],iconAnchor:[5,5],popupAnchor:[0,-12]
  }});
  const stars = p.rating>0 ? ('★'.repeat(Math.floor(p.rating))+(p.rating%1>=0.5?'½':'') + ' ' + p.rating.toFixed(1)) : 'No rating';
  const safetyRow = p.safety_score != null ? `
    <div class="safety-bar-wrap">
      <span class="safety-badge" style="background:${{sColor(p.safety_score).bg}};color:${{sColor(p.safety_score).text}};border:1px solid ${{sColor(p.safety_score).color}}">
        <svg viewBox="0 0 12 12" width="10" height="10" fill="currentColor"><path d="M6 1L1 3v4c0 2.5 2.2 4.4 5 5 2.8-.6 5-2.5 5-5V3L6 1z"/></svg>
        ${{safetyLabel(p.safety_score)}} · ${{p.safety_score}}/10
      </span>
    </div>` : '';
  const pop = L.popup({{maxWidth:280}}).setContent(`
    <div class="pop">
      <div class="pop-name">${{p.name}}</div>
      <span class="pop-badge" style="background:${{c.bg}};color:${{c.text}};border:1px solid ${{c.mid}}">${{stars}}</span>
      ${{safetyRow}}
      <div class="pop-row">
        <svg viewBox="0 0 16 16"><circle cx="8" cy="6" r="3"/><path d="M8 15s-5-4.5-5-9a5 5 0 0110 0c0 4.5-5 9-5 9z"/></svg>
        ${{p.neighborhood}}
      </div>
      <div class="pop-row">
        <svg viewBox="0 0 16 16"><rect x="2" y="4" width="12" height="9" rx="1"/><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1"/></svg>
        ${{p.address}}
      </div>
      ${{p.googlelink ? `
      <div class="pop-row">
        <svg viewBox="0 0 16 16"><path d="M10 2h4v4"/><line x1="14" y1="2" x2="8" y2="8"/><path d="M7 3H3a1 1 0 00-1 1v9a1 1 0 001 1h9a1 1 0 001-1V9"/></svg>
        <a href="${{p.googlelink}}" target="_blank">Open in Google Maps</a>
      </div>` : ''}}
      ${{p.summary ? `<div class="pop-divider"></div><div class="pop-summary">${{p.summary}}</div>` : ''}}
    </div>`);

  const m = L.marker([p.lat,p.lon],{{icon}}).bindPopup(pop);
  m._d = p;

  function makeBoundary(){{
    if(!p.boundary) return null;
    const c2 = rColor(p.rating);
    return L.polygon(p.boundary, {{
      color: c2.color, fillColor: c2.color,
      fillOpacity: 0.15, weight: 1.5, opacity: 0.6
    }}).addTo(map);
  }}

  m.on('mouseover', function(){{
    if(pinnedMarker === m) return;
    if(hoverLayer) {{ map.removeLayer(hoverLayer); hoverLayer=null; }}
    hoverLayer = makeBoundary();
  }});
  m.on('mouseout', function(){{
    if(pinnedMarker === m) return;
    if(hoverLayer) {{ map.removeLayer(hoverLayer); hoverLayer=null; }}
  }});
  m.on('click', function(e){{
    L.DomEvent.stopPropagation(e);
    if(pinnedMarker && pinnedMarker !== m) {{
      pinnedMarker.closePopup();
      if(pinnedLayer) {{ map.removeLayer(pinnedLayer); pinnedLayer=null; }}
    }}
    if(hoverLayer) {{ map.removeLayer(hoverLayer); hoverLayer=null; }}
    pinnedMarker = m;
    if(pinnedLayer) {{ map.removeLayer(pinnedLayer); pinnedLayer=null; }}
    pinnedLayer = makeBoundary();
    m.openPopup();
  }});

  m.addTo(map);
  markers.push(m);
}});

map.on('click', function(){{
  if(pinnedMarker) {{ pinnedMarker.closePopup(); pinnedMarker=null; }}
  if(pinnedLayer)  {{ map.removeLayer(pinnedLayer); pinnedLayer=null; }}
  if(hoverLayer)   {{ map.removeLayer(hoverLayer);  hoverLayer=null;  }}
}});

// Neighborhood boundaries
const hoodPolys = {hood_json};
let hoodBoundaryLayer = null;

function showHoodBoundary(hood){{
  if(hoodBoundaryLayer) {{ map.removeLayer(hoodBoundaryLayer); hoodBoundaryLayer=null; }}
  if(hood === 'all' || !hoodPolys[hood]) return;
  hoodBoundaryLayer = L.polygon(hoodPolys[hood], {{
    color: '#006e82',
    fillColor: '#78eaff',
    fillOpacity: 0.18,
    weight: 1.5,
    opacity: 0.6,
    dashArray: '4 3'
  }}).addTo(map);
  // Fly map to fit the neighborhood boundary
  map.flyToBounds(hoodBoundaryLayer.getBounds(), {{
    paddingTopLeft: [20, 20],
    paddingBottomRight: [20, 20],
    maxZoom: 15,
    duration: 0.8
  }});
}}

// Neighborhood dropdown
const hoods = [...new Set(parks.map(p=>p.neighborhood))].filter(Boolean).sort();
const sel = document.getElementById('nbhd-select');
hoods.forEach(h=>{{
  const opt=document.createElement('option');
  opt.value=h; opt.textContent=h; sel.appendChild(opt);
}});

function setRating(range){{
  activeRating = range;
  document.getElementById('rbtn-all').className  = 'rbtn' + (range==='all'  ? ' active-all'  : '');
  document.getElementById('rbtn-high').className = 'rbtn' + (range==='high' ? ' active-high' : '');
  document.getElementById('rbtn-mid').className  = 'rbtn' + (range==='mid'  ? ' active-mid'  : '');
  document.getElementById('rbtn-low').className  = 'rbtn' + (range==='low'  ? ' active-low'  : '');
  applyFilters();
}}

function setSafety(range){{
  activeSafety = range;
  document.getElementById('sbtn-all').className  = 'rbtn' + (range==='all'  ? ' active-all'  : '');
  document.getElementById('sbtn-high').className = 'rbtn' + (range==='high' ? ' active-high' : '');
  document.getElementById('sbtn-mid').className  = 'rbtn' + (range==='mid'  ? ' active-mid'  : '');
  document.getElementById('sbtn-low').className  = 'rbtn' + (range==='low'  ? ' active-low'  : '');
  applyFilters();
}}

function safetyInRange(score, range){{
  if(range==='all')  return true;
  if(score==null)    return range==='all';
  if(range==='high') return score>=7.5;
  if(range==='mid')  return score>=5.0 && score<7.5;
  if(range==='low')  return score<5.0;
  return true;
}}

function applyFilters(){{
  const q = document.getElementById('search').value.trim().toLowerCase();
  const activeHood = document.getElementById('nbhd-select').value;
  showHoodBoundary(activeHood);
  let vis=0;
  markers.forEach(m=>{{
    const p=m._d;
    const ok = ratingInRange(p.rating, activeRating)
      && safetyInRange(p.safety_score, activeSafety)
      && (activeHood==='all' || p.neighborhood===activeHood)
      && (!q || p.name.toLowerCase().includes(q));
    if(ok){{ if(!map.hasLayer(m)) m.addTo(map); vis++; }}
    else  {{ if(map.hasLayer(m))  map.removeLayer(m); }}
  }});
  document.getElementById('count-badge').innerHTML=`<strong>${{vis}}</strong> of ${{markers.length}} parks`;
}}

function resetAll(){{
  document.getElementById('search').value='';
  document.getElementById('nbhd-select').value='all';
  showHoodBoundary('all');
  map.flyTo([47.6062,-122.3320], 12, {{duration: 0.8}});
  setSafety('all');
  setRating('all');
}}

applyFilters();
</script>
</body>
</html>"""

    out_path = project_root / "output" / "seattle_parks_map.html"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved → {out_path}")

if __name__ == "__main__":
    build_parks_map()