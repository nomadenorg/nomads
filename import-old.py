from nomads_pb2 import AppoinmentList, Appointment
from datetime import datetime
import requests
import re


# this is a simple scraping script for the archived appointments
# from the old nomaden.org site


def scrape_url(url, cb):  
    r = requests.get(url)

    if r.status_code == requests.codes.ok:
        r.encoding = 'utf-8'
        txt = r.text

        for line in txt.split('\n'):
            m = re.match(ur'^([0-9]{2}\.[0-9]{2}\.[0-9]{4}, .*)<BR>$',
                         line)
            if m:
                res = m.group(1)

                dat, name, addr = res.split(',', 2)

                name = name.lstrip()
                addr = addr.lstrip()
                
                cb(dat.encode('utf-8'),
                   name.encode('utf-8'),
                   addr.encode('utf-8'))


applis = AppoinmentList()


def convert_date(datum):
    return datetime.strptime(datum, "%d.%m.%Y").isoformat()


def put_appointment(datum, name, addr):
    app = Appointment()
    app.name = name
    app.street = addr
    app.setdate = convert_date(datum)
    app.source = "import"
    applis.apps.extend([ app ])


def import_old():
    scrape_url("http://www.nomaden.org/cgi-bin/termine/olddates.cgi",
               put_appointment)

    with open("archive.pb", "wb") as f:
        f.write(applis.SerializeToString())
    f.close()


if __name__ == "__main__":
    import_old()
