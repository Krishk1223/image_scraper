from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.exceptions import ElementClickInterceptedException, NoSuchElementException, TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
import io
from PIL import Image
import time
import os
import logging
from datetime import datetime

#CONFIGURATION: 
DEBUG_MODE = True
HEADLESS = False
SELECTOR_VERSION = "2025-10-16"
DELAY = 1

# SELECTORS FOR IMAGE SCRAPING:

THUMBNAIL_SELECTORS = [
    "img.rg_i", #default
    "img.Q4LuWd", #alternative
    "img.YQ4gaf", #older alternative
]

FULL_IMAGE_SELECTORS = [
    "img.sFLh5c", #default + seems to work for most images
    "img.n3VNCb", #seems to work for cats
]

ACCEPT_COOKIES_SELECTORS = [
    "button#L2AGLb", #default accept cookies button
    "button[aria-label*='Accept']", #aria label Accept
    "button[aria-label*='accept']", #lowecase handling
    "//button[contains(text(), 'Accept')]",  # XPath
    "//button[contains(text(), 'I agree')]", # XPath alternative
]

REJECT_COOKIES_SELECTORS = [
    "button#W0wltc", #reject all cookies button
    "button[aria-label*='Reject']", #aria label reject
    "//button[contains(text(), 'Reject')]", #XPath
]


# LOG SETUP:
logging.basicConfig( #logger setup in info mode with details about time, lvl and message
    level=logging.INFO, 
    filename="image_scraper.log", #log file name,
    format= "%(asctime)s - %(levelname)s - %(message)s",
    handlers= [#log config
        logging.FileHandler("image_scraper.log"), #logs to file
        logging.StreamHandler()#logs to console
    ]
)
log = logging.getLogger(__name__) #logger instance


def main():
    """
    MAIN FUNCTION:
    """

    #Path setup:
    download_path : str = "./images/" #path to images folder
    original_path = os.path.join(download_path, "accepted") #path to accepted images folder
    rejected_path = os.path.join(download_path, "rejected") #path to rejected images

    #path creation if not exists:
    for path in [original_path, rejected_path]:
        if not os.path.exists(path): 
            os.makedirs(path) 

    #get user input for query:
    query:str = input("What images would you like to search for? (Please be detailed): ") #user query
    max_images:int= int(input("How many images would you like to download?: ")) #max images wanted

    #starting logs
    log.info(f"Starting image scraper for query: {query} with {max_images} images")
    log.info(f"Selector version: {SELECTOR_VERSION}, if it doesn't work please check for updates")

    driver_options = Options()
    
    #Headless setup:
    if HEADLESS:
        chrome_options.add_argument("--headless")
        log.info("Running driver in headless mode")

    #Additional options to avoid detection:
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    #webdriver instance with options:
    wd = webdriver.Chrome(options=driver_options)

    try:
        #call get images function and download images from them
        image_urls = get_images_from_google(webdriver=wd, search_request=search_query, delay:int=1, max_images:int =max_images)

        #No images found, saves page source if in debug mode
        if not image_urls:
            logger.error("No images found, please check selectors updated selectors or try a different query")
            if DEBUG_MODE:
                save_page_source(wd, "failed_search")
            return

        #dictionary for tracking downloads
        download_stats = {"success":0, "failed":0, "rejected":0}

        #Download images based on found urls
        for i, url in enumerate(image_urls):
            download_image(accepted_path, rejected_path, url=url, filename=f"{search_query}_{i+1}.png")
            download_stats[result] += 1

        #Logger summary of downloads:
        log.info("\n" + "+"*50)
        log.info("Download summary:")
        log.info(f"Successful downloads: {download_stats['sucess']}")
        log.info(f"Failed downloads: {download_stats["failed"]}")
        log.info(f"Rejected downloads: {download_stats["rejected"]}")
        log.info(f"Total attempts: {len(image_urls)}")
        log.info("+"*50)

    except Exception as e:
        log.error(f"Whoops - something messed up twin read the error message cos I can't: {e}")
        if DEBUG_MODE:
            save_page_source(wd, "error")
    finally:
        if DEBUG_MODE:
            input("\nPress enter to close browser window")
        wd.quit() #ensures webdriver instance is quit even if error occurs
        log.info("Download complete, please check for downloaded images in 'images' folder")
    
def save_cookies(webdriver, filename:str = "google_cookies.pkl"):
    """
    Saves cookies to file for reuse in future sessions
    Run once after manually accepting/rejecting cookies to save the state
    """
    import pickle
    try:
        cookies = webdriver.get_cookies()
        with open(filename, "wb") as f:
            pickle.dump(cookies,f)
        log.info(f"Cookies saved to {filename}")
        return True
    except Exception as e:
        log.error(f"Failed to save cookies: {e}")
        return False

def load_cookies(webdriver, filename:str = "google_cookies.pkl"):
    """
    Loads cookeis from file to webdriver instance
    """
    import pickle 

    #file existence check
    if not os.path.exists(filename):
        log.info("No saved cookies file found")
        return False

    # try to load cookies from google.com using the pkl file
    try:
        wd.get("https://google.com") #navigate to google to set domain for cookies
        time.sleep(2)

        with open(filename, "rb") as f: #opens file in read binary mode
            cookies = pickle.load(f)
        
        # add each cookie to webdriver
        for cookie in cookies:
            try:
                webdriver.add_cookie(cookie)
            except Exception as e:
                log.debug(f"Failed to add cookie {cookie.get('name')}: {e}")

        log.info(f"Cookies loaded from {filename}")
        return True
    
    except Exception as e:
        log.error(f"Failed to load cookies: {e}")
        return False

