from urllib import response

import uuid

from datetime import datetime, timezone

from rich import print

from geopy.distance import geodesic

import requests

from shapely.geometry import Point, LineString

# List of all the locations, this is currently hardcoded.
from app.services.locations import ALL_FOOD_LOCATIONS


EVERYTHING_OPEN = False #Incase the hours cannot be fetched

# Makes API call and parses data to get the hours of the locations. Currently done at the start of the program.

today = datetime.now().strftime("%Y-%m-%d")
url = f"https://nh19d71sp8.execute-api.us-east-2.amazonaws.com/hours?date={today}"

try:   
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

except:
    EVERYTHING_OPEN = True

DATA = {"date": today, "data": parsed_locations}

class recommendation:

    TAMU_BOUNDS = {
    'north': 30.643,  # ~1 mile north
    'south': 30.595,  # ~1 mile south
    'east': -96.315,  # ~1 mile east
    'west': -96.380   # ~1 mile west
    }
    

    def __init__(self, current_location: tuple, user_id: str, restriction: str = None, time: str = None):
        self.current_location = current_location
        self.restriction = restriction # Currently this method, but in future this will be populated using user id
        if time == None or time == "":
            self.time = datetime.now().time()
        else:
            self.time = datetime.strptime(time, "%I:%M%p").time()

        #self.restriction = self._get_details(user_id)
    

    def _get_details(self, user_id: str) -> list:

        """
        TODO: Needs implementation. Currently everything is hardcoded. Not used anywhere currently

        Obtains the details of an user through some form of id.
        Input: User ID
        Output: a tuple with the user's restrictions, and the time bewteen classes (restriction, time)
        """

        restriction = "vegetarian"
        
        #####################################################################################################
        #########            TODO: Add logic to get the restrictions of the user and                #########            
        #########                   the time they have to get food                                  #########
        #####################################################################################################

        return restriction   


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
    

    def _is_on_campus(self, location_of_interest: tuple) -> bool:

        """
        Finds if the location of the user is within 1 mile of the campus bounds as specified in TAMU_BOUNDS
        Input: none
        Output: Boolean
        """

        lat, long = location_of_interest
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

        elif self.restriction == "chicken":
            for location in locations:
                if location["restriction"].endswith("chicken"):
                    new_locs.append(location)

        elif self.restriction == "beef":
            for location in locations:
                if location["restriction"].endswith("beef"):
                    new_locs.append(location)
        
        elif self.restriction == "meat":
            for location in locations:
                if location["restriction"].startswith("meat"):
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
        if EVERYTHING_OPEN == True:
            return locs
        
        open_locs = []
        current_time = self.time
        api_data = DATA["data"]
        
        for loc in locs:
            name = loc["name"].lower()
            if name in api_data:
                for start_time, end_time in api_data[name]:
                    if start_time <= current_time <= end_time:
                        open_locs.append(loc)
                        break 

        return open_locs
    
    def _point_to_segment_distance(self, point: tuple, seg_start: tuple, seg_end: tuple) -> float:
       
        """
        Finds the perpendicular distance from a point to a line segment using Shapely.
        Automatically clamps projection to segment bounds, so points that fall before
        or beyond the segment endpoints are measured to the nearest endpoint instead.
        Input: tuple of the point, tuple of the segment start, tuple of the segment end
        Output: meters as float
        """

        shapely_point = Point(point[1], point[0])
        shapely_seg   = LineString([(seg_start[1], seg_start[0]),
                                    (seg_end[1],   seg_end[0])])
        deg_dist = shapely_point.distance(shapely_seg)
        return geodesic(point, (point[0] + deg_dist, point[1])).m

    def _score_location(self, loc_coord: tuple, center_of_interest: tuple, radius: float, corridor_weight: float = 0.6, distance_weight: float = 0.4) -> float:

        """
        Scores a location based on how well it lies along the path from the user to the
        center of interest. Combines perpendicular distance from the user->destination
        corridor and raw distance from the user. Lower score = higher priority.
        Input: location coordinate as tuple, center of interest as tuple, search radius as float, optional corridor and distance weights as floats (default 0.6 / 0.4)
        Output: score as float
        """
         
        perp_dist = self._point_to_segment_distance(loc_coord, self.current_location, center_of_interest)
        raw_dist  = self._calc_distance(self.current_location, loc_coord)
        norm_perp = min(perp_dist / radius, 1.0)
        norm_dist = min(raw_dist  / radius, 1.0)
        return corridor_weight * (norm_perp ** 2) + distance_weight * norm_dist

    def recommend(self, center_of_interest: tuple, radius: float) -> list:

        """
        Recommends the places that the user can eat. Current methodology: Finds places within
        specified search circle, filters by open hours and user restriction, then sorts by
        corridor score which prioritizes locations along the path from the user to the center
        of interest.
        Limitations: If no places within search circle fit the user's needs, it returns nothing.
        Input: center_of_interest as a tuple (lat, long), radius as a float in meters
        Output: Recommended places to eat as a list of dictionaries. Dictionary structure:
                {'name': name, 'cuisine': cuisine, 'restriction': restriction, 'distance': distance from user, 'score': corridor score}
        """

        recom_locs = []

        if not self._is_on_campus(center_of_interest):
            return recom_locs

        for location in ALL_FOOD_LOCATIONS:
            name = location["name"]
            coord = (location["latitude"], location["longitude"])
            cuisine = location["cuisine"]
            restriction = location["restriction"]

            if self._within_radius(center_of_interest, coord, radius):
                score = self._score_location(coord, center_of_interest, radius)
                recom_locs.append({
                    'name': name,
                    'cuisine': cuisine,
                    'restriction': restriction,
                    'distance': self._calc_distance(self.current_location, coord),
                    'score': score
                })

        recom_locs = self._find_is_open(recom_locs)
        recom_locs = self._filter_by_restriction(recom_locs)
        recom_locs.sort(key=lambda x: x['score'])

        return recom_locs


    

    

if __name__ == "__main__":
    new_rec = recommendation((30.6123, -96.3414), "user1")
    print(new_rec.recommend((30.6123, -96.3414), 400.0))