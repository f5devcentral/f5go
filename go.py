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
import re
import string
import time
import urllib.request
import urllib.error
import urllib.parse
import configparser
import cherrypy
import jinja2
import html
from pprint import pprint

from sqlalchemy import Column, Integer, String, DateTime, Table, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import IntegrityError

from cp_sqlalchemy import SQLAlchemyTool, SQLAlchemyPlugin

Base = declarative_base()


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


def deampify(s):
    """Replace '&amp;'' with '&'."""
    return s.replace("&amp;", "&")


def escapeascii(s):
    return html.escape(s).encode("ascii", "xmlcharrefreplace")


def randomLink(LL):
    return random.choice([l for l in LL.links])


def popularLink(LL):
    return sorted(LL.links, key=lambda L: (-L.no_clicks))[0]


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


def makeList(s):
    if isinstance(s, str):
        return [s]
    elif isinstance(s, list):
        return s
    else:
        return list(s)


def canonicalUrl(url):
    if url:
        m = re.search(r'href="(.*)"', jinja2.utils.urlize(url))
        if m:
            return m.group(1)

    return url


def getDictFromCookie(cookiename):
    if cookiename not in cherrypy.request.cookie:
        return {}

    return dict(urllib.parse.parse_qsl(cherrypy.request.cookie[cookiename].value))


sanechars = string.ascii_lowercase + string.digits + "-."


def sanitary(s):
    s = s.lower()
    for a in s[:-1]:
        if a not in sanechars:
            return None

    if s[-1] not in sanechars and s[-1] != "/":
        return None

    return s


def byClicks(links):
    return sorted(links, key=lambda L: (-L.recentClicks, -L.totalClicks))


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


association_table = Table('association', Base.metadata,
                          Column('list_id', Integer, ForeignKey('listoflinks.id')),
                          Column('link_id', Integer, ForeignKey('links.id')))


class ListOfLinks(Base):
    __tablename__ = 'listoflinks'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    mode = Column(String, nullable=False, default='freshest')
    last_used = Column(DateTime)
    links = relationship('Link', back_populates="lists", secondary=association_table)


class Link(Base):
    __tablename__ = 'links'
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    no_clicks = Column(Integer, default=0)
    last_used = Column(DateTime)

    # 1 to many
#    edits = relationship('Edit')
    # many to many
    lists = relationship('ListOfLinks', back_populates='links', secondary=association_table)


