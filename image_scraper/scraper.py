import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    ElementClickInterceptedException, 
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException
)
from selenium.webdriver.support import expected_conditions as EC
import requests
import io
from PIL import Image
import time
import os
import logging
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

try:
    from .config import (
        DEBUG_MODE,
        HEADLESS,
        SELECTOR_VERSION,
        DELAY,
        THUMBNAIL_SELECTORS,
        FULL_IMAGE_SELECTORS,
        ACCEPT_COOKIES_SELECTORS,
        REJECT_COOKIES_SELECTORS
    )
except ImportError:
    #CONFIGURATION if importing config.py fails: 
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
        "img.sFlh5c.FyHeAf", #default
        "img.sFlh5c", 
        "img.n3VNCb",
        "img.iPVvYb", 
        "div.islrc img",
        "img.r48jcc",
        "img.VFACy",     
        "a.wXeWr.fxgdke img", 
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
    format= "%(asctime)s - %(levelname)s - %(message)s",
    handlers= [#log config
        logging.FileHandler("image_scraper.log"), #logs to file
        logging.StreamHandler()#logs to console
    ]
)
log = logging.getLogger(__name__) #logger instance

def driver_setup(headless:bool = False):
    """
    Sets up undetected chromedriver with options
    """
    driver_options = uc.ChromeOptions()

    #Headless setup:
    if headless:
        driver_options.add_argument("--headless=new")
        log.info("Running driver in headless mode")

    #Additional options for stability:
    driver_options.add_argument("--no-sandbox")
    driver_options.add_argument("--disable-dev-shm-usage")
    driver_options.add_argument("--window-size=1920,1080")

    # Create undetected Chrome instance
    try:
        wd = uc.Chrome(options=driver_options, version_main=None)
        log.info("Undetected Chrome initialized successfully")
        return wd
    except Exception as e:
        log.error(f"Failed to initialize Chrome: {e}")
        return None


