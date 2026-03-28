from datetime import datetime as dt
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, Playwright
from rich import print
from playwright_stealth import Stealth
from bs4 import BeautifulSoup

class scraper():

    def __init__(self, names_with_urls : dict, timezone : str = 'America/Chicago', date : str = None):
        

        # Obtains date and weekday
        if date == None:
            self.date = self._get_current_date(timezone).strftime("%Y-%m-%d")
            self.weekday = self._get_current_date(timezone).weekday()
        
        else:
            try:
                self.date = date
                self.weekday = dt.strptime(date, "%Y-%m-%d").strftime("%w")
            except:
                raise ValueError("Check the date format. It needs to be in YYYY-MM-DD.")


        # Initializes menu dictionary

        self.menu = {}
        for name in names_with_urls.keys():
            self.menu[name] = {}


        # Saves the URLS

        self.urls = names_with_urls

    def _handler(self, page: str):
        soup = BeautifulSoup(page, "html.parser")
        station_menu = {}
        
        #############################################
        #            STATION NAME FINDER           #
        ############################################
        toggle = soup.find(attrs={"aria-label": lambda x: x and x.startswith("Toggle")})
        if not toggle:
            return
        station_name = toggle["aria-label"].replace("Toggle ", "").replace(" category", "")
        ###########################################
        #             MENU FINDER                 #
        ###########################################
        food_items = []

        for food in soup.find_all('td'):
            item = food.find(attrs={"aria-label": lambda x: x and x.startswith("View nutritional information")})
            if item:
                food_items.append(item.text)

        station_menu[station_name] = food_items

        return station_menu
    
    def _get_current_date (self,timezone) :
        return dt.now(ZoneInfo(timezone))
    
    def scrape (self, time_of_food : str):

        date = self.date
        menu = self.menu
        urls = self.urls

        with sync_playwright() as playwright:
            chrome = playwright.chromium
            browser = chrome.launch(headless=False)
            page = browser.new_page()
            Stealth().apply_stealth_sync(page)
            
            for name, url in urls.items():
                print(f"Visiting:{url}{date}/{time_of_food}")
                try: 
                    page.goto(f"{url}{date}/{time_of_food}", timeout=30000)
                    page.wait_for_selector('tbody') 
                    for item in page.locator(f'div.p-4').all():
                        station_menu = self._handler(item.inner_html())
                        if station_menu:
                            menu[name].update(station_menu)
                except Exception as e:
                    print(e)
                    continue

            browser.close()
            return 0


if __name__ == "__main__":

    times = ["brunch", "dinner"]
    
    urls = {"Commons": "https://dineoncampus.com/tamu/whats-on-the-menu/the-commons-dining-hall-south-campus/", "Sbisa" : "https://dineoncampus.com/tamu/whats-on-the-menu/sbisa-dining-hall-north-campus/", "Duncan" : "https://dineoncampus.com/tamu/whats-on-the-menu/duncan-dining-hall-south-campus-quad/"}
    my_scraper = scraper(urls)

    for time in times:
        print(my_scraper.scrape(time))
        with open("menu.txt", "a") as f:
            f.write(f"{time}:\n\n{my_scraper.menu}\n\n")