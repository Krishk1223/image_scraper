from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, TimeoutException
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
CAPTCHA_WAIT_TIME = 120  # Max seconds to wait for user to solve CAPTCHA

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
        driver_options.add_argument("--headless=new")
        log.info("Running driver in headless mode")

    #Additional options to avoid detection:
    driver_options.add_argument("--disable-blink-features=AutomationControlled")
    driver_options.add_argument("--no-sandbox")
    driver_options.add_argument("--disable-dev-shm-usage")

    #webdriver instance with options:
    wd = webdriver.Chrome(options=driver_options)

    try:
        #call get images function and download images from them
        image_urls = get_images_from_google(webdriver=wd, search_request=query, delay=1, max_images=max_images)

        #No images found, saves page source if in debug mode
        if not image_urls:
            log.error("No images found, please check selectors updated selectors or try a different query")
            if DEBUG_MODE:
                save_page_source(wd, "failed_search")
            return

        #dictionary for tracking downloads
        download_stats = {"success":0, "failed":0, "rejected":0}

        #Download images based on found urls
        for i, url in enumerate(image_urls):
            result = download_image(original_path=original_path, rejected_path=rejected_path, url=url, file_name=f"{query}_{i+1}.jpg")
            download_stats[result] += 1

        #Logger summary of downloads:
        log.info("\n" + "+"*50)
        log.info("Download summary:")
        log.info(f"Successful downloads: {download_stats['success']}")
        log.info(f"Failed downloads: {download_stats['failed']}")
        log.info(f"Rejected downloads: {download_stats['rejected']}")
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
    #Chcks user selection
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
            time.sleep(1) #wait for 2 seconds after clicking
            return True
        except TimeoutException: #didn't find anything with selector
            log.debug(f"No action found using {selector}, trying next selector")
            continue
        except Exception as e:
            log.error(f"Error while trying to {action} cookies using {selector}: {e}")
            continue

    log.info("No cookie pop up found or selectors failed")
    return False

def check_for_captcha(webdriver):
    """
    Checks if a CAPTCHA is present on the page
    Returns True if CAPTCHA detected, False otherwise
    """
    captcha_indicators = [
        "//iframe[contains(@src, 'recaptcha')]",  # reCAPTCHA iframe
        "//div[@id='recaptcha']",  # reCAPTCHA div
        "//*[contains(text(), 'unusual traffic')]",  # Google's CAPTCHA message
        "//*[contains(text(), 'not a robot')]",  # Common CAPTCHA text
        "//form[@id='captcha-form']",  # Generic CAPTCHA form
    ]
    
    for indicator in captcha_indicators:
        try:
            element = webdriver.find_element(By.XPATH, indicator)
            if element.is_displayed():
                return True
        except:
            continue
    
    return False

