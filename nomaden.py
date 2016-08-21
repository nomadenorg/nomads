import os
import urllib

from google.appengine.api import users
from google.appengine.ext import ndb

from logging import info

import jinja2
import webapp2

import datetime

# model layer

DEFAULT_BUCKET_NAME = 'current_appointments'
ARCHIVE_BUCKET_NAME = 'archive_appointments'
BIT_BUCKET_NAME = 'delete_appointments'

# all entities under this root form the current list
def appointments_key(bucket_name=DEFAULT_BUCKET_NAME):
    return ndb.Key('Appointment', bucket_name)

# all entitties under this root form the archive
def apparchive_key(bucket_name=ARCHIVE_BUCKET_NAME):
    return ndb.Key('Appointment', bucket_name)

def bitbucket_key(bucket_name=BIT_BUCKET_NAME):
    return ndb.Key('Appointment', bucket_name)

class Comment(ndb.Model):
    uname = ndb.StringProperty()
    text = ndb.StringProperty()
    source = ndb.StringProperty()

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
    removed = ndb.StringProperty()

class MailContact(ndb.Model):
    name = ndb.StringProperty()
    email = ndb.StringProperty()

class Nomad(ndb.Model):
    name = ndb.StringProperty()
    mail = ndb.StringProperty()
    moderator = ndb.BooleanProperty()

def clone_entity(e, **extra_args):
    klass = e.__class__
    props = dict((v._code_name, v.__get__(e, klass)) for v in klass._properties.itervalues() if type(v) is not ndb.ComputedProperty)
    props.update(extra_args)
    return klass(**props)
    
# utility & templates

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__) + '/templates'),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

def get_nomad():
    nuser = None
    guser = users.get_current_user()

    if guser:
        mail = guser.email().lower()
        q = Nomad.query(Nomad.mail == mail)
        nuserlis = q.fetch(1)
        if len(nuserlis) > 0:
            nuser = nuserlis[0]

    return nuser

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
    target = datetime.date.today()
    while target.isoweekday() <> 2:
        target = target - datetime.timedelta(1)
    return target

# get a source string for reproduceabiltiy purposes
def generate_source(req):
    ip = req.remote_addr
    now = datetime.datetime.now().isoformat()
    uid = "None"
    if users.get_current_user():
        uid = users.get_current_user().user_id()

    return ip + "$" + now + "$" + uid

# http dispatching

class NomadHandler(webapp2.RequestHandler):
    def deny(self):
        self.response.status_int = 403
        self.response.write("<!DOCTYPE html><html><head><title>Can I haz page...</title></head><body><h1>You cannot haz page</h1></body></html>")

class MainPage(webapp2.RequestHandler):
    def get(self):
        fixed_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate != None).order(Appointment.setdate)

        fixed_list = fixed_query.fetch(4)

        wait_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None).order(Appointment.sortorder)

        wait_list = wait_query.fetch()

        current_username = "not logged in"
        if users.get_current_user():
            current_username = users.get_current_user().nickname()

        loginout_text = "Login"
        loginout_url = users.create_login_url('/')

        if users.get_current_user():
            loginout_text = "Logout"
            loginout_url = users.create_logout_url('/')
            
        template_values = {
            'username': current_username,
            'fixed_apps': fixed_list,
            'wait_apps': wait_list,
            'loginout_url': loginout_url,
            'loginout_text': loginout_text, }

        nomad = get_nomad()
        if (nomad and nomad.moderator) or users.is_current_user_admin():
            template_values['moderator'] = "yes"
        
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

        app.source = generate_source(self.request)

        if self.request.get('magic') == '4':
            query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate == None).order(-Appointment.sortorder)

            sorder = 1
            
            applis = query.fetch(1)
            if len(applis) > 0:
                prev_app = applis[0]
                sorder = prev_app.sortorder + 1

            app.sortorder = sorder
                
            app.put()

            info("pub entered")

        self.redirect('/')

class CommentPub(webapp2.RequestHandler):
    def post(self):
        appid = self.request.get('id')
        uname = self.request.get('author')
        text = self.request.get('text')
        magic = self.request.get('magic')

        key = ndb.Key(urlsafe=appid)

        app = key.get()

        if app and magic == "4":
            com = Comment()
            com.uname = uname
            com.text = text

            com.source = generate_source(self.request)
        
            app.comments.append(com)

            app.put()

            info('comment entered on pub id={}'.format(appid))

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

            info('pub moved forward id={}'.format(sortid))

        self.redirect('/')

class DeletePub(webapp2.RequestHandler):
    def get(self):
        nomad = get_nomad()

        if nomad.moderator:
            appid = self.request.get('id')
            app = ndb.Key(urlsafe=appid).get()

            if app:
                newapp = clone_entity(app, parent=bitbucket_key())
                newapp.removed = generate_source(self.request)
                newapp.put()
                app.key.delete()
                info("pub deleted key={}".format(appid))
                
                
        self.redirect('/')

class Moderator(NomadHandler):
    def get(self):
        nomad = get_nomad()

        if (nomad and nomad.moderator) or users.is_current_user_admin():
            q = Nomad.query(Nomad.moderator == True)
            nomads = q.fetch(100)
            
            template_values = {
                'moderators': nomads,
                'is_admin': users.is_current_user_admin(),
            }

            template = JINJA_ENVIRONMENT.get_template('moderator.html')
            self.response.write(template.render(template_values))
        else:
            self.deny()

class ModeratorAdd(webapp2.RequestHandler):
    def get(self):
        name = self.request.get('name')
        mail = self.request.get('mail')

        nomad = Nomad()
        nomad.name = name
        nomad.mail = mail
        nomad.moderator = True
        nomad.put()

        info("moderator created name = {}, mail = {}".format(name, mail))
        
        self.redirect('/moderator')

class ModeratorDelete(webapp2.RequestHandler):
    def get(self):
        pass
        
# woechentlicher cronjob
class SchedulePubs(webapp2.RequestHandler):
    def get(self):

        # wir haben drei gruppen

        # die fertig geplanten, feststehenden termine
        archive_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate < datetime.date.today(), Appointment.setdate != None)

        archive_list = archive_query.fetch()

        for app in archive_list:
            newapp = clone_entity(app, parent=apparchive_key())
            for com in newapp.comments:
                com.source = None
            newapp.source = None
            newapp.put()

            app.key.delete()

        # die aktuellen, also schon geplanten
        current_query = Appointment.query(ancestor=appointments_key()).filter(Appointment.setdate > datetime.date.today())

        current_list = current_query.fetch()

        current_apps = len(current_list)

        last_date = previous_tuesday()
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
    ('/delete', DeletePub),
    ('/comment', CommentPub),
    ('/archive', Archive),
    ('/moderator', Moderator),
    ('/moderatorAdd', ModeratorAdd),
    ('/moderatorDel', ModeratorDelete),
], debug=True)
