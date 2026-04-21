from sdk.moveapps_spec import hook_impl
from movingpandas import TrajectoryCollection
import movingpandas as mpd
import logging
import time

import geopandas as gpd
import folium
import overpy
from shapely import STRtree, intersection as shapely_intersection
from shapely.geometry import LineString

from datetime import timedelta
from app.parallel import parallelize

ROAD_FILTERS = {
    "minimal": '["highway"~"motorway|trunk"]',
    "major":   '["highway"~"motorway|trunk|primary|secondary|tertiary"]',
    "all":     '["highway"]',
}

INFRA_COLORS = {
    "highway":  "#e07b39",
    "railway":  "#5b5ea6",
    "power":    "#f5c518",
    "barrier":  "#c0392b",
    "waterway": "#2980b9",
    "other":    "#888888",
}

OVERPASS_ENDPOINTS = [
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.osm.ch/api",
    "https://overpass-api.de/api",
]

MAX_BBOX_DEG2 = 1.0  # ~111 × 111 km; larger queries time out on Overpass


def _overpass_query(query: str) -> overpy.Result:
    """Try each Overpass endpoint in order; return the first non-empty result."""
    api = overpy.Overpass()
    for url in OVERPASS_ENDPOINTS:
        interp = url if url.endswith('/interpreter') else url.rstrip('/') + '/interpreter'
        try:
            api.url = interp
            result = api.query(query)
            n = len(result.ways)
            logging.info(f"  {n} ways, {len(result.nodes)} nodes via {url}")
            if n == 0:
                logging.warning(f"  [{url}] returned 0 ways — trying next endpoint")
                continue
            return result
        except Exception as e:
            logging.warning(f"  [{url}] failed: {e} — trying next endpoint")
    return None


def _ways_to_gdf(result: overpy.Result) -> gpd.GeoDataFrame:
    """Convert an overpy Result to a GeoDataFrame of labelled LineStrings."""
    node_coords = {n.id: (float(n.lon), float(n.lat)) for n in result.nodes}
    records = []
    for way in result.ways:
        coords = [node_coords[n.id] for n in way.nodes if n.id in node_coords]
        if len(coords) < 2:
            continue
        tags = way.tags
        for key in ('highway', 'railway', 'power', 'barrier', 'waterway'):
            if tags.get(key):
                itype = key
                break
        else:
            itype = 'other'
        records.append({
            'way_id':     way.id,
            'infra_type': itype,
            'name':       tags.get('name', ''),
            'geometry':   LineString(coords),
        })
    if not records:
        return None
    return gpd.GeoDataFrame(records, geometry='geometry', crs='EPSG:4326')


