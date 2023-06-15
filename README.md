# Human Infrastructure and Wildlife Interactions Detection

Github repository: *github.com/arky/humaninfra-wildlife-interactions* 
## Description

This early stage MoveApp written in python visualizes wildlife interactions with human infrastructure using Open Street Map (OSM) data.  

Current implementation extracts Road networks (highway,motorway, trunk, primary, secondary and tertiary roads) and plots any stops detected from animal trajectories.

Biologists and conservation projects could easily get an idea of wildlife interactions with man made infrastructure such as roadways at a glance.

## Documentation

The code is based on [MovingPandas](https://movingpandas.readthedocs.io/en/main/) [stop detector](https://movingpandas.readthedocs.io/en/main/trajectorystopdetector.html)

The OpenStreetMap geo spatial data is retrieved using [OSMnx](https://osmnx.readthedocs.io/en/stable/) python package.

* Limitations * : The tool is envisioned to be an interactive dashboard built with MoveApps Python GUI. The current version generates only static plot. 

At the moment, (MovingPandas)[https://movingpandas.readthedocs.io/en/main/trajectory.html#movingpandas.Trajectory.intersection] seems to only support shapely objects only. In future, we need to find a suitable ways to find intersections of OSMNx graphs.

### Input data

 MovingPandas TrajectoryCollection in Movebank format. Requires that you [link-r-python](https://github.com/movestore/link-r-python) MoveApp to convert R data into MovingPandas TrajectoryCollection.

### Output data

App does not pass on any data to other apps.

### Artefacts

`StopPoints-OSM.png`: PNG image file with road networks and stop points visualized.

### Settings 

In future, you can fine tune stop detector by passing following parameters.

`min_duration (int)`: Defines the minimum time period of the stop in seconds. The default is 120 seconds.


`max_diameter (int)`: Defines the diameter of the area that animal has to stay in minimum duration of time for it to be considered a stop point. The default is 100 meters. 


`buffer (float)`: Add padding around (bounding box)[https://osmnx.readthedocs.io/en/stable/osmnx.html#osmnx.graph.graph_from_bbox]. The default is `0.005`.

`custom_filter (str)`: A custom ways filter to passed to (OSMNx graph)[https://osmnx.readthedocs.io/en/stable/osmnx.html#osmnx.graph.graph_from_bbox]. The default is `["highway"~"motorway|trunk|primary|secondary|tertiary"]`.