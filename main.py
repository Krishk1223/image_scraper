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
            download_image(original_path=original_path, rejected_path=rejected_path, url=url, filename=f"{search_query}_{i+1}.png")
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
    for image in all_images:
        try:
            size = image.size
            if 50 < size['width'] < 400 and 50 < size['height'] < 400: #generally thumbnails between 100 to 300px
                src = image.get_attribute("src") or image.get_attribute("data-src")
                if src and image.is_displayed(): #checks if src exists and image is visible
                    thumbnails.append(image)
        except:
            continue
    
    log.info(f"Fallback found {len(thumbnails)}")
    return thumbnails



def get_images_from_google(webdriver, search_request:str ,delay:int, max_images:int):
    """
    Gets images from google search via the following steps:
    1) uses webdriver to get to google images page and sleeps for 5 seconds for any cookies etc
    2) finds search box and enters search query and presses enter/return
    """
    def scroll_down(wd):
        """
        Scrolls down the webpage to load more images
        1) Executes JavaScript to scroll to the bottom of the page (document.body.scrollHeight)
        2) waits for a specified delay to allow images to load
        """
        wd.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
        #handle edge cases for this such as looks like you have reached the end of the page
    cookies_loaded = load_cookies(webdriver)

    log.info("Navigating to Google Images")

    webdriver.get("https://google.com/imghp?hl=en") #gets page to google images url
    time.sleep(1)

    #cookie handling in case of expiration or otherwise
    if not cookies_loaded:
        consent_handled = handle_cookies(webdriver, accept=True, delay=5)

        if consent_handled:
            save_cookies(webdriver) #saves updated cookies for future sessions
        

    #Finding search box and entering query:
    try:
        search = webdriver.find_element(By.NAME, "q") 
        search.send_keys(search_query) 
        search.send_keys(Keys.RETURN)
        time.sleep(2)
    except Exception as e:
        log.error(f"Failed to enter search query: {e}")
        return set() #returns empty set in error case
    
    log.info(f"Searching for images of {search_request}")

    #url set, counter, thumbnail and fullsize initialisation
    image_urls = set() #makes a set to store image urls to prevent duplicate urls
    skips = 0
    successful_thumbnail_selector = None
    successful_fullsize_selector = None

    #loop for image finding:
    while len(image_urls) < max_images:
        scroll_down(wd=webdriver)
    
        #click show more button if it exists if no such element exists just move on
        try:
            show_more = webdriver.find_element(By.CSS_SELECTOR, ".mye4qd")
            show_more.click()
            log.info("Clicked 'Show more results' button")
            time.sleep(2)
        except NoSuchElementException:
            pass

        #Fall back selector thumbnails:
        thumbnails, t_selector = find_elements(wd, THUMBNAIL_SELECTORS, "thumbnails")

        #if no thumbnail selector works then use image characteristics fallback
        if not thumbnails:
            thumbnails = thumbnails_fallback(webdriver)
            if not thumbnails:
                log.error("All thumbnail selectors and fallback methods failed")
                break
        
        #rememebering fallbacks that worked
        if t_selector and not successful_thumbnail_selector:
            successful_thumbnail_selector = t_selector
            log.info(f"Using thumbnail selector: {t_selector}")

        log.info(f"Processing {len(thumbnails)} thumbnails")

        for image in thumbnails[len(image_urls) + skips:]:
            if len(image_urls) >= max_images: 
                break #breaks out of loop if enough urls found

            #try to get full image by clicking on thumbnail to avoid resizing issues
            try:
                image.click()
                time.sleep(delay) 
            except ElementClickInterceptedException:
                continue #if click fails then continue to the next thumbnail in the loop
            
            #find full size images using selectors
            full_images, f_selector = find_elements(wd, FULL_IMAGE_SELECTORS, "full-size images")

            #if no full image selectors work then log error and continue
            if not full_images:
                log.error("All full image selectors failed, skipping this thumbnail")
                skips += 1
                continue

            #remembering successful full image selector
            if f_selector and not successful_fullsize_selector:
                successful_fullsize_selector = f_selector
                log.info(f"Using full image selector: {f_selector}")

            for img in full_images: #loops through all returned images
                src = img.get_attribute("src")
                if src in image_urls: #checks if src attribute in set to prevent looping
                    max_images += 1 #inrements max images to ensure we get enough unique images
                    skips += 1 #increments skips counter 
                    break #breaks out of for loop to go to next thumbnail

                if src and "http" in src: #checks if src attribute exists and contains http
                    image_urls.add(src)
                    print(f"Found {len(image_urls)}") #logs each found image (just for tracking progress)

        #find image thumbnails using CSS selector with images of rg_i class
        thumbnails = webdriver.find_elements(By.CSS_SELECTOR, "img.rg_i") 
        if not thumbnails: #no thumnnails found then break out of the while loop
            print("No more images found, breaking out of loop")
            break
        
        #Process each thumbnail and click to get full image (account for skips and max image count)
        for image in thumbnails[len(image_urls)+skips]:
            if len(image_urls) >= max_images:
                break #breaks out of loop if enough urls found
            
            try:
                image.click()
                time.sleep(delay)
            except ElementClickInterceptedException:
                log.debug("Click intercepted, skipping to next thumbnail")
                continue
            except Exception as e:
                log.error(f"Error clicking thumbnail, click failed: {e}")
                continue
        
            #finding the full size images with selectors:
            actual_images, full_selector = find_elements(webdriver, FULL_IMAGE_SELECTORS, "full-size images")

            #check which selector worked
            if full_selector and not successful_fullsize_selector:
                successful_fullsize_selector = full_selector
                log.info(f"Using full image size selector: {full_selector}")

            #Process each full size image url found
            for actual_image in actual_images:
                try:
                    src = actual_image.get_attribute("src")
                    if not src or "http"  not in src:
                        continue #skips if src attribute is invalid

                    #duplicate check
                    if src in image_urls:
                        skips+=1
                        break

                    image_urls.add(src)
                    log.info(f"Found {len(image_urls)}/{max_images} so far.")
                    break
                except Exception as e:
                    log.debug(f"Error extracting full image src: {e}")
                    continue
        #Safety checks:
        if len(thumbnails) < 10 and len(image_urls) < max_images:
            log.warning("Far few thumbnails found, possibly reached end of results")
            break
    
    #LOG SELECTTOR SUMMARY:
    log.info("\n" + "="*50)
    log.info("SELECTOR SUMMARY:")
    log.info(f"Thumbnail selector: {successful_thumbnail_selector or 'Fallback method used'}")
    log.info(f"Full-size selector: {successful_fullsize_selector or 'None found'}")
    log.info(f"Image urls collected: {len(image_urls)}")
    log.info(f"Duplicates skipped: {skips}")
    log.info("="*50)

    return image_urls

