import uuid

from datetime import datetime, timezone

from rich import print

from geopy.distance import geodesic


class recommendation:

    TAMU_BOUNDS = {
    'north': 30.643,  # ~1 mile north
    'south': 30.595,  # ~1 mile south
    'east': -96.315,  # ~1 mile east
    'west': -96.380   # ~1 mile west
    }
    

    def __init__(self, current_location: tuple, center_of_interest: tuple, radius: float, user_id: str):
        self.current_location = current_location
        self.center = center_of_interest
        self.radius = radius
        self.restriction, self.time = self._get_details(user_id)
        self.all_food_loc = self._get_food_locs()


    def _get_food_locs(self) -> list:

        """
        Currently reads locations from locations.txt to load all locations into data with addition info
        Input: none
        Output: List of Dictionaries in this format {name: [(lat, long), type of food, restriction]}
        """

        food_locations = []
        with open("locations.txt", "r") as f:
            for location in f:
                loc = location.strip().split(", ")
                food_locations.append({loc[0]:[(float(loc[1]),float(loc[2])), loc[3], loc[4]]})
        
        return food_locations
    

    def _get_details(self, user_id: str) -> tuple[list, float]:

        """
        TODO: Needs implementation. Currently everything is hardcoded

        Obtains the details of an user through some form of id.
        Input: User ID
        Output: a tuple with the user's restrictions, and the time bewteen classes (restriction, time)
        """

        restriction = "vegetarian"
        time = None
        #####################################################################################################
        #########            TODO: Add logic to get the restrictions of the user and                #########            
        #########                   the time they have to get food                                  #########
        #####################################################################################################

        return(restriction,time)    


    def _calc_distance(self, point_1: tuple, point_2: tuple) -> float:

        """
        Finds the distance between 2 points
        Input: tuple of point 1 and tuple of point 2
        Output: meters as float
        """

        return geodesic(point_1, point_2).m
    

    def _within_radius(self, point_1: tuple, point_2: tuple, radius: float) -> bool:

        """
        Finds if 2 points are between a specified radius
        Input: tuple of point 1, tuple of point 2, and a radius as a float
        """

        return self._calc_distance(point_1, point_2) <= radius
    

    def _is_on_campus(self) -> bool:

        """
        Finds if the location of the user is within 1 mile of the campus bounds as specified in TAMU_BOUNDS
        Input: none
        Output: Boolean
        """

        lat, long = self.current_location
        return self.TAMU_BOUNDS['south'] <= lat <= self.TAMU_BOUNDS['north'] and self.TAMU_BOUNDS['west'] <= long <= self.TAMU_BOUNDS['east']
    

    def _filter_by_restriction(self, locations: list) -> list:

        """
        Filters down the location recommendations to only those that fit the user
        Input: list of locations
        Output: List of locations that fits the users needs
        """
        
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

        """
        Recommends the places that the user can eat. Current methodology: Finds places within specified search circle, filters the locations by user restriction, then sorts by distance fom user
        Limitations: If no places within search circle fit the user's needs, it returns nothing
        Input: none
        Output: Recommended places to eat as a list of dictionaries. Dictionary structure: {'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': distance from user}
        """

        recom_locs = []

        if not self._is_on_campus():
            raise ValueError("Location is out of bounds")

        for location in self.all_food_loc:
            name, (coord, cuisine, restriction) = next(iter(location.items()))
            if self._within_radius(self.center, coord, self.radius):
                recom_locs.append({'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': self._calc_distance(self.current_location, coord)})

        #     TODO: Finish
        #
        #        1: Get the recommended locations from S3

        recom_locs = self._filter_by_restriction(recom_locs)

        recom_locs.sort(key=lambda x: x['distance'])

        return recom_locs


    

    

if __name__ == "__main__":
    new_rec = recommendation((30.6123, -96.3414),(30.6123, -96.3414), 400.0, "user1")
    print(new_rec.recommend())