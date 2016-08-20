#Nomaden Termin-Datenbank

The main purpose of the app is to schedule a computer science regulars
table in Hamburg. This regulars table meets in a different (gastro-)
pub each tuesday. The app enables people to enter pubs on a waiting
list. Every wednesday night a list of four fixed pubs is generated,
which are then announced to the world as the next meeting
places. Every tuesday we meet and enjoy the day.

This is a Google App Engine Project. It uses the cloud datastore internally.

You'll find the central application logic in nomaden.py, this defines all application logic. The framework is webapp2.

Templates are to be found in templates/*, these are Jinja2 templates.

Static assets are to be found in assets, whenever they're not in the root path.

We try making this a responsive webapp, performing equally well on
desktop and on mobile.

The original app was hosted at http://nomaden.org.

When you're developing, you can trigger the cronjob via
http://localhost:8080/schedulePubs This should just return an empty
page. This runs the cronjob that marks pubs as scheduled and archives
older ones. Log in to the test appengine via the login button on the
lower right corner and mark that you're an admin user. Otherwise you
will not be able to trigger the cronjob.
