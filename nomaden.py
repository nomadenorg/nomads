import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, render_template, request, redirect, url_for,\
    make_response, g as flask_g

from flask_login import LoginManager, current_user, login_required,\
    login_user, logout_user

from hashlib import pbkdf2_hmac
from binascii import unhexlify

from smtplib import SMTP
from email.mime.text import MIMEText

import datetime
import pytz
import dateutil.parser
import re
import os.path
import fcntl
from uuid import uuid4 as uuid

from ics import Calendar, Event
from nomads_pb2 import AppoinmentList as PBAppointmentList,\
    Appointment as PBAppointment

import ConfigParser


# config

config = ConfigParser.ConfigParser()
config.read('nomaden.cfg')


# flask app & login manager

app = Flask(__name__, static_folder='assets', static_url_path='/assets')
login_manager = LoginManager()
login_manager.init_app(app)
app.secret_key = config.get("app", "secret", 0)


# gunicorn logging

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)


# model layer


class StorageHelper():

    archive = None
    schedule = None

    def __init__(self):
        pass

    def get_scheduled(self):
        scheduled = getattr(flask_g, 'scheduled_apps', None)
        if not scheduled:
            scheduled = PBAppointmentList()
            if os.path.isfile("schedule.pb"):
                with open("schedule.pb", "rb") as f:
                    fcntl.lockf(f, fcntl.LOCK_SH)
                    scheduled.ParseFromString(f.read())
                f.close()
        flask_g.scheduled_apps = scheduled
        return scheduled

    def get_archived(self):
        archived = getattr(flask_g, 'archived_apps', None)
        if not archived:
            archived = PBAppointmentList()
            if os.path.isfile("archive.pb"):
                with open("archive.pb", "rb") as f:
                    fcntl.lockf(f, fcntl.LOCK_SH)
                    archived.ParseFromString(f.read())
                f.close()
        flask_g.archived_apps = archived
        return archived

    def save(self):
        scheduled = getattr(flask_g, 'scheduled_apps', None)
        if scheduled:
            with open("schedule.pb", "wb") as f:
                fcntl.lockf(f, fcntl.LOCK_EX)
                f.write(scheduled.SerializeToString())
            f.close()

        archived = getattr(flask_g, 'archived_apps', None)
        if archived:
            with open("archive.pb", "wb") as f:
                fcntl.lockf(f, fcntl.LOCK_EX)
                f.write(archived.SerializeToString())
            f.close()


storage_helper = StorageHelper()