def main(query:str=None, max_images:int=None):
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
    if query is None:
        query = input("What images would you like to search for? (Please be detailed): ") #user query
    if max_images is None:
        max_images = int(input("How many images would you like to download?: ")) #max images wanted

    #starting logs
    log.info(f"Starting image scraper for query: {query} with {max_images} images")
    log.info(f"Selector version: {SELECTOR_VERSION}, if it doesn't work please check for updates")
    log.info("Using undetected-chromedriver to avoid bot detection")

    # Undetected Chrome setup
    driver_options = uc.ChromeOptions()

    headless_mode:str = ''
    try:
        while headless_mode not in ['y','n']:
            headless_mode = input("Would you like to run the browser in headless mode? (y/n): ").lower()
    except KeyboardInterrupt:
        log.info("User interrupted input, defaulting to headless mode 'n'")
        headless_mode = 'n'

    headless = (headless_mode == 'y')
    wd = driver_setup(headless=headless)
    if not wd:
        log.error("Webdriver setup failed, exiting...")
        return

    try:
        #call get images function and download images from them
        image_urls = get_images_from_google(webdriver=wd, search_request=query, delay=DELAY, max_images=max_images)

        #No images found, saves page source if in debug mode
        if not image_urls:
            log.error("No images found, please check selectors or try a different query")
            if DEBUG_MODE:
                save_page_source(wd, "failed_search")
            return

            #convert set to list to make sure index can be accessed:
        image_urls_list= list(image_urls)
        log.info(f"\n Starting multithreaded download of {len(image_urls_list)} images...")

        #dictionary for tracking downloads and lock for thready safety
        download_stats = {"success":0, "failed":0, "rejected":0}
        stats_lock = Lock()

        #multithreaded downloading: Prepare thread pool using 5 for good behaviour
        max_workers = min(5, len(image_urls_list)) #max 5 threads or less if we have less images
        log.info(f"Using {max_workers} worker threads\n")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            #submit all download tasks and map to urls:
            future_to_url = {} #empty dict to see which future belongs to which url
            for i, url in enumerate(image_urls_list):
                future = executor.submit( #submit download task to the worker thread
                    download_image,
                    original_path=original_path,
                    rejected_path=rejected_path,
                    url=url,
                    file_name=f"{query}_{i+1}.jpg"
                )
                future_to_url[future] = (i,url) #map future to index and url as a tuple

                #update stats as futures complete individually
            completed = 0 
            for future in as_completed(future_to_url):
                completed += 1
                try:
                    result = future.result() #get download result

                    #update stats with thread-safety:
                    with stats_lock:
                        download_stats[result] += 1

                    #Progress log:
                    log.info(f"Progress: {completed}/{len(image_urls_list)} images downloaded")
                except Exception as e:
                    log.error(f"Image download failed - Error in downloading image: {e}")
                    with stats_lock:
                        download_stats["failed"] += 1 

        #Logger summary of downloads:
        log.info("\n" + "+"*50)
        log.info("Download summary:")
        log.info(f"Successful downloads: {download_stats['success']}")
        log.info(f"Failed downloads: {download_stats['failed']}")
        log.info(f"Rejected downloads: {download_stats['rejected']}")
        log.info(f"Total attempts: {len(image_urls)}")
        log.info("+"*50)

    except Exception as e:
        log.error(f"Error during scraping: {e}")
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
    Loads cookies from file to webdriver instance
    """
    import pickle 

    #file existence check
    if not os.path.exists(filename):
        log.info("No saved cookies file found")
        return False

    # try to load cookies from google.com using the pkl file
    try:
        webdriver.get("https://google.com") #navigate to google to set domain for cookies
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
    #Checks user selection
    selectors = ACCEPT_COOKIES_SELECTORS if accept else REJECT_COOKIES_SELECTORS
    action = "accept" if accept else "reject"

    log.info(f"Attempting to {action} cookies")

    # tries each selector in list till it works, clicks on relevant button if found
    for selector in selectors:
        try:
            method = By.XPATH if selector.startswith("//") else By.CSS_SELECTOR
            button = WebDriverWait(webdriver, delay).until(EC.element_to_be_clickable((method, selector)))
            button.click()
            log.info(f"Cookies {action}ed")
            time.sleep(1)
            return True
        except TimeoutException: #didn't find anything with selector
            log.debug(f"No action found using {selector}, trying next selector")
            continue
        except Exception as e:
            log.error(f"Error while trying to {action} cookies using {selector}: {e}")
            continue

    log.info("No cookie pop up found or selectors failed")
    return False

def find_elements(webdriver, selectors:list, element_type:str="elements"):
    """
    Tries multiple selectors until one works.
    """
    for selector in selectors:
        try:
            elements = webdriver.find_elements(By.CSS_SELECTOR, selector)
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
    Fallback function to find images by characteristics if all selectors fail
    """
    log.info("Attempting to find thumbnails using fallback")
    all_images = webdriver.find_elements(By.TAG_NAME, "img")
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
    
    log.info(f"Fallback found {len(thumbnails)} thumbnails")
    return thumbnails