def wait_for_captcha_solution(webdriver, timeout=120):
    """
    Waits for user to solve CAPTCHA manually
    Returns True if CAPTCHA was solved, False if timeout
    """
    log.warning("CAPTCHA DETECTED! ")
    log.warning("Please solve the CAPTCHA in the browser window...")
    log.warning(f"Waiting up to {timeout} seconds...")
    
    start_time = time.time()
    last_log_time = 0
    
    while time.time() - start_time < timeout:
        # Check if CAPTCHA is still present
        if not check_for_captcha(webdriver):
            log.info("CAPTCHA solved! Waiting for page to stabilize...")
            time.sleep(8)  # Increased from 5 to 8 seconds for page stabilization
            
            # Verify page is actually ready by checking for search box
            try:
                search_box = webdriver.find_element(By.NAME, "q")
                if search_box.is_displayed():
                    log.info("Page is ready! Continuing...")
                    time.sleep(2)  # Extra buffer
                    return True
            except:
                log.info("Waiting for page elements to load...")
                time.sleep(5)  # Increased wait
                # Try one more time
                try:
                    search_box = webdriver.find_element(By.NAME, "q")
                    if search_box:
                        log.info("Page is ready! Continuing...")
                        time.sleep(2)  # Extra buffer
                        return True
                except:
                    pass
            
            return True
        
        # Show countdown every 10 seconds
        elapsed = int(time.time() - start_time)
        if elapsed > 0 and elapsed % 10 == 0 and elapsed != last_log_time:
            remaining = timeout - elapsed
            log.info(f"Still waiting... {remaining} seconds remaining")
            last_log_time = elapsed
        
        time.sleep(1)
    
    log.error("CAPTCHA timeout - could not verify solution")
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
    Fallback function to find images  by characteristics if all selectors fail
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
        Returns True if page height changed (more content loaded), False if at bottom
        """
        last_height = wd.execute_script("return document.body.scrollHeight")
        wd.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
        new_height = wd.execute_script("return document.body.scrollHeight")
        return new_height > last_height
        
    cookies_loaded = load_cookies(webdriver)

    log.info("Navigating to Google Images")

    webdriver.get("https://google.com/imghp?hl=en")
    time.sleep(2)  # Give page time to load

    #cookie handling in case of expiration or otherwise
    if not cookies_loaded:
        consent_handled = handle_cookies(webdriver, accept=True, delay=5)
        if consent_handled:
            save_cookies(webdriver)
    
    # Check for CAPTCHA before proceeding
    if check_for_captcha(webdriver):
        if not wait_for_captcha_solution(webdriver, timeout=CAPTCHA_WAIT_TIME):
            log.error("Could not proceed due to unsolved CAPTCHA")
            return set()
        
        # After solving CAPTCHA, reload the Google Images page
        log.info("Reloading Google Images after CAPTCHA...")
        webdriver.get("https://google.com/imghp?hl=en")
        time.sleep(5)  # Increased from 3 to 5 seconds
        
        # Check again for CAPTCHA after reload
        if check_for_captcha(webdriver):
            log.warning("CAPTCHA appeared again after reload")
            if not wait_for_captcha_solution(webdriver, timeout=CAPTCHA_WAIT_TIME):
                log.error("Could not proceed due to unsolved CAPTCHA on reload")
                return set()
            time.sleep(5)  # Increased from 3 to 5 seconds

    #Finding search box and entering query:
    try:
        # Wait for search box to be present and interactable
        search = WebDriverWait(webdriver, 20).until(  # Increased from 15 to 20 seconds
            EC.element_to_be_clickable((By.NAME, "q"))
        )
        time.sleep(2)  # Increased from 1 to 2 seconds before typing
        search.clear()  # Clear any existing text
        search.send_keys(search_request) 
        search.send_keys(Keys.RETURN)
        time.sleep(5)  # Increased from 4 to 5 seconds wait for results to load
        
        # Check for CAPTCHA after search
        if check_for_captcha(webdriver):
            log.warning("CAPTCHA appeared after search")
            if not wait_for_captcha_solution(webdriver, timeout=CAPTCHA_WAIT_TIME):
                log.error("Could not proceed due to CAPTCHA after search")
                return set()
            # Retry the search after CAPTCHA
            log.info("Retrying search after CAPTCHA...")
            search = WebDriverWait(webdriver, 15).until(
                EC.element_to_be_clickable((By.NAME, "q"))
            )
            search.clear()
            search.send_keys(search_request)
            search.send_keys(Keys.RETURN)
            time.sleep(5)
            
    except TimeoutException:
        log.error("Search box not found - possible CAPTCHA or page load issue")
        if DEBUG_MODE:
            save_page_source(webdriver, "search_box_timeout")
        return set()
    except Exception as e:
        log.error(f"Failed to enter search query: {e}")
        if DEBUG_MODE:
            save_page_source(webdriver, "search_error")
        return set()
    
    log.info(f"Searching for images of {search_request}")

    #url set, counter, thumbnail and fullsize initialisation
    image_urls = set()
    skips = 0
    successful_thumbnail_selector = None
    successful_fullsize_selector = None
    processed_count = 0

    #loop for image finding:
    while len(image_urls) < max_images:
        # Check for CAPTCHA during scraping
        if check_for_captcha(webdriver):
            if not wait_for_captcha_solution(webdriver, timeout=CAPTCHA_WAIT_TIME):
                log.error("CAPTCHA appeared during scraping and was not solved")
                break
        
        # Scroll and check if more content loaded
        can_scroll = scroll_down(webdriver)
    
        #click show more button if it exists
        try:
            show_more = webdriver.find_element(By.CSS_SELECTOR, ".mye4qd")
            show_more.click()
            log.info("Clicked 'Show more results' button")
            time.sleep(2)
        except NoSuchElementException:
            if not can_scroll:
                log.info("Cannot scroll further and no 'Show more' button, stopping")
                break
        
        # Try to scope to main image grid to avoid suggestion chips
        try:
            # Target the main results grid container
            grid = webdriver.find_element(By.CSS_SELECTOR, "div#islrg")
            thumbnails = grid.find_elements(By.TAG_NAME, "img")
            
            # Filter more aggressively:
            # 1. Must have reasonable thumbnail size
            # 2. Must not be in suggestion chips or related searches
            # 3. Must have valid src attribute
            filtered_thumbnails = []
            for thumb in thumbnails:
                try:
                    # Check size
                    if thumb.size.get('width', 0) < 50 or thumb.size.get('height', 0) < 50:
                        continue
                    
                    # Check if it's actually a search result image (has data-* attributes)
                    # Skip if parent contains suggestion/chip/related keywords
                    parent = thumb.find_element(By.XPATH, "./..")
                    parent_class = parent.get_attribute("class") or ""
                    parent_id = parent.get_attribute("id") or ""
                    
                    # Skip if in suggestion chips (usually at top of page)
                    if any(keyword in parent_class.lower() for keyword in ['chip', 'suggestion', 'related', 'search']):
                        continue
                    if any(keyword in parent_id.lower() for keyword in ['suggestion', 'related']):
                        continue
                    
                    # Check if thumbnail is in viewport position (suggestions usually at top)
                    location = thumb.location
                    if location.get('y', 0) < 200:  # Skip elements in first 200px (suggestion area)
                        continue
                    
                    # Must have src attribute
                    src = thumb.get_attribute("src")
                    if not src:
                        continue
                    
                    filtered_thumbnails.append(thumb)
                except:
                    continue
            
            thumbnails = filtered_thumbnails
            t_selector = "div#islrg img (filtered)"
            log.info(f"Scoped and filtered thumbnails in grid: {len(thumbnails)}")
        except Exception as e:
            log.debug(f"Error scoping thumbnails from grid: {e}")
            thumbnails = []
            t_selector = None

        #find thumbnails using selectors if scoping failed
        if not thumbnails:
            thumbnails, t_selector = find_elements(webdriver, THUMBNAIL_SELECTORS, "thumbnails")

            #if no thumbnail selector works then use image characteristics fallback
            if not thumbnails:
                thumbnails = thumbnails_fallback(webdriver)
                if not thumbnails:
                    log.error("All thumbnail selectors and fallback methods failed")
                    break
            
        #remembering fallbacks that worked
        if t_selector and not successful_thumbnail_selector:
            successful_thumbnail_selector = t_selector
            log.info(f"Using thumbnail selector: {t_selector}")

        log.info(f"Processing {len(thumbnails)} thumbnails")

        # Process thumbnails by index to avoid stale elements
        start_index = processed_count
        images_to_process = min(20, len(thumbnails) - start_index)
        
        for offset in range(images_to_process):
            if len(image_urls) >= max_images: 
                break
            
            current_index = start_index + offset

            # Refetch fresh thumbnails for each click to prevent stale references
            try:
                # Scope to grid first with same filtering
                try:
                    grid = webdriver.find_element(By.CSS_SELECTOR, "div#islrg")
                    fresh_thumbnails = grid.find_elements(By.TAG_NAME, "img")
                    
                    # Apply same filtering
                    filtered = []
                    for thumb in fresh_thumbnails:
                        try:
                            if thumb.size.get('width', 0) < 50:
                                continue
                            location = thumb.location
                            if location.get('y', 0) < 200:  # Skip top 200px
                                continue
                            parent = thumb.find_element(By.XPATH, "./..")
                            parent_class = parent.get_attribute("class") or ""
                            if any(kw in parent_class.lower() for kw in ['chip', 'suggestion', 'related', 'search']):
                                continue
                            filtered.append(thumb)
                        except:
                            continue
                    fresh_thumbnails = filtered
                except:
                    fresh_thumbnails, _ = find_elements(webdriver, THUMBNAIL_SELECTORS, "thumbnails")
                
                if not fresh_thumbnails or current_index >= len(fresh_thumbnails):
                    break
                
                fresh_thumbnails[current_index].click()
                time.sleep(delay)
                processed_count += 1
                
            except ElementClickInterceptedException:
                skips += 1
                processed_count += 1
                continue
            except Exception as e:
                log.debug(f"Error clicking thumbnail {current_index}: {e}")
                skips += 1
                processed_count += 1
                continue
            
            #find full size images using selectors
            full_images, f_selector = find_elements(webdriver, FULL_IMAGE_SELECTORS, "full-size images")

            #if no full image selectors work then log error and continue
            if not full_images:
                skips += 1
                continue

            #remembering successful full image selector
            if f_selector and not successful_fullsize_selector:
                successful_fullsize_selector = f_selector
                log.info(f"Using full image selector: {f_selector}")

            for img in full_images:
                try:
                    src = img.get_attribute("src")
                    if not src or "http" not in src:
                        continue
                        
                    if src in image_urls:
                        max_images+=1
                        skips += 1
                        break

                    image_urls.add(src)
                    log.info(f"Found {len(image_urls)}/{max_images}")
                    break
                    
                except Exception as e:
                    log.debug(f"Error getting src from full image: {e}")
                    continue

        #Safety check:
        if len(thumbnails) < 10:
            log.warning("Very few thumbnails found, possibly reached end of results")
            break
    
    #LOG SELECTOR SUMMARY:
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
            #file path for rejected image of that reason, save image in path as jpeg
            file_path = os.path.join(reject_path, file_name)
            with open(file_path, "wb") as f:
                image.save(f, "JPEG", quality=95)
            
            #log and rejection returned
            log.info(f"Image rejected due to {reason}, saved to {file_path}")
            return "rejected"
        
        #accepted image handling:
        file_path = os.path.join(original_path, file_name)
        with open(file_path,"wb") as f:
            image.save(f, "JPEG", quality=95)

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
            f.write(webdriver.page_source)
        log.info(f"Page source saved as {filename}")
    except Exception as e:
        log.error(f"Failed to save page source due to error: {e}")

if __name__ == "__main__":
    main()
    input("\nPress enter key to exit")