class Appointment():

    entered = None
    setdate = None
    removed = None

    def __init__(self, pbapp, index):
        self.sortorder = index + 1
        self.pbapp = pbapp

        self.id = self.pbapp.id
        self.name = self.pbapp.name
        self.street = self.pbapp.street
        self.city = self.pbapp.city
        self.publictrans = self.pbapp.publictrans
        self.source = self.pbapp.source

        if self.pbapp.entered != '':
            self.entered = dateutil.parser.parse(self.pbapp.entered).date()

        if self.pbapp.setdate != '':
            self.setdate = dateutil.parser.parse(self.pbapp.setdate).date()

        if self.pbapp.removed != '':
            self.removed = dateutil.parser.parse(self.pbapp.removed).date()

        self.comments = self.pbapp.comments

    # return a url safe id
    def get_id(self):
        return self.pbapp.id

    def put(self, save=True):
        self.pbapp.name = self.name
        self.pbapp.street = self.street
        self.pbapp.city = self.city
        self.pbapp.publictrans = self.publictrans
        self.pbapp.source = self.source

        if self.entered:
            self.pbapp.entered = self.entered.isoformat()
        if self.setdate:
            self.pbapp.setdate = self.setdate.isoformat()
        if self.removed:
            self.pbapp.removed = self.removed.isoformat()

        self.pbapp.id = self.id

        app.logger.info('putting {}'.format(self.pbapp))
        if save:
            storage_helper.save()

    # fetch an appointment by a url safe id
    @classmethod
    def by_id(cls, appid):
        pbapps = storage_helper.get_scheduled()
        for pbapp in pbapps.apps:
            if pbapp.id == appid:
                return Appointment(pbapp, 0)

    # get currently scheduled pubs
    @classmethod
    def get_current(cls):
        return [Appointment(x, idx) for idx, x in enumerate(storage_helper.get_scheduled().apps)
                if x.setdate != '']

    # get waiting list
    @classmethod
    def get_waiting(cls):
        return [Appointment(x, idx) for idx, x in enumerate(storage_helper.get_scheduled().apps)
                if x.setdate == '']

    # get archived appointments
    @classmethod
    def get_archive(cls):
        return sorted([Appointment(x, idx) for idx, x in enumerate(storage_helper.get_archived().apps)], key=lambda appo: appo.setdate, reverse=True)

    @classmethod
    def append_pub(cls):
        sched = storage_helper.get_scheduled()

        pbapp = PBAppointment()

        pbapp.id = str(uuid())
        sched.apps.extend([pbapp])

        return Appointment(sched.apps[-1], len(sched.apps))

    def __eq__(self, other): 
        return self.id == other.id

    # archive this appointment
    def archive(self):
        sched = storage_helper.get_scheduled()
        archi = storage_helper.get_archived()

        if self.pbapp in sched.apps:
            sched.apps.remove(self.pbapp)
            pbapp = PBAppointment()
            pbapp.CopyFrom(self.pbapp)
            archi.apps.extend([pbapp])

            storage_helper.save()

    def delete(self):
        sched = storage_helper.get_scheduled()
        sched.apps.remove(self.pbapp)
        storage_helper.save()
        app.logger.info("pub deleted key={}".format(self.id))

    def move_forward(self):
        if self.setdate is not None:
            app.logger.info('cannot move direction=forward id={}'.format(self.id))
            return
        sched = storage_helper.get_scheduled()
        for idx, item in enumerate(sched.apps):
            if item.id == self.id:
                index = idx

        if index > 0:
            tmp = PBAppointment()
            tmp.CopyFrom(sched.apps[index-1])
            sched.apps[index-1].CopyFrom(self.pbapp)
            sched.apps[index].CopyFrom(tmp)

            app.logger.info('pub moved direction=forward id={}'.format(self.id))

            storage_helper.save()
        else:
            app.logger.info('already first move direction=forward id={}'.format(self.id))

    def move_backward(self):
        if self.setdate is not None:
            app.logger.info('cannot move direction=backward id={}'.format(self.id))
            return
        sched = storage_helper.get_scheduled()
        for idx, item in enumerate(sched.apps):
            if item.id == self.id:
                index = idx

        if index + 1 < len(sched.apps):
            app.logger.info("exchanging {} for {}".format(sched.apps[index], sched.apps[index+1]))
            tmp = PBAppointment()
            tmp.CopyFrom(sched.apps[index+1])
            sched.apps[index+1].CopyFrom(sched.apps[index])
            sched.apps[index].CopyFrom(tmp)

            app.logger.info('pub moved direction=backward id={}'.format(self.id))

            storage_helper.save()
        else:
            app.logger.info('already last move direction=backward id={}'.format(self.id))

    def is_first(self):
        apps = Appointment.get_waiting()
        return self.id == apps[0].id

    def is_last(self):
        apps = Appointment.get_waiting()
        return self.id == apps[-1].id

    def is_fix(self):
        return self.setdate is not None


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
    fixed_list = Appointment.get_current()

    wait_list = Appointment.get_waiting()

    current_username = "not logged in"
    if current_user.is_active:
        current_username = current_user.get_id()

    loginout_text = "Login"
    loginout_url = url_for('login')

    if current_user.is_active:
        loginout_text = "Logout"
        loginout_url = url_for('logout')

    return render_template('index.html',
                           username=current_username,
                           fixed_apps=fixed_list,
                           wait_apps=wait_list,
                           loginout_url=loginout_url,
                           loginout_text=loginout_text,
                           current_user=current_user)


