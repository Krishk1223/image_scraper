"""
Configuration settings for the image scraper.
"""
DEBUG_MODE = False
HEADLESS = False
SELECTOR_VERSION = "2025-10-17"
DELAY = 1

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

