from urllib import response

import uuid

from datetime import datetime, timezone

from rich import print

from geopy.distance import geodesic

import requests

# List of all the locations, this is currently hardcoded.
from app.services.locations import ALL_FOOD_LOCATIONS


# Makes API call and parses data to get the hours of the locations. Currently done at the start of the program.

today = datetime.now().strftime("%Y-%m-%d")
url = f"https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/hours?date={today}"

parsed_locations = {}
for places in requests.get(url).json()["locations"]:
    parsed_hours = []
    for hours in places["hours"]:

        start_time, end_time = hours.split(" - ")
        start_time = start_time.replace("a", "AM").replace("p", "PM")
        end_time = end_time.replace("a", "AM").replace("p", "PM")
        start_time = datetime.strptime(start_time, "%I:%M%p").time()
        end_time = datetime.strptime(end_time, "%I:%M%p").time()
        parsed_hours.append((start_time, end_time))

    parsed_locations[places["location"].lower()] = parsed_hours

DATA = {"date": today, "data": parsed_locations}

class recommendation:

    TAMU_BOUNDS = {
    'north': 30.643,  # ~1 mile north
    'south': 30.595,  # ~1 mile south
    'east': -96.315,  # ~1 mile east
    'west': -96.380   # ~1 mile west
    }
    

    def __init__(self, current_location: tuple, user_id: str, restriction: str = None):
        self.current_location = current_location
        self.restriction = restriction # Currently this method, but in future this will be populated using user id

        #self.restriction, self.time = self._get_details(user_id)
    

    def _get_details(self, user_id: str) -> tuple[list, float]:

        """
        TODO: Needs implementation. Currently everything is hardcoded. Not used anywhere currently

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
    
    def _find_is_open(self, locs: list) -> list:

        """
        Uses the data gathered from API. This is not efficient, but it is a proof of concept. In the future, we can use a more efficient data structure to store the hours of the locations, but for now this is sufficient.
        Input: list of locations
        Output: list of locations that are open
        """

        open_locs = []
        current_time = datetime.now().time()
        api_data = DATA["data"]
        
        for loc in locs:
            name = loc["name"].lower()
            if name in api_data:
                for start_time, end_time in api_data[name]:
                    if start_time <= current_time <= end_time:
                        open_locs.append(loc)
                        break 

        return open_locs

    def recommend(self, center_of_interest: tuple, radius: float) -> list:

        """
        Recommends the places that the user can eat. Current methodology: Finds places within specified search circle, filters the locations by user restriction, then sorts by distance from user.
        Limitations: If no places within search circle fit the user's needs, it returns nothing.
        Input: center_of_interest as a tuple (lat, long), radius as a float in meters
        Output: Recommended places to eat as a list of dictionaries. Dictionary structure: {'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': distance from user}
        """

        recom_locs = []

        if not self._is_on_campus():
            raise ValueError("Location is out of bounds")

        for location in ALL_FOOD_LOCATIONS:

            name, coord, cuisine, restriction = location["name"], (location["latitude"], location["longitude"]), location["cuisine"], location["restriction"]

            if self._within_radius(center_of_interest, coord, radius):

                recom_locs.append({'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': self._calc_distance(self.current_location, coord)})

        recom_locs = self._find_is_open(recom_locs)

        recom_locs = self._filter_by_restriction(recom_locs)

        recom_locs.sort(key=lambda x: x['distance'])

        return recom_locs


    

    

if __name__ == "__main__":
    new_rec = recommendation((30.6123, -96.3414), "user1")
    print(new_rec.recommend((30.6123, -96.3414), 400.0))