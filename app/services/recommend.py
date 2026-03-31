import uuid

from datetime import datetime, timezone

from math import sqrt

from rich import print

from geopy.distance import geodesic


class recommendation:

    TAMU_BOUNDS = {
    'north': 30.643,  # ~1 mile north
    'south': 30.595,  # ~1 mile south
    'east': -96.315,  # ~1 mile east
    'west': -96.380   # ~1 mile west
    }
    

    def __init__(self, current_location: tuple, center_of_interst: tuple, radius: float, user_id: str):
        self.current_location = current_location
        self.center = center_of_interst
        self.radius = radius
        self.restriction, self.time = self._get_details(user_id)
        self.all_food_loc = self._get_food_locs()


    def _get_food_locs(self) -> list:
        food_locations = []
        with open("locations.txt", "r") as f:
            for location in f:
                loc = location.strip().split(", ")
                food_locations.append({loc[0]:[(float(loc[1]),float(loc[2])), loc[3], loc[4]]})
        
        return food_locations
    

    def _get_details(self, user_id) -> tuple[list, float]:

        restriction = "vegetarian"
        time = None
        #####################################################################################################
        #########            TODO: Add logic to get the restrictions of the user and                #########            
        #########                   the time they have to get food                                  #########
        #####################################################################################################

        return(restriction,time)    


    def _calc_distance(self, point_1: tuple, point_2: tuple) -> float:
        return geodesic(point_1, point_2).m
    

    def _within_radius(self, point_1: tuple, point_2: tuple) -> bool:
        return self._calc_distance(point_1, point_2) <= self.radius
    

    def _is_on_campus(self) -> bool:
        lat, long = self.current_location
        return self.TAMU_BOUNDS['south'] <= lat <= self.TAMU_BOUNDS['north'] and self.TAMU_BOUNDS['west'] <= long <= self.TAMU_BOUNDS['east']
    

    def _filter_by_restriction(self, locations: list) -> list:
        
        new_locs = []

        if self.restriction == "vegetarian":
            for location in locations:
                if location["restriction"].startswith("vegetarian") or location["restriction"].startswith("vegan"):
                    new_locs.append(location)
        
        elif self.restriction == "vegan":
            for location in locations:
                if location["restriction"].startswith("vegan"):
                    new_locs.append(location)

        else:
            new_locs = locations

        
        return new_locs
    

    def recommend(self) -> list:
        recom_locs = []

        if not self._is_on_campus():
            raise ValueError("Location is out of bounds")

        for location in self.all_food_loc:
            name, (coord, cuisine, restriction) = next(iter(location.items()))
            if self._within_radius(self.center, coord):
                recom_locs.append({'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': self._calc_distance(self.current_location, coord)})

        #     TODO: Finish
        #
        #        1: Get the recommended locations from S3

        recom_locs = self._filter_by_restriction(recom_locs)

        print(recom_locs)

        recom_locs.sort(key=lambda x: x['distance'])

        return recom_locs


    

    

if __name__ == "__main__":
    new_rec = recommendation((30.6123, -96.3414),(30.6123, -96.3414), 400.0, "user1")
    print(new_rec.recommend())