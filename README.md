# Python Image scraper using selenium
Image scraper to download images by a user given query in google images.

This is purely a learning exercise and is meant to be useful for dataset creation for training an image classifier model that will be made soon enough, that being said I hate image scraping so much.

Please note that as webscraping is a new field for me, claude was used in providing suggestions such as cookies handling functionality (mainly the idea of storing it in a pkl file) and it also helped with my learning journey for helping publish the package.

In version 0.1.1b (the current release version on PyPi) you will have slightly faster downloads (I hope) due to multithreading support (also new to this so please reach out to me if I have messed up). 

#### YOU CAN FINALLY INSTALL IT PEOPLE (still no tests though)

To install the package in terminal and run:

```bash 
pip install img-scrapr
```

Go into a folder (where you wish to store the images) using terminal and run:

```bash
scrape
```

Alternatively you can also run the following command in terminal (if scrape does not work or is assigned to another command already):

```bash
google-images-scraper
```

Once the program has begun follow the instructions in the terminal for the questions asked by the program 

Please note it does sometimes go off on the deep end with the images it downloads I am sorry I am working on it. I also know I should write tests and I will (soon).