def _find_crossings(traj_gdf: gpd.GeoDataFrame, infra_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame of points where trajectories cross infrastructure.

    Uses an STRtree spatial index to find candidates, then vectorised
    shapely.intersection for batch GEOS calls — avoids an O(n×m) Python loop.
    """
    tree = STRtree(infra_gdf.geometry.values)
    records = []

    for _, traj in traj_gdf.iterrows():
        idxs = tree.query(traj.geometry, predicate='intersects')
        if len(idxs) == 0:
            continue
        matched = infra_gdf.iloc[idxs]
        geoms = shapely_intersection(traj.geometry, matched.geometry.values)
        for geom, (_, feat) in zip(geoms, matched.iterrows()):
            if geom.is_empty:
                continue
            records.append({
                'traj_id':    traj['traj_id'],
                'infra_type': feat['infra_type'],
                'name':       feat['name'],
                'geometry':   geom if geom.geom_type == 'Point' else geom.centroid,
            })
        logging.info(f"  {traj['traj_id']}: {len(idxs)} candidates → {sum(1 for g in geoms if not g.is_empty)} crossings")

    return gpd.GeoDataFrame(records, geometry='geometry', crs='EPSG:4326') if records else \
           gpd.GeoDataFrame(columns=['traj_id', 'infra_type', 'name', 'geometry'])


def _build_map(center, traj_gdf, infra_gdf, stop_points, crossings_gdf) -> folium.Map:
    """Build and return an interactive Folium map."""
    m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

    for itype, color in INFRA_COLORS.items():
        subset = infra_gdf[infra_gdf['infra_type'] == itype]
        if subset.empty:
            continue
        layer = folium.FeatureGroup(name=f"Infrastructure: {itype}", show=True)
        for _, row in subset.iterrows():
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda _, c=color: {'color': c, 'weight': 2, 'opacity': 0.6},
                tooltip=row['name'] or itype,
            ).add_to(layer)
        layer.add_to(m)

    traj_layer = folium.FeatureGroup(name="Trajectories", show=True)
    for _, row in traj_gdf.iterrows():
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda _: {'color': '#222222', 'weight': 2.5, 'opacity': 0.8},
            tooltip=str(row['traj_id']),
        ).add_to(traj_layer)
    traj_layer.add_to(m)

    stops_layer = folium.FeatureGroup(name="Stop Points", show=True)
    for _, row in stop_points.iterrows():
        dur = row.get('duration_s', 0)
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=max(4, int(dur / 60)),
            color='#cc0000', fill=True, fill_color='#cc0000', fill_opacity=0.55,
            popup=folium.Popup(f"<b>Stop</b><br>{dur:.0f}s ({dur/60:.1f} min)", max_width=200),
            tooltip=f"Stop {dur:.0f}s",
        ).add_to(stops_layer)
    stops_layer.add_to(m)

    crossings_layer = folium.FeatureGroup(name="Crossings", show=True)
    for _, row in crossings_gdf.iterrows():
        color = INFRA_COLORS.get(row['infra_type'], '#888888')
        label = row['name'] or row['infra_type']
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=7,
            color=color, fill=True, fill_color=color, fill_opacity=0.9,
            popup=folium.Popup(
                f"<b>{row['infra_type']}</b><br>{label}<br>Trajectory: {row['traj_id']}",
                max_width=220,
            ),
            tooltip=f"{row['infra_type']}: {label}",
        ).add_to(crossings_layer)
    crossings_layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


class _StopDetector:
    """Picklable callable for use with parallelize()."""

    def __init__(self, min_duration, max_diameter):
        self.min_duration = min_duration
        self.max_diameter = max_diameter

    def __call__(self, gdf):
        traj = mpd.Trajectory(gdf, traj_id=0)
        return mpd.TrajectoryStopDetector(traj).get_stop_points(
            min_duration=timedelta(seconds=self.min_duration),
            max_diameter=self.max_diameter,
        )


class App(object):

    def __init__(self, moveapps_io):
        self.moveapps_io = moveapps_io

    @hook_impl
    def execute(self, data: TrajectoryCollection, config: dict) -> TrajectoryCollection:
        # Load config
        min_duration  = config.get('min_duration', 180)
        max_diameter  = config.get('max_diameter', 100)
        buffer        = config.get('buffer', 0.005)
        road_network  = config.get('road_network', 'major')
        custom_filter = config.get('custom_filter') or ROAD_FILTERS.get(road_network, ROAD_FILTERS['major'])
        logging.info(f"Config: min_duration={min_duration}s, max_diameter={max_diameter}m, "
                     f"buffer={buffer}, custom_filter={custom_filter}")

        # Stop detection
        logging.info("Running Stop Detector")
        n = len(data.trajectories)
        point_counts = [len(t.df) for t in data.trajectories]
        total_points = sum(point_counts)
        logging.info(f"Trajectories: {n}  |  Points: {total_points:,}  |  "
                     f"min={min(point_counts):,}  max={max(point_counts):,}  mean={total_points//n:,}")
        t0 = time.time()
        stop_points = parallelize(data, _StopDetector(min_duration, max_diameter))
        logging.info(f"Stop detection: {len(stop_points)} stops in {time.time()-t0:.1f}s")

        # Build trajectory LineStrings
        traj_gdf = gpd.GeoDataFrame(
            {'traj_id': [t.id for t in data.trajectories]},
            geometry=[LineString(t.df.geometry.values) for t in data.trajectories],
            crs='EPSG:4326',
        )

        # Guard: reject oversized query areas
        minx, miny, maxx, maxy = traj_gdf.geometry.total_bounds
        bbox_area = (maxy - miny) * (maxx - minx)
        if bbox_area > MAX_BBOX_DEG2:
            logging.error(
                f"Trajectory bbox too large ({bbox_area:.1f} deg²  ≈  "
                f"{(maxy-miny)*111:.0f} km × {(maxx-minx)*111:.0f} km). "
                "Overpass cannot serve this area. Use a smaller study region."
            )
            return data

        # Query infrastructure
        logging.info("Running Infrastructure Query Routine")
        bbox = f"{miny-buffer},{minx-buffer},{maxy+buffer},{maxx+buffer}"
        logging.info(f"Query bbox: {bbox}")
        query = (
            f"[out:json][timeout:60];\n(\n"
            f"  way{custom_filter}({bbox});\n"
            f"  way[\"railway\"]({bbox});\n"
            f"  way[\"power\"~\"line|minor_line|cable\"]({bbox});\n"
            f"  way[\"barrier\"]({bbox});\n"
            f"  way[\"waterway\"]({bbox});\n"
            f");\n(._;>;);\nout body;"
        )
        result = _overpass_query(query)
        if result is None:
            logging.error(f"All Overpass endpoints failed for bbox {bbox}.")
            return data

        infra_gdf = _ways_to_gdf(result)
        if infra_gdf is None:
            logging.error("No infrastructure features found in the trajectory area.")
            return data
        logging.info(f"Infrastructure: {len(infra_gdf)} features — "
                     f"{infra_gdf['infra_type'].value_counts().to_dict()}")

        # Intersection analysis
        logging.info("Finding trajectory-infrastructure intersections")
        crossings_gdf = _find_crossings(traj_gdf, infra_gdf)
        logging.info(f"Crossings: {len(crossings_gdf)}")
        if not crossings_gdf.empty:
            for itype, grp in crossings_gdf.groupby('infra_type'):
                logging.info(f"  {itype}: {len(grp)}")

        # Build and save interactive map
        logging.info("Building interactive map")
        center = ((miny + maxy) / 2, (minx + maxx) / 2)
        m = _build_map(center, traj_gdf, infra_gdf, stop_points, crossings_gdf)
        out_path = self.moveapps_io.create_artifacts_file("infrastructure_crossings.html")
        m.save(out_path)
        logging.info(f"Map saved → {out_path}")

        return data
