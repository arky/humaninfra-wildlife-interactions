from sdk.moveapps_spec import hook_impl
from movingpandas import TrajectoryCollection
import movingpandas as mpd
import logging

import pandas as pd
import numpy as np
import geopandas as gpd
import shapely as shp
import matplotlib.pyplot as plt

import networkx as nx
import osmnx as ox
from osmnx import utils_graph

from geopandas import GeoDataFrame, read_file
from shapely.geometry import Point, LineString, Polygon
from datetime import datetime, timedelta

# Enable OSMNX cache and logs  
ox.settings.use_cache=True
#ox.settings.log_console=True


class App(object):

    def __init__(self, moveapps_io):
        self.moveapps_io = moveapps_io
    

    @hook_impl
    def execute(self, data: TrajectoryCollection, config: dict) -> TrajectoryCollection:
        """
        This following code is based on MovingPandas Stop Detection examples and tech demos. 

        https://github.com/movingpandas/movingpandas-examples/blob/main/1-tutorials/8-detecting-stops.ipynb

        https://github.com/movingpandas/movingpandas-examples/blob/main/3-tech-demos/stop-hotspots.ipynb
        
        """
 
        # Stop Detector Routine
        logging.info("Running Stop Detector" )
        detector = mpd.TrajectoryStopDetector(data)
        stop_points = detector.get_stop_points(min_duration=timedelta(seconds=120), max_diameter=100)
        logging.info(f"Detected {len(stop_points)} Stop Points." )
       
        
        # Network Data Routine
        logging.info("Running Network Data Routine" )
        minx, miny, maxx, maxy = stop_points.geometry.total_bounds
        buffer = 0.005
        cf = '["highway"~"motorway|trunk|primary|secondary|tertiary"]'
        G = ox.graph_from_bbox(maxy+buffer, miny-buffer, minx-buffer, maxx+buffer, network_type='drive', custom_filter=cf)
        logging.info(f"OSM Graph Length: {len(G)}.")
        
        # Simplify Network Data Routine
        logging.info("Running Consolidate Intersections" )
        G_proj = ox.project_graph(G)  
        G2 = ox.consolidate_intersections(G_proj, rebuild_graph=True, tolerance=15, dead_ends=False)
        G2 = ox.project_graph(G2, to_crs='EPSG:4326')
        logging.info(f"Consolidated OSM Graph Length: {len(G2)}.")


        # Visualization Routine 
        graph_gdf = gpd.GeoDataFrame(utils_graph.graph_to_gdfs(G2, nodes=False)["geometry"])
        ax = graph_gdf.plot(figsize=(9,9), color='grey', zorder=0)
        res = stop_points.plot(ax=ax, color='red', zorder=3, alpha=0.2)
        fig = res.get_figure()
        logging.info("Saving plot to image.")
        fig.savefig('StopPoints-OSM.png')
       

        return data
