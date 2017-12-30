from google.appengine.api import users
from google.appengine.api import mail
from google.appengine.ext import ndb

from logging import info

from flask import Flask, render_template, request, redirect, url_for,\
    make_response

import datetime
import re

from ics import Calendar, Event

# flask app

app = Flask(__name__)

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
@app.context_processor
def fmt_date_proc():
    def fmt_date(dat):
        return dat.strftime("%d.%m.%Y")
    return dict(fmt_date=fmt_date)


@app.context_processor
def fmt_date_print_proc():
    def fmt_date_print(dat):
        return dat.strftime("%d.%m.")
    return dict(fmt_date_print=fmt_date_print)


def next_tuesday(dat):
    target = dat + datetime.timedelta(1)
    while target.isoweekday() != 2:
        target = target + datetime.timedelta(1)
    return target


def previous_tuesday():
    target = datetime.date.today()
    while target.isoweekday() != 2:
        target = target - datetime.timedelta(1)
    return target


# get a source string for reproduceabiltiy purposes
def generate_source(req):
    now = datetime.datetime.now().isoformat()
    uid = "None"
    if users.get_current_user():
        uid = users.get_current_user().user_id()

    return now + "$" + uid


# email handling


# this is the weekly email we send out
class NewsEmail:
    def __init__(self):
        self.pubs = []
        self.sender = "Nomaden-Termindatenbank <ofosos@gmail.com>"
        self.subject = "Nomaden Termine"
        self.recipients = ["Mark Meyer <mark@ofosos.org>"]

    def add_pub(self, pub):
        self.pubs.append(pub)

    def build_body(self):
        template_values = {'pubs': self.pubs}

        template = JINJA_ENVIRONMENT.get_template('weekly.email')
        return template.render(template_values)

    def send(self):
        msg_body = self.build_body()

        for recip in self.recipients:
            mail.send_mail(sender=self.sender,
                           to=recip,
                           subject=self.subject,
                           body=msg_body)


class ParameterError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "Invalid parameter value: " + repr(self.value)


# http dispatching

class NomadHandler():
    posint_pat = re.compile(r'^[0-9]+$')

    def set_headers(self):
        self.response.headers['Content-Security-Policy'] =\
            "default-src 'self'; img-src 'self'; frame-ancestors 'none'"
        self.response.headers['Strict-Transport-Security'] =\
            "max-age=31536000"
        self.response.headers['X-Frame-Options'] = "DENY"
        self.response.headers['X-XSS-Protection'] = "1; mode=block"
        self.response.headers['X-Content-Type-Options'] = 'nosniff'

    def vrfy_posint(self, s):
        if self.posint_pat.match(s):
            return int(s)
        else:
            raise ParameterError(s)
        
    def deny(self):
        self.response.status_int = 403
        self.response.write("<!DOCTYPE html><html><head><title>"
                            "Can I haz page...</title></head><body>"
                            "<h1>You cannot haz page</h1></body></html>")


@app.route('/index', methods=['GET'])
@app.route('/', methods=['GET'])
def main_page():
    fixed_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate != None).\
        order(Appointment.setdate)

    fixed_list = fixed_query.fetch(4)

    wait_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate == None).\
        order(Appointment.sortorder)

    wait_list = wait_query.fetch()

    current_username = "not logged in"
    if users.get_current_user():
        current_username = users.get_current_user().nickname()

    loginout_text = "Login"
    loginout_url = users.create_login_url('/')

    if users.get_current_user():
        loginout_text = "Logout"
        loginout_url = users.create_logout_url('/')

    moderator = 'no'

    nomad = get_nomad()
    if (nomad and nomad.moderator) or users.is_current_user_admin():
        moderator = "yes"

    return render_template('index.html',
                           username=current_username,
                           fixed_apps=fixed_list,
                           wait_apps=wait_list,
                           loginout_url=loginout_url,
                           loginout_text=loginout_text,
                           moderator=moderator)


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500


@app.route('/archive', methods=['GET'])
def archive():
    archive_query = Appointment.query(ancestor=apparchive_key()).\
        order(Appointment.setdate)
    archive_list = archive_query.fetch()

    template_values = {'archive_apps': archive_list}

    return render_template('archive.html', **template_values)


@app.route('/enterPub', methods=['POST'])
def enter_pub():
    app = Appointment(parent=appointments_key())

    app.name = request.form['name']
    app.street = request.form['street']
    app.city = request.form['city']
    app.publictrans = request.form['publictrans']

    app.source = generate_source(request)

    if request.form['magic'] == '4':
        query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None).\
            order(-Appointment.sortorder)

        sorder = 1

        applis = query.fetch(1)
        if len(applis) > 0:
            prev_app = applis[0]
            sorder = prev_app.sortorder + 1

        app.sortorder = sorder

        app.put()

        info("pub entered")

    return redirect(url_for('main_page'))