class Edit(Base):
    __tablename__ = 'edits'
    id = Column(Integer, primary_key=True)
    editor = Column(String)
    timestamp = Column(DateTime)


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

    def redirectToEditLink(self, **kwargs):
        if "linkid" in kwargs:
            url = "/_edit_/%s" % kwargs["linkid"]
            del kwargs["linkid"]
        else:
            url = "/_add_"

        return self.redirect(url + "?" + urllib.parse.urlencode(kwargs))

    def redirectToEditList(self, listname, **kwargs):
        baseurl = "/_editlist_/%s?" % escapekeyword(listname)
        return self.redirect(baseurl + urllib.parse.urlencode(kwargs))

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

        link = self.db.query(Link).order_by(func.random()).first()
        link.no_clicks += 1
        link.last_used = datetime.datetime.utcnow()
        self.db.commit()

        return self.redirect(deampify(link.url))

    @cherrypy.expose
    def index(self, **kwargs):
        self.redirectIfNotFullHostname()

        topLinks = self.db.query(Link).order_by(Link.no_clicks.desc()).limit(10).all()
        filter_after = datetime.datetime.today() - datetime.timedelta(days = 30)
        allLists = self.db.query(ListOfLinks).filter(ListOfLinks.last_used).order_by(ListOfLinks.last_used > filter_after).all()
        if 'keyword' in kwargs:
            return self.redirect("/" + kwargs['keyword'])

        return env.get_template('index.html').render(folderLinks=[], topLinks=topLinks, allLists=allLists, now=today())

    @cherrypy.expose
    def default(self, *rest, **kwargs):
        self.redirectIfNotFullHostname()

        keyword = rest[0]
        rest = rest[1:]

        forceListDisplay = False

        if keyword[0] == ".":  # force list page instead of redirect
            if keyword == ".me":
                username = getSSOUsername()
                self.redirect("." + username)
            forceListDisplay = True
            keyword = keyword[1:]

        if rest:
            keyword += "/"
        elif forceListDisplay and cherrypy.request.path_info[-1] == "/":
            # allow go/keyword/ to redirect to go/keyword but go/.keyword/
            #  to go to the keyword/ index
            keyword += "/"

        LL = self.db.query(ListOfLinks).filter_by(name=keyword).first()
        if LL:
            if forceListDisplay or LL.mode == 'list':
                return env.get_template('list.html').render(L=LL, keyword=keyword, popularLinks=LL.links)
            else:
                if LL.mode == 'top':
                    link = popularLink(LL)
                elif LL.mode == 'random':
                    link = randomLink(LL)
                elif LL.mode == 'freshest':
                    link = LL.links[-1]
                else:
                    # redirect to list if unknown mode
                    return env.get_template('list.html').render(L=LL, keyword=keyword, popularLinks=LL.links)

                now = datetime.datetime.utcnow()
                link.no_clicks += 1
                link.last_used = now
                LL.last_used = now
                self.db.commit()

                self.redirect(url=link.url)
        else:
            return env.get_template('list.html').render(L=[], keyword=keyword, popularLinks=[])

    @cherrypy.expose
    def special(self):
        LL = {}
        LL['name'] = "Smart Keywords"

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
        link = self.db.query(Link).filter_by(id=_id).first()
        if link:
            link.no_clicks += 1
            self.db.commit()
            return self.redirect(link.url, status=301)

        cherrypy.response.status = 404
        return self.notfound("Link %s does not exist" % _id)

    @cherrypy.expose
   # @cherrypy.tools.allow(methods=['GET','POST'])
    def _add_(self, *args, **kwargs):
        # _add_?ll=tag1
        _ll = kwargs.get('ll', '')

        LL = self.db.query(ListOfLinks).filter_by(name=_ll).all()
        if LL:
            return env.get_template("editlink.html").render(L=[], lists=[l.__dict__ for l in LL], returnto=_ll, **kwargs)

        else:
            return env.get_template("editlink.html").render(L=[], lists=[{'name': _ll}], returnto=_ll, **kwargs)

    @cherrypy.expose
    def _edit_(self, _id, **kwargs):
        link = self.db.query(Link).filter_by(id=_id).first()

        if link:
            return env.get_template("editlink.html").render(L=link, lists=link.lists, **kwargs)

        # edit new link
        # TODO redirect to _add_
        return env.get_template("editlink.html").render(L=[], **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        LL = self.db.query(ListOfLinks).filter_by(name=keyword).first()
        return env.get_template("list.html").render(L=LL, keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        LL = self.db.query(ListOfLinks).filter_by(name=keyword).first()
        if LL:
            if 'behavior' in kwargs:
                LL.mode = kwargs['behavior']

        return self.redirect("/." + keyword)

    @cherrypy.expose
    def _delete_(self, _id, returnto=""):

        try:
            self.db.query(Link).filter_by(id=_id).delete()
            self.db.commit()
        except IntegrityError:
            print('Unable to delete Link with ID {}'.format(_id))

        return self.redirect("/." + returnto)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def _modify_(self, **kwargs):

        title = kwargs.get('title', '')
        url = ''.join(kwargs.get('url', '').split())
        otherlists = list(set(kwargs.get('otherlists', []).split()))

        if title and url:

            link = self.db.query(Link).filter_by(id=kwargs.get('linkid', 0)).first()
            if not link:
                link = Link()

            link.title = title
            link.url = url
            otherlists.append(kwargs.get('lists', []))

            for l in otherlists:
                pprint(l)
                LL = self.db.query(ListOfLinks).filter_by(name=l).first()

                if not LL:
                    LL = ListOfLinks(name=l)

                LL.links.append(link)
                self.db.add(LL)

            self.db.add(link)

            try:
                self.db.commit()
            except IntegrityError as e:
                self.db.rollback()
                return self.redirectToEditLink(error=e, **kwargs)


        return self.redirect("/." + kwargs.get("returnto", ""))

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n=100):
        topLinks = self.db.query(Link).order_by(Link.no_clicks.desc())[:n]
        return env.get_template("toplinks.html").render(topLinks=topLinks, n=n)

    @cherrypy.expose
    def variables(self):
        return env.get_template("variables.html").render()

    @cherrypy.expose
    def help(self):
        return env.get_template("help.html").render()

    @cherrypy.expose
    def _override_vars_(self, **kwargs):
        cherrypy.response.cookie["variables"] = urllib.parse.urlencode(kwargs)
        cherrypy.response.cookie["variables"]["max-age"] = 10 * 365 * 24 * 3600

        return self.redirect("variables")

    @cherrypy.expose
    def _set_variable_(self, varname="", value=""):

        return self.redirect("/variables")


env = jinja2.Environment(loader=jinja2.FileSystemLoader("./html"))


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
    conf = {'/images': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/images"},
            '/css': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/css"},
            '/js': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/js"},
            '/': {'tools.db.on': True}}
    print("Cherrypy conf: %s" % conf)

    cherrypy.tree.mount(Root(), "/", config=conf)

    dbfile = os.path.join(file_path, 'f5go.db')
    if not os.path.exists(dbfile):
        open(dbfile, 'w+').close()

    sqlalchemy_plugin = SQLAlchemyPlugin(cherrypy.engine, Base, 'sqlite:///%s' % (dbfile), echo=True)
    sqlalchemy_plugin.subscribe()
    sqlalchemy_plugin.create()
    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":

    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./html"))
    env.filters['time_t'] = prettytime
    env.filters['int'] = int
    env.filters['escapekeyword'] = escapekeyword

    env.globals["enumerate"] = enumerate
    env.globals["sample"] = random.sample
    env.globals["len"] = len
    env.globals["min"] = min
    env.globals["str"] = str
    env.globals["list"] = makeList
    env.globals.update(globals())
    main()
