#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This is the Go Redirector. It uses short mnemonics as redirects to otherwise
long URLs. Few remember how to write in cursive, most people don't remember
common phone numbers, and just about everyone needs a way around bookmarks.
"""

__author__ = "Saul Pwanson <saul@pwanson.com>"
__credits__ = "Bill Booth, Bryce Bockman, treebird, Sean Smith, layertwo"

import base64
import datetime
import os
import random
import string
import time
import urllib.request
import urllib.error
import urllib.parse
import configparser
import cherrypy
import jinja2

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from cp_sqlalchemy import SQLAlchemyTool, SQLAlchemyPlugin

from models import Base, RedirectList, RedirectLink, Edit


config = configparser.ConfigParser()
config.read('go.cfg')

cfg_fnDatabase = config.get('goconfig', 'cfg_fnDatabase')
cfg_urlFavicon = config.get('goconfig', 'cfg_urlFavicon')
cfg_hostname = config.get('goconfig', 'cfg_hostname')
cfg_port = config.getint('goconfig', 'cfg_port')
cfg_urlSSO = config.get('goconfig', 'cfg_urlSSO')
cfg_urlEditBase = "https://" + cfg_hostname
cfg_sslEnabled = False # default to False
try:
    cfg_sslEnabled = config.getboolean('goconfig', 'cfg_sslEnabled')
except:
    # just preventing from crashing if the cfg option doesn't exist since technically it's optional
    pass
cfg_sslCertificate = config.get('goconfig', 'cfg_sslCertificate')
cfg_sslPrivateKey = config.get('goconfig', 'cfg_sslPrivateKey')
cfg_contactEmail = config.get('goconfig', 'cfg_contactEmail')
cfg_contactName = config.get('goconfig', 'cfg_contactName')
cfg_customDocs = config.get('goconfig', 'cfg_customDocs')

class MyGlobals(object):
    def __init__(self):
        self.db_hnd = None

    def __repr__(self):
        return '%s(hnd=%s)' % (self.__class__.__name__, self.db_hnd)


    def set_handle(self, hnd):
        self.db_hnd = hnd

MYGLOBALS = MyGlobals()


class Error(Exception):
    """base error exception class for go, never raised"""
    pass


class InvalidKeyword(Error):
    """Error raised when a keyword fails the sanity check"""
    pass


def today():
    return datetime.date.today().toordinal()


def escapekeyword(kw):
    return urllib.parse.quote_plus(kw, safe="/")


def opacity(LL):
    """ goes from 1.0 (today) to 0.2 (a month ago)"""
    dt = (datetime.datetime.today() - LL.last_used)
    c = min(1, max(0.2, (30 - dt.days) / 30))
    return "%.02f" % c


def prettyday(d):
    if d < 10:
        return 'never'

    s = today() - d
    if s < 1:
        return 'today'
    elif s < 2:
        return 'yesterday'
    elif s < 60:
        return '%d days ago' % s
    else:
        return '%d months ago' % (s / 30)


def prettytime(t):
    if isinstance(t, (datetime.date, datetime.datetime)):
        t = time.mktime(t.timetuple())

    if t < 100000:
        return 'never'

    dt = time.time() - t
    if dt < 24*3600:
        return 'today'
    elif dt < 2 * 24*3600:
        return 'yesterday'
    elif dt < 60 * 24*3600:
        return '%d days ago' % (dt / (24 * 3600))
    else:
        return '%d months ago' % (dt / (30 * 24*3600))


sanechars = string.ascii_lowercase + string.digits + "-."


def sanitary(s):
    s = s.lower()
    for a in s[:-1]:
        if a not in sanechars:
            return None

    if s[-1] not in sanechars and s[-1] != "/":
        return None

    return s


def getCurrentEditableUrl():
    redurl = cfg_urlEditBase + cherrypy.request.path_info
    if cherrypy.request.query_string:
        redurl += "?" + cherrypy.request.query_string

    return redurl


def getCurrentEditableUrlQuoted():
    return urllib.parse.quote(getCurrentEditableUrl(), safe=":/")


def getSSOUsername(redirect=True):
    """
    If no SSO URL is specified then the 'testuser' is returned, otherwise returns an SSO username
    (or redirects to SSO to get it)
    :param redirect:
    :return: the SSO username
    """
    if cfg_urlSSO is None or cfg_urlSSO == 'None':
        return 'testuser'

    if cherrypy.request.base != cfg_urlEditBase:
        if not redirect:
            return None
        if redirect is True:
            redirect = getCurrentEditableUrl()
        elif redirect is False:
            raise cherrypy.HTTPRedirect(redirect)

    if "issosession" not in cherrypy.request.cookie:
        if not redirect:
            return None
        if redirect is True:
            redirect = cherrypy.url(qs=cherrypy.request.query_string)

        raise cherrypy.HTTPRedirect(cfg_urlSSO + urllib.parse.quote(redirect, safe=":/"))

    sso = urllib.parse.unquote(cherrypy.request.cookie["issosession"].value)
    session = list(map(base64.b64decode, string.split(sso, "-")))
    return session[0]






class Root:

    @property
    def db(self):
        return cherrypy.request.db

    def redirect(self, url, status=307):
        cherrypy.response.status = status
        cherrypy.response.headers["Location"] = url

    def undirect(self):
        raise cherrypy.HTTPRedirect(cherrypy.request.headers.get("Referer", "/"))

    def notfound(self, msg):
        return env.get_template("notfound.html").render(message=msg)

    def redirectIfNotFullHostname(self, scheme=None):
        if scheme is None:
            scheme = cherrypy.request.scheme

        # redirect to our full hostname to get the user's cookies
        if cherrypy.request.scheme != scheme or cherrypy.request.base.find(cfg_hostname) < 0:
            fqurl = scheme + "://" + cfg_hostname
            fqurl += cherrypy.request.path_info
            if cherrypy.request.query_string:
                fqurl += "?" + cherrypy.request.query_string
            raise cherrypy.HTTPRedirect(fqurl)


    @cherrypy.expose
    def robots_txt(self):
        # Specifically for the internal GSA
        return open("robots.txt").read()

    @cherrypy.expose
    def favicon_ico(self):
        cherrypy.response.headers["Cache-control"] = "max-age=172800"
        return self.redirect(cfg_urlFavicon, status=301)

    @cherrypy.expose
    def lucky(self):

        link = self.db.query(RedirectLink).order_by(func.random()).first()
        link.no_clicks += 1
        self.db.commit()

        return self.redirect(link.url)

    @cherrypy.expose
    def index(self, **kwargs):
        self.redirectIfNotFullHostname()

        top = self.db.query(RedirectLink).order_by(RedirectLink.no_clicks.desc()).limit(8).all()
        filter_after = datetime.datetime.today() - datetime.timedelta(days = 30)
        lists = self.db.query(RedirectList).filter(RedirectList.last_used).order_by(RedirectList.last_used > filter_after).all()
        specials = self.db.query(RedirectLink).filter_by(regex=True).limit(15).all()
        if 'keyword' in kwargs:
            return self.redirect("/" + kwargs['keyword'])

        return env.get_template('index.html').render(specials=specials, topLinks=top, allLists=lists, now=today())

    @cherrypy.expose
    def default(self, *rest, **kwargs):
        self.redirectIfNotFullHostname()

        keyword = rest[0]
        rest = rest[1:]

        show_list = False

        # force list page instead of redirect
        if keyword[0] == ".":
            if keyword == ".me":
                username = getSSOUsername()
                self.redirect("." + username)
            show_list = True
            keyword = keyword[1:]

        if rest:
            keyword += "/"
        elif show_list and cherrypy.request.path_info[-1] == "/":
            # allow go/keyword/ redirect to go/keyword
            # but go/.keyword/ goes to the keyword/ index
            keyword += "/"

        LL = self.db.query(RedirectList).filter_by(name=keyword).first()
        if LL:
            if show_list or LL.redirect == 'list':
                return env.get_template('list.html').render(L=LL, keyword=keyword, popularLinks=LL.links)
            else:
                if LL.redirect == 'top':
                    link = sorted(LL.links, key=lambda L: (-L.no_clicks))[0]
                elif LL.redirect == 'random':
                    link = random.choice([l for l in LL.links])
                elif LL.redirect == 'freshest':
                    # TODO validate created date, not index in list
                    link = LL.links[-1]
                # elif by link_id
                else:
                    # redirect to list if unknown mode
                    return env.get_template('list.html').render(L=LL, keyword=keyword, popularLinks=LL.links)

                if link.regex:
                    url = link.url.replace('{*}', rest[0])
                else:
                    url = link.url

                link.no_clicks += 1
                LL.last_used = datetime.datetime.utcnow()
                self.db.commit()

                self.redirect(url=url)
        else:
            return env.get_template('list.html').render(L=[], keyword=keyword, popularLinks=[])

    @cherrypy.expose
    def special(self):
        LL = self.db.query(RedirectLink).filter_by(regex=True).all()

        return env.get_template('list.html').render(L=LL, keyword="special")

    @cherrypy.expose
    def _login_(self, redirect=""):
        if redirect:
            return self.redirect(redirect)
        return self.undirect()

    @cherrypy.expose
    def me(self):
        return self.redirect(getSSOUsername())

    @cherrypy.expose
    def _link_(self, _id):
        link = self.db.query(RedirectLink).filter_by(id=_id).first()
        if link:
            link.no_clicks += 1
            self.db.commit()
            return self.redirect(link.url, status=301)

        cherrypy.response.status = 404
        return self.notfound("RedirectLink %s does not exist" % _id)

    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        # _add_?ll=tag1
        _ll = kwargs.get('ll', '')

        LL = self.db.query(RedirectList).filter_by(name=_ll).all()
        if LL:
            return env.get_template("editlink.html").render(L=[], lists=[l.__dict__ for l in LL], returnto=_ll, **kwargs)

        else:
            return env.get_template("editlink.html").render(L=[], lists=[{'name': _ll}], returnto=_ll, **kwargs)

    @cherrypy.expose
    def _edit_(self, _id, **kwargs):
        link = self.db.query(RedirectLink).filter_by(id=_id).first()

        if link:
            return env.get_template("editlink.html").render(L=link, lists=link.lists, **kwargs)

        # edit new link
        # TODO redirect to _add_
        return env.get_template("editlink.html").render(L=[], **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        LL = self.db.query(RedirectList).filter_by(name=keyword).first()
        return env.get_template("list.html").render(L=LL, keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        LL = self.db.query(RedirectList).filter_by(name=keyword).first()
        if LL:
            if 'behavior' in kwargs:
                LL.mode = kwargs.get('behavior', 'freshest')

        return self.redirect("/." + keyword)

    @cherrypy.expose
    def _delete_(self, _id, returnto=""):

        try:
            self.db.query(RedirectLink).filter_by(id=_id).delete()
            self.db.commit()
        except IntegrityError:
            cherrypy.log('Unable to delete RedirectLink with ID {}'.format(_id))

        return self.redirect("/." + returnto)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def _modify_(self, **kwargs):

        title = kwargs.get('title', '')
        url = ''.join(kwargs.get('url', '').split())

        if title and url:

            link = self.db.query(RedirectLink).filter_by(id=kwargs.get('linkid', 0)).first()
            if not link:
                link = RedirectLink()

            if '{*}' in url:
                link.regex = True

            link.title = title
            link.url = url

            link.lists.clear()

            otherlists = list(set(kwargs.get('otherlists', []).split()))
            otherlists.append(kwargs.get('lists', []))

            for l in otherlists:
                if link.regex and not l.endswith('/'):
                    l += '/'

                LL = self.db.query(RedirectList).filter_by(name=l).first()

                if not LL:
                    LL = RedirectList(name=l)

                LL.links.append(link)
                self.db.add(LL)

            self.db.add(link)
            self.db.flush()

            edit = Edit(link_id=link.id,
                        editor=getSSOUsername())
            self.db.add(edit)

            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                cherrypy.log("unable to commit to database", traceback=True)
                return self._edit_(link.id, **kwargs)

        return self.redirect("/." + kwargs.get("returnto", ""))

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n=100):
        topLinks = self.db.query(RedirectLink).order_by(RedirectLink.no_clicks.desc())[:n]
        return env.get_template("toplinks.html").render(topLinks=topLinks, n=n)

    @cherrypy.expose
    def variables(self):
        return env.get_template("variables.html").render()

    @cherrypy.expose
    def help(self):
        link = self.db.query(RedirectLink).order_by(func.random()).first()
        return env.get_template("help.html").render(link=link)

    @cherrypy.expose
    def _override_vars_(self, **kwargs):
        cherrypy.response.cookie["variables"] = urllib.parse.urlencode(kwargs)
        cherrypy.response.cookie["variables"]["max-age"] = 10 * 365 * 24 * 3600

        return self.redirect("variables")

    @cherrypy.expose
    def _set_variable_(self, varname="", value=""):

        return self.redirect("/variables")


def main():

    cherrypy.tools.db = SQLAlchemyTool()

    cherrypy.config.update({'server.socket_host': '::',
                            'server.socket_port': cfg_port,
                            'request.query_string_encoding': "latin1",
                            })

    cherrypy.https = s = cherrypy._cpserver.Server()
    if cfg_sslEnabled:
        s.socket_host = '::'
        s.socket_port = 443
        s.ssl_certificate = cfg_sslCertificate
        s.ssl_private_key = cfg_sslPrivateKey
        s.subscribe()

    file_path = os.getcwd().replace("\\", "/")
    conf = {'/css': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/static/css"},
            '/js': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/static/js"},
            '/': {'tools.db.on': True,
                  'tools.sessions.on': True}
           }

    print("Cherrypy conf: %s" % conf)

    cherrypy.tree.mount(Root(), "/", config=conf)

    dbfile = os.path.join(file_path, 'f5go.db')
    sqlalchemy_plugin = SQLAlchemyPlugin(cherrypy.engine, Base, 'sqlite:///%s' % (dbfile), echo=True)
    sqlalchemy_plugin.subscribe()
    sqlalchemy_plugin.create()
    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":

    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./templates/"))
    env.filters['time_t'] = prettytime
    env.filters['int'] = int
    env.filters['escapekeyword'] = escapekeyword

    env.globals["enumerate"] = enumerate
    env.globals["sample"] = random.sample
    env.globals["len"] = len
    env.globals["min"] = min
    env.globals["str"] = str
    env.globals.update(globals())
    main()
