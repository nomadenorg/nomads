from google.appengine.ext import ndb

from logging import info

from flask import Flask, render_template, request, redirect, url_for,\
    make_response

from flask_login import LoginManager, current_user, login_required,\
    login_user, logout_user

from hashlib import pbkdf2_hmac
from binascii import unhexlify

from smtplib import SMTP
from email.mime.text import MIMEText

import datetime
import re

from ics import Calendar, Event

# flask app & login manager

app = Flask(__name__)
login_manager = LoginManager()
login_manager.init_app(app)
app.secret_key = 'This is just a Testing scenario'

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


def clone_entity(e, **extra_args):
    klass = e.__class__
    props = dict((v._code_name, v.__get__(e, klass)) for v in klass._properties.itervalues() if type(v) is not ndb.ComputedProperty)
    props.update(extra_args)
    return klass(**props)


# utility & templates


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
    if current_user.is_active:
        uid = current_user.get_id()

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

        return render_template('weekly.email', **template_values)

    def send(self):
        msg_body = self.build_body()
        msg = MIMEText(msg_body)
        msg['Subject'] = self.subject
        msg['From'] = self.sender
        msg['To'] = ', '.join(self.recipients)

        s = SMTP('localhost')

        s.sendmail(self.sender,
                   self.recipients,
                   msg.as_string())


class ParameterError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "Invalid parameter value: " + repr(self.value)


# user management

class NomadicUser:
    def __init__(self, alg, salt, rounds, secret, username):
        self.alg = alg
        self.salt = salt
        self.rounds = rounds
        self.secret = secret
        self.username = username
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def check_pw(self, pw):
        check = pbkdf2_hmac(self.alg, pw,
                            self.salt, self.rounds)
        return check == self.secret

    def get_id(self):
        return self.username


userdict = {}


def load_users(aDict):
    userfile = open('users.txt', 'r')
    for line in userfile:
        if len(line) > 0:
            tmp = line[:-1]
            alg, salt, rounds, secret, username = tmp.split(':')
            username = username.decode('utf-8')
            secret = unhexlify(secret)
            salt = unhexlify(salt)
            rounds = int(rounds)
            aDict[username] = NomadicUser(alg, salt, rounds, secret, username)


load_users(userdict)


@login_manager.user_loader
def load_user(user_id):
    if user_id in userdict:
        return userdict[user_id]
    return None


# http dispatching


@app.after_request
def set_headers(response):
    response.headers['Content-Security-Policy'] =\
        "default-src 'self'; img-src 'self'; frame-ancestors 'none'"
    response.headers['Strict-Transport-Security'] =\
        "max-age=31536000"
    response.headers['X-Frame-Options'] = "DENY"
    response.headers['X-XSS-Protection'] = "1; mode=block"
    response.headers['X-Content-Type-Options'] = 'nosniff'

    return response


class NomadHandler():
    posint_pat = re.compile(r'^[0-9]+$')

    def vrfy_posint(self, s):
        if self.posint_pat.match(s):
            return int(s)
        else:
            raise ParameterError(s)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    else:
        uname = request.form.get('username')
        pw = request.form.get('password')

        if uname in userdict:
            user = userdict[uname]
            if user.check_pw(pw):
                login_user(user)
                return redirect(url_for('main_page'))
            else:
                return render_template('login.html',
                                       msg='Username or password wrong')
        else:
            return render_template('login.html',
                                   msg='Username or password wrong')


@app.route('/logout', methods=['GET'])
def logout():
    logout_user()
    return redirect(url_for('main_page'))


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
    if current_user.is_active:
        current_username = current_user.get_id()

    loginout_text = "Login"
    loginout_url = url_for('login')

    if current_user.is_active:
        loginout_text = "Logout"
        loginout_url = url_for('logout')

    moderator = 'no'

    if current_user.is_active:
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
    appo = Appointment(parent=appointments_key())

    appo.name = request.form['name']
    appo.street = request.form['street']
    appo.city = request.form['city']
    appo.publictrans = request.form['publictrans']

    appo.source = generate_source(request)

    if request.form['magic'] == '4':
        query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None).\
            order(-Appointment.sortorder)

        sorder = 1

        applis = query.fetch(1)
        if len(applis) > 0:
            prev_app = applis[0]
            sorder = prev_app.sortorder + 1

        appo.sortorder = sorder

        appo.put()

        info("pub entered")

    return redirect(url_for('main_page'))


@app.route('/comment', methods=['POST'])
def comment():
    appid = request.form['id']
    uname = request.form['author']
    text = request.form['text']
    magic = request.form['magic']

    key = ndb.Key(urlsafe=appid)

    appo = key.get()

    if appo and magic == "4":
        com = Comment()
        com.uname = uname
        com.text = text

        com.source = generate_source(request)

        appo.comments.append(com)

        appo.put()

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
@login_required
def delete():
    if current_user.is_active:
        appid = request.args.get('id')
        appo = ndb.Key(urlsafe=appid).get()

        if appo:
            newapp = clone_entity(appo, parent=bitbucket_key())
            newapp.removed = generate_source(request)
            newapp.put()
            appo.key.delete()
            info("pub deleted key={}".format(appid))

    return redirect(url_for('main_page'))


@app.route('/moderator', methods=['GET'])
@login_required
def moderator():
    # FIXME add in values for current user
    if current_user.is_active:
        q = Nomad.query(Nomad.moderator == True)
        nomads = q.fetch(100)

        template_values = {
            'moderators': nomads,
            'is_admin': current_user.is_active,
        }

        return render_template('moderator.html', **template_values)
    else:
        response = make_response(render_template('unauthorized.html'), 403)
        return response


@app.route('/publishMail', methods=['GET'])
@login_required
def publish_mail():
    current_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate != None).\
        order(Appointment.setdate)

    current_list = current_query.fetch(4)

    msg = NewsEmail()
    for appo in current_list:
        msg.add_pub(appo)

    msg.send()

    return redirect(url_for('main_page'))


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
    appo = ndb.Key(urlsafe=appid).get()

    if appo:
        c = Calendar()
        e = Event()

        e.name = "Nomaden im {}, {} ({})".format(appo.name, appo.street, appo.publictrans)
        e.begin = datetime.datetime.combine(appo.setdate, datetime.time(19))

        c.events.append(e)

        res = make_response(str(c))
        res.headers['Content-Type'] = 'text/calendar; charset=utf-8'
        return res


# woechentlicher cronjob
@app.route('/schedulePubs', methods=['GET'])
@login_required
def schedule_pubs():
    # wir haben drei gruppen

    # die fertig geplanten, feststehenden termine
    archive_query = Appointment.query(ancestor=appointments_key()).\
        filter(Appointment.setdate < datetime.date.today(),
               Appointment.setdate != None)

    archive_list = archive_query.fetch()

    for appo in archive_list:
        newapp = clone_entity(appo, parent=apparchive_key())
        for com in newapp.comments:
            com.source = None
        newapp.source = None
        newapp.put()

        appo.key.delete()

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

    for appo in current_list:
        if appo.setdate in fill_dates:
            del fill_dates[appo.setdate]

    # die einzufuegenden, die wir aus der warteliste ziehen

    klis = sorted(fill_dates.keys(), reverse=True)
    if len(klis) > 0:
        next_query = Appointment.query(ancestor=appointments_key()).\
            filter(Appointment.setdate == None)

        next_list = next_query.fetch(1)

        for dat in klis:
            if len(next_list) > 0:
                appo = next_list[0]
                appo.setdate = dat
                appo.put()

                next_list = next_query.fetch(1)

    return redirect(url_for('main_page'))
