import pandas as pd
from geopandas.geodataframe import GeoDataFrame
from movingpandas import TrajectoryCollection
import logging
import time
import geopy.distance
import multiprocessing as mp



def get_cpu_limit() -> int:
    """
    From https://donghao.org/2022/01/20/how-to-get-the-number-of-cpu-cores-inside-a-container/
    :return: number of CPUs that is available in the docker container
    """
    with open("/sys/fs/cgroup/cpu/cpu.cfs_quota_us") as fp:
        cfs_quota_us = int(fp.read())
    with open("/sys/fs/cgroup/cpu/cpu.cfs_period_us") as fp:
        cfs_period_us = int(fp.read())
    container_cpus = cfs_quota_us // cfs_period_us
    # For physical machine, the `cfs_quota_us` could be '-1'
    cpus = mp.cpu_count() if container_cpus < 1 else container_cpus
    return cpus


def calculate_distance(data: GeoDataFrame) -> GeoDataFrame:
    """
    Calculates the distance between each location and the previous location
    :param data: a GeoDataFrame
    :return: input data with distances in km
    """
    mp.log_to_stderr(logging.INFO)

    data.set_crs('epsg:4326')
    data["x"] = data.get_coordinates(include_z=False)["x"]
    data["y"] = data.get_coordinates(include_z=False)["y"]

    logging.info("Calculating distances")

    # calculate the distance between the locations for each row in the data
    distances = [None] * (len(data) - 1)
    for row in range(len(data) - 1):
        distances[row] = geopy.distance.distance((data["y"].iloc()[row], data["x"].iloc()[row]),
                                                 (data["y"].iloc()[row + 1], data["x"].iloc()[row + 1])).km

    data["distance_from_previous_geopy"] = [None] + distances

    # now wait for 10 seconds
    logging.info("Sleeping for 10 seconds")
    time.sleep(10)

    # return the data with distances
    return data


def parallelize(data: TrajectoryCollection, func) -> GeoDataFrame:
    """
    :param data:
    :param func: The function that needs to be executed in parallel
    :return:
    """

    logging.info("Function parallelize has been started")

    # transfer the data to a GeoDataFrame
    data_gdf = data.to_point_gdf()

    # Derive track IDs directly from the TrajectoryCollection — avoids any
    # column-name mismatch between get_traj_id_col() and to_point_gdf() output.
    track_id_col_name = data.get_traj_id_col()
    track_ids = [traj.id for traj in data.trajectories]
    logging.info(f'Track IDs discovered: {track_ids}')

    # Ensure the flat GDF has the column we need for splitting
    if track_id_col_name not in data_gdf.columns:
        id_map = {i: traj.id for i, traj in enumerate(data.trajectories)}
        for col in data_gdf.columns:
            if set(data_gdf[col].unique()) == set(track_ids):
                track_id_col_name = col
                logging.info(f"Resolved track ID column to '{col}'")
                break
        else:
            raise KeyError(
                f"Cannot find track ID column '{track_id_col_name}' in {list(data_gdf.columns)}"
            )

    # find the number of CPUs that is available
    n_cpu = mp.cpu_count()
    logging.info(f'mp.cpu_count() found {n_cpu} CPUs')

    logging.info(f'Number of cores currently available for parallel processing: {n_cpu}')

    # determine the maximum number of cores available or needed
    if len(track_ids) > n_cpu:
        n_cpu = n_cpu
    else:
        n_cpu = len(track_ids)

    logging.info(f'Number of cores that will be used for parallel processing: {n_cpu}')

    # split the data by trackID
    data_split = [data_gdf[data_gdf[track_id_col_name] == tr_id] for tr_id in track_ids]

    # multiprocessing
    pool = mp.Pool(n_cpu)
    data_return = pd.concat(pool.map(func, data_split), ignore_index=False)
    pool.close()
    pool.join()

    # return the resulting data
    return data_return
