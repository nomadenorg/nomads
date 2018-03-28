# Nomaden Termin-Datenbank

Warning: lot's of outdated info here, we moved away from Google App Engine.

The main purpose of the app is to schedule a computer science regulars
table in Hamburg. This regulars table meets in a different (gastro-)
pub each tuesday. The app enables people to enter pubs on a waiting
list. Every wednesday night a list of four fixed pubs is generated,
which are then announced to the world as the next meeting
places. Every tuesday we meet and enjoy the day.

This is a Google App Engine Project. It uses the cloud datastore internally.

You'll find the central application logic in nomaden.py, this defines all application logic. The framework is webapp2.

Templates are to be found in templates/*, these are Jinja2 templates.

Frontend boilerplate is provided by Skeleton (http://getskeleton.com/).

Static assets are to be found in assets, whenever they're not in the root path.

We try making this a responsive webapp, performing equally well on
desktop and on mobile.

The original app is hosted at http://nomaden.org.
The current demo app is hosted at https://nomaden.ofosos.org

When you're developing, you can trigger the cronjob via
http://localhost:8080/schedulePubs This should just return an empty
page. This runs the cronjob that marks pubs as scheduled and archives
older ones. Log in to the test appengine via the login button on the
lower right corner and mark that you're an admin user. Otherwise you
will not be able to trigger the cronjob.

To finally deploy I recommend doing a `git archive master | tar -x -C ~/deploy-path` and then uploading that stuff into AppEngine or pointing the development server to that path. Then install the missing libraries via `pip install -r requirements.txt -t lib`.

See the file LICENSE for license information to the app. The images
(favicon.ico, assets/camel.jpg and assets/camel-250.jpg) included are
owned by the nomaden.org group of people.

See the file CONTRIBUTORS.md for contributor information.