def handle_cookies(webdriver, accept:bool=True, delay:int=5):
    """
    Handles cookie pop ups by either accepting or rejecting cookies, default accept
    """
    #Chcks user selection
    selectors = ACCEPT_COOKIES_SELECTORS if accept else REJECT_COOKIES_SELECTORS
    action = "accept" if accept else "reject"

    log.info(f"Attempting to {action} cookies")

    # tries each selector in list till it works, clicks on relevant button if found
    for selector in selectors:
        try:
            method = By.XPath if selector.startswith("//") else By.CSS_SELECTOR
            button = WebDriverWait(webdriver, delay).until(EC.element_to_be_clickable(method, selector))
            button.click()
            log.info(f"Cookies {action}ed")
            time.sleep(1) #wait for 2 seconds after clicking
            return True
        except TimeoutException: #didn't find anything with selector
            log.info(f"No action found using {selector}, trying next selector")
            continue
        except Exception as e:
            log.error("Error while trying to {action} cookies using {selector}: {e}")
            continue

    log.info("No cookie pop up found or selectors failed")
    return False

def find_elements(webdriver, selectors:list, element_type:str="elements"):
    """
    Tries multiple selectors until one works.
    """
    for selector in selectors:
        try:
            elements = wd.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                log.info(f"Found {len(elements)} {element_type} using selector: {selector}")
                return elements, selector
            except Exception as e:
                log.debug(f"Selector {selector} failed: {e}")
                continue

    #if no selectors work error raised and empty list returned
    log.warning(f"All selectors failed for {element_type}, please check for updates")
    return [], None

def thumbnails_fallback(webdriver):
    """
    Fallback function to find images  by characteristics if all selectors fail
    """
    log.info("Attempting to find thumbnails using fallback")
    all_images = wd.find_elements(By.TAG_NAME, "img")
    thumbnails = []


def get_images_from_google(webdriver, search_request:str ,delay:int, max_images:int):
    """
    Gets images from google search via the following steps:
    1) uses webdriver to get to google images page and sleeps for 5 seconds for any cookies etc
    2) finds search box and enters search query and presses enter/return
    """
    def scroll_down(webdriver):
        """
        Scrolls down the webpage to load more images
        1) Executes JavaScript to scroll to the bottom of the page (document.body.scrollHeight)
        2) waits for a specified delay to allow images to load
        """
        wd.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
        #handle edge cases for this such as looks like you have reached the end of the page
    
    wd.get("https://google.com/imghp?hl=en") #gets page to google images url
    time.sleep(5) # any cookies that need to be accepted or rejected can be done in this delay period

    #Finding search box and entering query:
    search = wd.find_element(By.NAME, "q") 
    search.send_keys(search_query) 
    search.send_keys(Keys.RETURN) 
    
    image_urls = set() #makes a set to store image urls to prevent duplicate urls
    skips = 0 #counter to keep track of skipped images due to duplicates

    while (len(image_urls)+skips) < max_images: #loops until we have enough image urls as requested by function_call
        scroll_down(wd)


        #sclick show more button if it exists if no such element exists just move on
        try:
            show_more = wd.find_element(By.CLASS_NAME, "mye4qd")
            show_more.click()
            time.sleep(2)
        except NoSuchElementException:
            pass
        
        #find image thumbnails using CSS selector with images of rg_i class
        thumbnails = wd.find_elements(By.CSS_SELECTOR, "img.rg_i") 
        if not thumbnails: #no thumnnails found then break out of the while loop
            print("No more images found, breaking out of loop")
            break

        for image in thumbnails[len(image_urls)+skips]:
            if len(image_urls) >= max_images:
                break #breaks out of loop if enough urls found
            
            #try to get full image by clicking on thumbnail to avoid resizing issues
            try:
                image.click()
                time.sleep(delay) 
            except ElementClickInterceptedException:
                continue #if click fails then continue to the next thumbnail in the loop
            
            images = wd.find_elements(By.CLASS_NAME, "sFlh5c") #finds all elements with that class
            for img in images: #loops through all returned images
                if img.get_attribute("src") in image_urls: #checks if src attribute in set to prevent looping
                    max_images += 1 #inrements max images to ensure we get enough unique images
                    skips += 1 #increments skips counter 
                    break #breaks out of for loop to go to next thumbnail

                if img.get_attribute("src") and "http" in img.get_attribute("src"): #checks if src attribute exists # and contains http
                    image_urls.add(img.get_attribute("src"))
                    print(f"Found {len(image_urls)}") #logs each found image (just for tracking progress)


    return image_urls

def download_image(download_path, url, file_name): #function to download image
    """
    1) Make get request and fetch content from url with requests.get(url).content
    2) convert to a binary data format with io.BytesIO
    3) convert binary data format to image object with PIL.Image
    4) create a file path to save image from download_path and file_name by string concatenation
    5) open file to write in wb (write binary) mode
    6) save image in requested format (be it PNG or JPEG or others)
    7) print success message with file path
    """
    try:
        image_content = requests.get(url).content #makes http get request and fetches content of url
        image_file = io.BytesIO(image_content) #stores a binary data format of image content in memory
        image = Image.open(image_file) #converts binary data to image object
        file_path = download_path + file_name # creates a file path to save the image by string concatenation
        with open(file_path, "wb") as f:  #opens file to write in wb (write binary) mode
            image.save(f, "PNG") #saves the image in a png format

        print(f"Great success - saved image as {file_path}")
    except Exception as e:
        print(f" Whoops - something fucked up twin read the error message cos I can't: {e}")

if __name__ == "__main__":
    main()
    input("Press any key to exit")