@app.errorhandler(500)
def application_error(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500

@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

@app.route('/archive', methods=['GET'])
def archive():
    archive_list = Appointment.get_archive()

    template_values = {'archive_apps': archive_list}

    return render_template('archive.html', **template_values)

@app.route('/enterPub', methods=['GET'])
def enter_pub_display():
    template_values = {'current_user': current_user}
    
    return render_template('enterpub.html', **template_values)

@app.route('/enterPub', methods=['POST'])
def enter_pub():
    appo = Appointment.append_pub()

    appo.name = request.form['name']
    appo.street = request.form['street']
    appo.city = request.form['city']
    appo.publictrans = request.form['publictrans']

    appo.source = generate_source(request)

    if request.form['magic'] == '4':
        appo.put()

        app.logger.info("pub entered")
    else:
        app.logger.info("/enterPub wrong magic")

    return redirect(url_for('main_page'))


@app.route('/comment', methods=['POST'])
def comment():
    appid = request.form['id']
    uname = request.form['author']
    text = request.form['text']
    magic = request.form['magic']

    appo = Appointment.by_id(appid)

    if appo and magic == "4":
        com = PBAppointment.Comment()
        com.uname = uname
        com.text = text

        com.source = generate_source(request)

        appo.comments.extend([com])

        appo.put()

        app.logger.info('comment entered on pub id={}'.format(appid))

    return redirect(url_for('main_page'))


@app.route('/move', methods=['GET'])
def move_pub():
    appid = request.args['id']

    app = Appointment.by_id(appid)
    
    direction = 'forward'
    if 'direction' in request.args:
        direction = request.args['direction']

    if direction == "forward":
        app.move_forward()
    else:
        app.move_backward()

    return redirect(url_for('main_page'))


@app.route('/delete', methods=['GET'])
@login_required
def delete():
    if current_user.is_active:
        appid = request.args.get('id')
        appo = Appointment.by_id(appid)

        if appo:
            appo.delete()

    return redirect(url_for('main_page'))


@app.route('/publishMail', methods=['GET'])
def publish_mail():
    if current_user.is_authenticated or\
       request.args.get('token') == config.get('app', 'crontoken', 0):
        current_list = Appointment.get_current()

        msg = NewsEmail()
        for appo in current_list:
            msg.add_pub(appo)
        msg.send()
    else:
        app.logger.info("unauthorized publishMail")  

    return redirect(url_for('main_page'))


@app.route('/poster', methods=['GET'])
def poster():
    current_list = Appointment.get_current()

    template_values = {
        'pubs': current_list, }

    return render_template('poster.html', **template_values)

def get_event(appo):
    e = Event()

    tz = pytz.timezone('Europe/Berlin')
    e.name = u'Nomaden im {}'.format(appo.name, appo.street)
    e.description = u'Nomaden in der Kneipe {}. Adresse: {} {}. HVV: {}'.format(appo.name, appo.street, appo.city,
                                                                                appo.publictrans)
    e.location = u'{}, {}'.format(appo.city, appo.street)
    e.begin = datetime.datetime.combine(appo.setdate, datetime.time(19, tzinfo=tz))
    e.end = datetime.datetime.combine(appo.setdate, datetime.time(23, tzinfo=tz))

    return e

@app.route('/calendarEntry', methods=['GET'])
def calendar_entry():
    appid = request.args.get('id')
    appo = Appointment.by_id(appid)

    if appo:
        c = Calendar()
        e = get_event(appo)

        c.events.append(e)

        res = make_response(str(c))
        res.headers['Content-Type'] = 'text/calendar; charset=utf-8'
        res.headers['Content-Disposition'] = 'attachment; filename="nomaden.ics"'

        return res


@app.route('/calendar', methods=['GET'])
def calendar():
    apps = Appointment.get_current()

    if len(apps) > 0:
        c = Calendar()

        for appo in apps:
            e = get_event(appo)
            c.events.append(e)

        res = make_response(str(c))
        res.headers['Content-Type'] = 'text/calendar; charset=utf-8'
        res.headers['Content-Disposition'] = 'attachment; filename="nomaden.ics"'
        return res


# woechentlicher cronjob
@app.route('/schedulePubs', methods=['GET'])
def schedule_pubs():
    if not (current_user.is_authenticated or\
       request.args.get('token') == config.get('app', 'crontoken', 0)):
        app.logger.info("unauthorized schedulePubs")
        return redirect(url_for('main_page'))

    # wir haben drei gruppen

    # die fertig geplanten, feststehenden termine
    current_list = Appointment.get_current()

    archive_list = [ap for ap in current_list
                    if ap.setdate < datetime.date.today()]

    for appo in archive_list:
        appo.archive()

    # die aktuellen, also schon geplanten
    current_list = [ap for ap in current_list
                    if ap.setdate > datetime.date.today()]

    fill_dates = {}
    last_date = previous_tuesday()

    for i in range(4):
        last_date = next_tuesday(last_date)
        fill_dates[last_date] = 1
        app.logger.info("scheduling {}".format(last_date))

    for appo in current_list:
        if appo.setdate in fill_dates:
            del fill_dates[appo.setdate]

    # die einzufuegenden, die wir aus der warteliste ziehen

    klis = sorted(fill_dates.keys())
    if len(klis) > 0:
        waiting = Appointment.get_waiting()

        appo = None
        if len(waiting) > 0:
            appo = waiting.pop(0)

        for dat in klis:
            if appo is not None:
                appo.setdate = dat
                appo.put(save=False)

                if len(waiting) > 0:
                    appo = waiting.pop(0)
                else:
                    appo = None
        storage_helper.save()

    return redirect(url_for('main_page'))

if __name__ == "__main__":
    # initialize the log handler
    log_handler = RotatingFileHandler(config.get('app', 'logpath', 0), maxBytes=10000, backupCount=1)
    
    # set the log handler level
    log_handler.setLevel(logging.INFO)

    # set the app logger level
    app.logger.setLevel(logging.INFO)

    app.logger.addHandler(log_handler)    
    app.run()