def get_images_from_google(webdriver, search_request:str, delay:int, max_images:int, max_allowed_failures:int = 20):
    """
    Gets images from google search with improved stale element handling
    """
    def scroll_down(wd):
        """
        Scrolls down with random delay for more human-like behavior
        """
        wd.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # Increased wait time after scrolling
        time.sleep(delay + random.uniform(1.0, 2.0))
    
    def wait_for_page_load(wd, timeout=5):
        """
        Waits for page to finish loading by checking document ready state
        """
        try:
            WebDriverWait(wd, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            time.sleep(0.5)  # Extra buffer
            return True
        except TimeoutException:
            log.warning("Page load timeout")
            return False
    
    cookies_loaded = load_cookies(webdriver)
    log.info("Navigating to Google Images")
    webdriver.get("https://google.com/imghp?hl=en")
    wait_for_page_load(webdriver)  # Wait for initial load

    #cookie handling in case of expiration or otherwise
    if not cookies_loaded:
        consent_handled = handle_cookies(webdriver, accept=True, delay=5)
        if consent_handled:
            save_cookies(webdriver)

    #Finding search box and entering query:
    try:
        search = webdriver.find_element(By.NAME, "q") 
        search.send_keys(search_request) 
        search.send_keys(Keys.RETURN)
        wait_for_page_load(webdriver)  # Wait for search results
        time.sleep(1)  # Extra buffer for images to render
    except Exception as e:
        log.error(f"Failed to enter search query: {e}")
        return set()
    
    log.info(f"Searching for images of {search_request}")

    #url set, counter, thumbnail and fullsize initialisation
    image_urls = set()
    skips = 0
    successful_thumbnail_selector = None
    successful_fullsize_selector = None
    processed_count = 0
    consecutive_failures = 0
    max_failures = max_allowed_failures
    last_thumbnail_count = 0  # Track if we're making progress
    

    #loop for image finding:
    while len(image_urls) < max_images:
        if len(image_urls) >= max_images:
            log.warning(f"Reached max images allowed: {max_images}")
            break

        scroll_down(webdriver)
        wait_for_page_load(webdriver)  # Wait after scroll
    
        #click show more button if it exists
        try:
            show_more = webdriver.find_element(By.CSS_SELECTOR, ".mye4qd")
            show_more.click()
            log.info("Clicked 'Show more results' button")
            wait_for_page_load(webdriver)  # Wait after clicking button
            time.sleep(2)
        except NoSuchElementException:
            pass

        #Find fresh batch of thumbnails
        thumbnails, t_selector = find_elements(webdriver, THUMBNAIL_SELECTORS, "thumbnails")

        #if no thumbnail selector works then use image characteristics fallback
        if not thumbnails:
            thumbnails = thumbnails_fallback(webdriver)
            if not thumbnails:
                log.error("All thumbnail selectors and fallback methods failed")
                break
        
        #remember which selector worked
        if t_selector and not successful_thumbnail_selector:
            successful_thumbnail_selector = t_selector
            log.info(f"Using thumbnail selector: {t_selector}")

        # Check if we're stuck (same number of thumbnails)
        if len(thumbnails) == last_thumbnail_count:
            consecutive_failures += 1
            log.warning(f"No new thumbnails loaded ({consecutive_failures}/5)")
        else:
            consecutive_failures = 0
            last_thumbnail_count = len(thumbnails)

        # Process only new thumbnails (skip ones we already processed)
        new_thumbnails = thumbnails[processed_count:]
        log.info(f"Processing {len(new_thumbnails)} new thumbnails")

        if len(new_thumbnails) == 0:
            log.warning("No new thumbnails to process after scrolling")
            if consecutive_failures >= 5:
                log.error("No new thumbnails found, ending search to avoid infinite loop.")
                break
            continue
        
        #checking target inside loop
        for idx, thumbnail in enumerate(new_thumbnails):
            if len(image_urls) >= max_images: 
                break

            try:
                # Wait for thumbnail to be clickable
                WebDriverWait(webdriver, 3).until(
                    EC.element_to_be_clickable(thumbnail)
                )
                
                # Scroll element into view before clicking
                webdriver.execute_script("arguments[0].scrollIntoView({block: 'center'});", thumbnail)
                time.sleep(0.3)  # Wait for scroll animation
                
                # Click thumbnail with increased delay
                thumbnail.click()
                time.sleep(delay + random.uniform(0.5, 1.0))  # Increased from 0.1-0.3
                
                # Wait for side panel/overlay to load
                wait_for_page_load(webdriver)
                
            except (ElementClickInterceptedException, StaleElementReferenceException) as e:
                log.debug(f"Couldn't click thumbnail: {e}")
                processed_count += 1
                skips += 1
                continue
            except TimeoutException:
                log.debug(f"Thumbnail not clickable after timeout")
                processed_count += 1
                skips += 1
                continue
            except Exception as e:
                log.debug(f"Unexpected error clicking: {e}")
                processed_count += 1
                skips += 1
                continue
            
            # Add wait before finding full-size images
            time.sleep(0.5)
            
            #find full size images using selectors
            full_images, f_selector = find_elements(webdriver, FULL_IMAGE_SELECTORS, "full-size images")

            #if no full image selectors work then log and continue
            if not full_images:
                log.debug("No full image found for this thumbnail")
                processed_count += 1
                skips += 1
                continue

            #remember successful full image selector
            if f_selector and not successful_fullsize_selector:
                successful_fullsize_selector = f_selector
                log.info(f"Using full image selector: {f_selector}")

            for img in full_images:
                try:
                    # Wait for src attribute to be available
                    src = None
                    for attempt in range(3):
                        src = img.get_attribute("src")
                        if src and "http" in src:
                            break
                        time.sleep(0.3)  # Wait between attempts
                    
                    if not src or "http" not in src:
                        continue
                    
                    if src in image_urls:
                        skips += 1
                        break
                    
                    image_urls.add(src)
                    log.info(f"Found {len(image_urls)}/{max_images}")
                    break
                    
                except Exception as e:
                    log.debug(f"Error getting src: {e}")
                    continue
            
            processed_count += 1

        #Safety checks:

        #url target check
        if len(image_urls) >= max_images:
            log.info(f"Reached target of {max_images} images")
            break
        #thumbnail exhaustion check
        if len(thumbnails) < 20 and len(image_urls) < max_images:
            log.warning("Few thumbnails remaining, possibly reached end of results")
            break
        
        #consecutive failure check
        if consecutive_failures >= max_failures:
            log.error("Maximum consecutive failures reached, ending search to avoid infinite loop.")
            break

        # processing current thumbnails check
        if processed_count >= len(thumbnails):
            log.info("Processed all current thumbnails, scrolling for more...")
            continue
    
    #LOG SELECTOR SUMMARY:
    log.info("\n" + "="*50)
    log.info("SELECTOR SUMMARY:")
    log.info(f"Thumbnail selector: {successful_thumbnail_selector or 'Fallback method used'}")
    log.info(f"Full-size selector: {successful_fullsize_selector or 'None found'}")
    log.info(f"Image urls collected: {len(image_urls)}")
    log.info(f"Duplicates/failures skipped: {skips}")
    log.info("="*50)

    return image_urls

def valid_image(image):
    """
    Validates image by checking file format and dimensions.
    returns validity and reason
    """
    #min size checks:
    width, height = image.size
    if width < 100 or height < 100:
        log.debug(f"Image is too small: {width}x{height}")
        return False, "too_small"
    
    #aspect ratio checks:
    aspect_ratio:float = max(width,height)/min(width,height)
    if aspect_ratio > 3.0: #arbitrary aspect ratio limit of 3:1
        log.debug(f"Image has poor aspect ratio: {aspect_ratio:.2f}")
        return False, "poor_aspect_ratio"
    
    return True, "valid"


def download_image(original_path:str, rejected_path:str, url:str, file_name:str):
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
            reject_path = os.path.join(rejected_path, reason)
            if not os.path.exists(reject_path):
                os.makedirs(reject_path)
            #file path for rejected image of that reason, save image in path as jpeg
            file_path = os.path.join(reject_path, file_name)
            with open(file_path, "wb") as f:
                image.save(f, "JPEG", quality=85)
            
            #log and rejection returned
            log.info(f"Image rejected due to {reason}: {file_name}")
            return "rejected"
        
        #accepted image handling:
        file_path = os.path.join(original_path, file_name)
        with open(file_path,"wb") as f:
            image.save(f, "JPEG", quality=95)

        log.info(f"✓ Downloaded: {file_name} ({image.size[0]}x{image.size[1]})")
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
            f.write(webdriver.page_source)
        log.info(f"Page source saved as {filename}")
    except Exception as e:
        log.error(f"Failed to save page source due to error: {e}")

if __name__ == "__main__":
    main()
    input("\nPress enter key to exit")