@app.route('/comment', methods=['POST'])
def comment():
    appid = request.form['id']
    uname = request.form['author']
    text = request.form['text']
    magic = request.form['magic']

    key = ndb.Key(urlsafe=appid)

    app = key.get()

    if app and magic == "4":
        com = Comment()
        com.uname = uname
        com.text = text

        com.source = generate_source(request)

        app.comments.append(com)

        app.put()

        info('comment entered on pub id={}'.format(appid))

    return redirect(url_for('main_page'))


@app.route('/move', methods=['GET'])
def move_pub():
    sortid = int(request.args['id'])

    direction = 'forward'
    if 'direction' in request.args:
        direction = request.args['direction']

    applis = []
    if direction == "forward":
        query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None,
                   Appointment.sortorder >= sortid - 1,
                   Appointment.sortorder <= sortid).\
            order(Appointment.sortorder)
        applis = query.fetch(2)
    else:
        query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None,
                   Appointment.sortorder >= sortid,
                   Appointment.sortorder <= sortid + 1).\
            order(-Appointment.sortorder)
        applis = query.fetch(2)

    if len(applis) > 1:
        app_a = applis[0]
        app_b = applis[1]

        tmp = app_a.sortorder
        app_a.sortorder = app_b.sortorder
        app_b.sortorder = tmp

        app_a.put()
        app_b.put()

        info('pub moved direction={} id={}'.format(direction, sortid))

    return redirect(url_for('main_page'))


@app.route('/delete', methods=['GET'])
def delete():
    nomad = get_nomad()

    if (nomad and nomad.moderator) or users.is_current_user_admin():
        appid = request.args.get('id')
        app = ndb.Key(urlsafe=appid).get()

        if app:
            newapp = clone_entity(app, parent=bitbucket_key())
            newapp.removed = generate_source(request)
            newapp.put()
            app.key.delete()
            info("pub deleted key={}".format(appid))

    return redirect(url_for('main_page'))


@app.route('/moderator', methods=['GET'])
def moderator():
    nomad = get_nomad()
    # FIXME add in values for current user
    if (nomad and nomad.moderator) or users.is_current_user_admin():
        q = Nomad.query(Nomad.moderator == True)
        nomads = q.fetch(100)

        template_values = {
            'moderators': nomads,
            'is_admin': users.is_current_user_admin(),
        }

        return render_template('moderator.html', **template_values)
    else:
        response = make_response(render_template('unauthorized.html'), 403)
        return response


@app.route('/moderatorAdd', methods=['POST'])
def moderator_add():
    name = request.form.get('name')
    mail = request.form.get('mail')

    nomad = Nomad()
    nomad.name = name
    nomad.mail = mail
    nomad.moderator = True
    nomad.put()

    info("moderator created name = {}, mail = {}".format(name, mail))

    return redirect(url_for('moderator'))


@app.route('/publishMail', methods=['GET'])
def publish_mail():
    current_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate != None).\
        order(Appointment.setdate)

    current_list = current_query.fetch(4)

    msg = NewsEmail()
    for app in current_list:
        msg.add_pub(app)

    msg.send()


@app.route('/poster', methods=['GET'])
def poster():
    current_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate != None).\
        order(Appointment.setdate)

    current_list = current_query.fetch(4)

    template_values = {
        'pubs': current_list, }

    return render_template('poster.html', **template_values)


@app.route('/calendar', methods=['GET'])
def calendar():
    appid = request.args.get('id')
    app = ndb.Key(urlsafe=appid).get()

    if app:
        c = Calendar()
        e = Event()

        e.name = "Nomaden im {}, {} ({})".format(app.name, app.street, app.publictrans)
        e.begin = datetime.datetime.combine(app.setdate, datetime.time(19))

        c.events.append(e)

        res = make_response(str(c))
        res.headers['Content-Type'] = 'text/calendar; charset=utf-8'
        return res


# woechentlicher cronjob
@app.route('/schedulePubs', methods=['GET'])
def schedule_pubs():
    # wir haben drei gruppen

    # die fertig geplanten, feststehenden termine
    archive_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate < datetime.date.today(),
               Appointment.setdate != None)

    archive_list = archive_query.fetch()

    for app in archive_list:
        newapp = clone_entity(app, parent=apparchive_key())
        for com in newapp.comments:
            com.source = None
        newapp.source = None
        newapp.put()

        app.key.delete()

    # die aktuellen, also schon geplanten
    current_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate > datetime.date.today())

    current_list = current_query.fetch()

    current_apps = len(current_list)

    fill_dates = {}
    last_date = previous_tuesday()

    for i in range(4):
        last_date = next_tuesday(last_date)
        fill_dates[last_date] = 1
        info("scheduling {}".format(last_date))

    for app in current_list:
        if app.setdate in fill_dates:
            del fill_dates[app.setdate]

    # die einzufuegenden, die wir aus der warteliste ziehen

    klis = sorted(fill_dates.keys(), reverse=True)
    if len(klis) > 0:
        next_query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None)

        next_list = next_query.fetch(1)

        for dat in klis:
            if len(next_list) > 0:
                app = next_list[0]
                app.setdate = dat
                app.put()

                next_list = next_query.fetch(1)
