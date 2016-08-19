#Nomaden Termin-Datenbank

This is a Google App Engine Project.

You'll find the central application logic in nomaden.py, this defines all logic.

Templates are to be found in templates/*, these are Jinja2 templates.

Static assets are to be found in assets, whenever they're not in the root path.

The main purpose of the app is to schedule a computer science regulars table in Hamburg. This regulars table meets in a different (gastro-) pub each tuesday. The app enables people to enter pubs on a waiting list. Every wednesday night a list of four fixed pubs is generated, which are then announced to the world as the next meeting places.

The original app was hosted at http://nomaden.org.