def valid_image(image):
    """
    Validates image by checking file format and dimensions.
    returns validity and reason
    """
    #min size checks:
    width, height = image.size
    if width < 200 or height < 200:
        log.info(f"Image is too small: {width}x{height}")
        return False, "too_small"
    
    #aspect ratio checks:
    aspect_ratio = max(width,height)/min(width,height)
    if aspect_ratio > 3: #arbitrary aspect ratio limit of 3:1
        log.info(f"Image has poor aspect ratio: {aspect_ratio:.2f}")
        return False, "poor_aspect_ratio"
    
    return True, "valid"


def download_image(original_path:str, rejected_path:str, url:str, file_name:str): #function to download image
    """
    Downloads image from urls and saves to relevant path
    returns 'success', 'failed' or 'rejected' based on outcome
    """

    try:
        #image content download
        response = requests.get(url, timeout=10)
        response.raise_for_status() #raises error for bad status codes

        #Gets image content, converts to a binary stream and opens with PIL
        image_content = response.content
        image_file = io.BytesIO(image_content)
        image = Image.open(image_file).convert("RGB")

        #image quality validation:
        validity, reason = valid_image(image)

        #path set up based on rejection reason:
        if not validity:
            reject_path = os.path.join(rejected_path,reason)
                if not os.path.exists(reject_path):
                    os.makedirs(reject_path)
            #file path for rejected image of that reason, save image in path as png
            file_path = os.path.join(reject_path, file_name)
            with open(file_path, "wb") as f:
                image.save(f, "PNG", quality=90)
            
            #log and rejection returned
            log.info(f"Image rejected due to {reason}, saved to {file_path}")
            return "rejected"
        
        #accepted image handling:
        file_path = os.path.join(original_path, file_name)
        with open(file_path,"wb") as f:
            image.save(f, "PNG", quality=95)

        log.info(f"Image {file_name} successfully downloaded and saved to {file_path}")
        return "success"
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to download image from {url}: {e}")
        return "failed"
    except Exception as e:
        log.error(f"Error processing image from {url}: {e}")
        return "failed"

def save_page_source(webdriver, prefix:str = "debug"):
    """
    Saves page source for debugging purposes
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.html"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(webdriver.page_source())
        log.info(f"Page source saved as {filename}")
    except Exception as e:
        log.error(f"Failed to save page source due to error: {e}")

if __name__ == "__main__":
    main()
    input("\nPress enter key to exit")




