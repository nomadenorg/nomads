import os
import urllib

from google.appengine.api import users
from google.appengine.ext import ndb

import jinja2
import webapp2

import datetime

# model layer

def appointments_key(bucket_name=DEFAULT_BUCKET_NAME):
    return ndb.Key('Appointment', bucket_name)

def apparchive_key(bucket_name=ARCHIVE_BUCKET_NAME):
    return ndb.Key('Appointment', bucket_name)

class Comment(ndb.Model):
    uname = ndb.StringProperty()
    text = ndb.StringProperty()

class Appointment(ndb.Model):
    name = ndb.StringProperty(indexed=False)
    street = ndb.StringProperty(indexed=False)
    city = ndb.StringProperty(indexed=False)
    publictrans = ndb.StringProperty(indexed=False)
    source = ndb.StringProperty(indexed=False)
    entered = ndb.DateTimeProperty(auto_now_add=True)
    setdate = ndb.DateProperty()
    sortorder = ndb.IntegerProperty()
    comments = ndb.LocalStructuredProperty(Comment, repeated=True)


# utility & templates

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__) + '/templates'),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

DEFAULT_BUCKET_NAME = 'current_appointments'
ARCHIVE_BUCKET_NAME = 'archive_appointments'

# user format date
def fmt_date(dat):
    return dat.strftime("%d.%m.%Y")

JINJA_ENVIRONMENT.globals.update(fmt_date=fmt_date)

def next_tuesday():
    target = datetime.date.today()
    while target.isoweekday() <> 2:
        target = target + datetime.timedelta(1)
    return target
        
def previous_tuesday():
    today = datetime.date.today()
    target = today
    while today <= target and target.isoweekday() <> 2:
        target = target - datetime.timedelta(1)
    return target

# http dispatching
    
class MainPage(webapp2.RequestHandler):
    def get(self):
        fixed_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate != None).order(Appointment.setdate)

        fixed_list = fixed_query.fetch(4)

        wait_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None).order(Appointment.sortorder)

        wait_list = wait_query.fetch()
        
        template_values = { 'username': users.get_current_user().nickname(), 'fixed_apps': fixed_list, 'wait_apps': wait_list }

        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(template_values))

class Archive(webapp2.RequestHandler):
    def get(self):
        archive_query = Appointment.query(ancestor=apparchive_key()).order(Appointment.setdate)
        archive_list = archive_query.fetch()

        template_values = { 'archive_apps': archive_list }

        template = JINJA_ENVIRONMENT.get_template('archive.html')
        self.response.write(template.render(template_values))
        
class EnterPub(webapp2.RequestHandler):
    def post(self):
        app = Appointment(parent=appointments_key())

        app.name = self.request.get('name')
        app.street = self.request.get('street')
        app.city = self.request.get('city')
        app.publictrans = self.request.get('publictrans')

        if self.request.get('magic') == '4':
            query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None).order(-Appointment.sortorder)

            sorder = 1
            
            applis = query.fetch(1)
            if len(applis) > 0:
                prev_app = applis[0]
                sorder = prev_app.sortorder + 1

            app.sortorder = sorder
                
            app.put()

        self.redirect('/')

class CommentPub(webapp2.RequestHandler):
    def post(self):
        appid = self.request.get('id')
        uname = self.request.get('author')
        text = self.request.get('text')

        key = ndb.Key(urlsafe=appid)

        app = key.get()

        if app:
            com = Comment()
            com.uname = uname
            com.text = text
        
            app.comments.append(com)

            app.put()

        self.redirect('/')
        
class MoveForwardPub(webapp2.RequestHandler):
    def get(self):
        sortid = int(self.request.get('id'))
        query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None, Appointment.sortorder >= sortid - 1, Appointment.sortorder <= sortid).order(Appointment.sortorder)
        
        applis = query.fetch(2)

        if len(applis) > 1:
            app_a = applis[0]
            app_b = applis[1]

            app_a.sortorder = app_a.sortorder + 1
            app_b.sortorder = app_b.sortorder - 1

            app_a.put()
            app_b.put()

        self.redirect('/')
        
# woechentlicher cronjob
class SchedulePubs(webapp2.RequestHandler):
    def get(self):

        # wir haben drei gruppen

        # die fertig geplanten, feststehenden termine
        archive_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate < datetime.date.today(), Appointment.setdate != None)

        archive_list = archive_query.fetch()

        for app in archive_list:
            app.parent = apparchive_key()
            app.save()

        # die aktuellen, also schon geplanten
        current_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate > datetime.date.today())

        current_list = current_query.fetch()

        current_apps = len(current_list)

        last_date = next_tuesday()
        for app in current_list:
            if app.setdate > last_date:
                last_date = app.setdate

        # die einzufuegenden, die wir aus der warteliste ziehen
        need_apps = 4 - current_apps

        if need_apps > 0:
            next_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None)

            next_list = next_query.fetch(need_apps)

            for app in next_list:
                last_date = last_date + datetime.timedelta(7)
                app.setdate = last_date
                app.put()
        
app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/enterPub', EnterPub),
    ('/schedulePubs', SchedulePubs),
    ('/moveForward', MoveForwardPub),
    ('/comment', CommentPub),
    ('/archive', Archive),
], debug=True)
