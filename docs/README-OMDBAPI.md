# README-OMDBAPI

### BACKGROUND:

The ARM uses a call to the OMDbAPI (Open Movie Database API) website to determine whether a video disc
is a movie or a TV series. It also uses the database to determine the correct year for a movie, since
older movies frequently report the date of issue on DVD as opposed to the date of the actual movie. An
example of this is "The Enforcer" which was originally released in 1976 but released on DVD in 2008.

Give the two primary functions OMDBAPI is used for in ARM, it's fair to say that having it not work is
more than a bit of a headache in re-titling and categorizing your final product. Years may be
wrong, and as the ARM is currently designed, your movies will be placed in the Unknown directory as 
opposed to the "Movies" directory. I can also see plenty of future uses for this functionality, so it
seemed prudent to repair it and make it work again. And I like shell scripts, and I wanted to
contribute something that might truly be useful to an already amazing project.

---

### HOW TO GET YOUR OWN OMDBAPI KEY:

Start by visiting https://www.omdbapi.com/apikey.aspx and select "Free! (1,000 daily limit)" if you are not an active Patron of OMDb.
Enter email address and submit request. Once email arrives, be sure to click the link contained in the 
email to activate your key. Your key will not function until this step is completed. 

NOTE: Patrons receive significantly more daily API requests. Please consider contributing.    

### TO USE YOUR NEW OMDBAPI KEY:

Open the ARM web UI and navigate to **Settings** (`/config`). Under **Metadata / identification**,
enter your key in the **OMDb API key** field and save. The key is stored in the database and takes
effect immediately — no restart required.

### DEVELOPER'S NOTES:

A special thank you to Aaron Helton (aargonian) for your help with the Python update...I'm a
Shell scripter, not a Python scripter...:-)
