import uuid

from datetime import datetime, timezone

from math import sqrt

import geopy

from rich import print


class recommendation:
    def __init__(self, current_location: tuple, center_of_interst: tuple, radius: float, restrictions: list, time_available: float):
        self.current_location = current_location
        self.center = center_of_interst
        self.radius = radius
        self.restrictions = restrictions
        self.time = time_available
        self.all_food_loc = self._get_food_locs()

    def _get_food_locs(self):
        food_locations = []
        with open("locations.txt", "r") as f:
            for location in f:
                loc = location.strip().split(",")
                food_locations.append({loc[0]:(float(loc[1]),float(loc[2]))})
        
        return food_locations

    def _calc_distance(self, point_1: tuple, point_2: tuple):
        return sqrt((point_2[0]-point_1[0])**2+(point_2[1]-point_1[1])**2)
    
    def _within_radius(self, point_1: tuple, point_2: tuple):
        return self._calc_distance(point_1, point_2) <= self.radius

    def recommend(self):
        recom_locs = []
        
        for location in self.all_food_loc:
            loc, coord =  next(iter(location.items()))
            if self._within_radius(self.center, coord):
                recom_locs.append(loc)

        return recom_locs        




    

    
    
if __name__ == "__main__":
    new_rec = recommendation((1,1), (1,1), 2.0, ["none"], 9999)
    print(new_rec.recommend())