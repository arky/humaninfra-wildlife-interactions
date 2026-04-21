# Human Infrastructure and Wildlife Interactions Detection

Github repository: *github.com/arky/humaninfra-wildlife-interactions*

> Wildlife stop hotspot detection app using MovingPandas and OSM road data. Switched from OSMnx to overpy for network downloads to fix Overpass API reliability issues.

## Description

This MoveApp written in Python detects where wildlife trajectories cross human infrastructure using OpenStreetMap (OSM) data and produces an interactive map of those crossings.

It detects stops from animal trajectories, then queries all infrastructure features (roads, railways, power lines, barriers, waterways) that intersect the full trajectory path. Crossing points are identified and visualised on a zoomable Leaflet map saved as an HTML artefact.

Biologists and conservation projects can use this to identify which infrastructure features animals actually cross — a direct indicator of interaction risk. All detection and query parameters are configurable through the MoveApps workflow UI.

## Documentation

Stop detection is based on [MovingPandas TrajectoryStopDetector](https://movingpandas.readthedocs.io/en/main/trajectorystopdetector.html). A stop is recorded when an animal remains within a configurable diameter area for at least a configurable minimum duration. Detection runs in parallel across all trajectories for performance.

Infrastructure data is retrieved from OpenStreetMap via the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) using [overpy](https://python-overpy.readthedocs.io/). A single bounding-box query covering the full trajectory area fetches all relevant feature types in one request. Four public Overpass mirrors are tried in order (fastest first); if one is unavailable or times out the next is used automatically. Queries covering more than ~111 × 111 km are rejected early with a clear log message, as Overpass cannot serve areas that large reliably.

Intersection points between trajectory paths and infrastructure features are computed using [Shapely](https://shapely.readthedocs.io/). Results are visualised in an interactive [Folium](https://python-visualization.github.io/folium/) map with toggleable layers per infrastructure type.

### Analysis pipeline

1. **Stop Detection** — `TrajectoryStopDetector` runs in parallel across all trajectories via `app/parallel.py` to extract stop points with their duration
2. **Infrastructure Query** — overpy fetches all OSM features (roads, railways, power lines, barriers, waterways) within the trajectory bounding box + buffer in a single Overpass request
3. **Intersection Analysis** — each trajectory `LineString` is intersected against all queried features; crossing points are recorded with their infrastructure type and name
4. **Visualisation** — interactive Folium map saved as `infrastructure_crossings.html`:
   - Toggleable layers per infrastructure type (highway, railway, power, barrier, waterway)
   - Trajectory paths
   - Stop points sized by duration
   - Crossing points coloured by infrastructure type with popup details

### Infrastructure types queried

| Type | OSM tag | Colour |
|---|---|---|
| Highway | `highway` (filtered by Road Network Coverage) | Orange |
| Railway | `railway` | Purple |
| Power line | `power~line\|minor_line\|cable` | Yellow |
| Barrier | `barrier` | Red |
| Waterway | `waterway` | Blue |

### Input data

MovingPandas `TrajectoryCollection` in Movebank format. Requires the [link-r-python](https://github.com/movestore/link-r-python) MoveApp to convert R `move2` objects into MovingPandas `TrajectoryCollection`.

### Output data

MovingPandas `TrajectoryCollection` in Movebank format (unchanged).

### Artefacts

`infrastructure_crossings.html` — interactive Leaflet map with:
- All queried OSM infrastructure features, coloured by type (toggleable per type)
- Trajectory paths
- Stop points (red circles sized by duration)
- Crossing points (coloured by infrastructure type; click for type, name, and trajectory ID)

### Settings

All parameters are configurable in the MoveApps workflow UI:

| UI Label | ID | Type | Default | Description |
|---|---|---|---|---|
| Minimum Stop Duration (seconds) | `min_duration` | Integer | `180` | Minimum time in seconds an animal must remain within the stop area. Increase to filter out brief pauses; decrease to capture shorter stops. |
| Maximum Stop Diameter (metres) | `max_diameter` | Integer | `100` | Diameter in metres within which the animal must remain to qualify as a stop. Smaller values require the animal to stay in a tighter area. |
| Bounding Box Buffer (degrees) | `buffer` | Double | `0.005` | Padding in degrees added around the trajectory bounding box when querying OSM infrastructure. |
| Road Network Coverage | `road_network` | Radio buttons | `major` | Predefined road type presets — see table below. Ignored if `custom_filter` is set. |
| Custom OSM Tag Filter | `custom_filter` | String | *(empty)* | Advanced: Overpass filter string that overrides Road Network Coverage when set. Example: `["highway"~"motorway\|primary\|cycleway"]` |

#### Road Network Coverage presets

| Option | OSM filter | Use case |
|---|---|---|
| Minimal | `["highway"~"motorway\|trunk"]` | Fastest download; major corridors only |
| Major roads *(default)* | `["highway"~"motorway\|trunk\|primary\|secondary\|tertiary"]` | Balanced coverage |
| All roads | `["highway"]` | Most complete; slowest download |

## Dependencies

| Package | Purpose |
|---|---|
| movingpandas | Trajectory handling and parallel stop detection |
| overpy | Overpass API client for OSM infrastructure queries |
| geopandas | Spatial data handling and intersection analysis |
| shapely | Geometry operations (LineString, intersection) |
| folium | Interactive Leaflet map generation |
| geopy | Distance calculation utilities |
