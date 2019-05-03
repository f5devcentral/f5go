#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This is the Go Redirector. It uses short mnemonics as redirects to otherwise
long URLs. Few remember how to write in cursive, most people don't remember
common phone numbers, and just about everyone needs a way around bookmarks.
"""

__author__ = "Saul Pwanson <saul@pwanson.com>"
__credits__ = "Bill Booth, Bryce Bockman, treebird, Sean Smith, layertwo"

import datetime
import os
import random
import string
import time
import urllib.request
import urllib.error
import urllib.parse
import cherrypy
import jinja2

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from cp_sqlalchemy import SQLAlchemyTool, SQLAlchemyPlugin

from config import get_config
from models import Base, RedirectList, RedirectLink, Edit

env = jinja2.Environment(loader=jinja2.FileSystemLoader("./templates/"))


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

    if s < 2:
        return 'yesterday'

    if s < 60:
        return '%d days ago' % s

    return '%d months ago' % (s / 30)


def prettytime(t):
    if isinstance(t, (datetime.date, datetime.datetime)):
        t = time.mktime(t.timetuple())

    if t < 100000:
        return 'never'

    dt = time.time() - t
    if dt < 24*3600:
        return 'today'

    if dt < 2 * 24*3600:
        return 'yesterday'

    if dt < 60 * 24*3600:
        return '%d days ago' % (dt / (24 * 3600))

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
    redurl = cherrypy.request.path_info
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
   # if cfg_urlSSO is None or cfg_urlSSO == 'None':
    return 'testuser'

   # if cherrypy.request.base != cfg_urlEditBase:
   #     if not redirect:
   #         return None
   #     if redirect is True:
   #         redirect = getCurrentEditableUrl()
   #     elif redirect is False:
   #         raise cherrypy.HTTPRedirect(redirect)

   # if "issosession" not in cherrypy.request.cookie:
   #     if not redirect:
   #         return None
   #     if redirect is True:
   #         redirect = cherrypy.url(qs=cherrypy.request.query_string)

   #     raise cherrypy.HTTPRedirect(cfg_urlSSO + urllib.parse.quote(redirect, safe=":/"))

   # sso = urllib.parse.unquote(cherrypy.request.cookie["issosession"].value)
   # session = list(map(base64.b64decode, sso.split("-")))
   # return session[0]


class Root:

    @property
    def db(self):
        return cherrypy.request.db

    def redirect(self, url, status=307):
        cherrypy.response.status = status
        cherrypy.response.headers["Location"] = url

    def undirect(self):
        raise cherrypy.HTTPRedirect(cherrypy.request.headers.get("Referer", "/"))

    @cherrypy.expose
    def robots_txt(self):
        # Specifically for the internal GSA
        if os.path.exists('robots.txt'):
            return open("robots.txt").read()
        return ''

    @cherrypy.expose
    def lucky(self):

        link = self.db.query(RedirectLink).order_by(func.random()).first()
        link.no_clicks += 1
        self.db.commit()

        return self.redirect(link.url)

    @cherrypy.expose
    def index(self, **kwargs):

        if 'keyword' in kwargs:
            return self.redirect("/" + kwargs['keyword'])

        top = self.db.query(RedirectLink).order_by(RedirectLink.no_clicks.desc()).limit(8).all()
        filter_after = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        lists = self.db.query(RedirectList).filter(RedirectList.last_used > filter_after).order_by(RedirectList.last_used).all()
        specials = self.db.query(RedirectLink).filter_by(regex=True).limit(15).all()

        return env.get_template('index.html').render(specials=specials, topLinks=top, allLists=lists, now=today())

    @cherrypy.expose
    def default(self, *rest, **kwargs):

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

            if LL.redirect == 'top':
                link = sorted(LL.links, key=lambda L: (-L.no_clicks))[0]
            elif LL.redirect == 'random':
                link = random.choice([l for l in LL.links])
            elif LL.redirect == 'freshest':
                # TODO validate created date, not index in list
                link = LL.links[-1]
            else:
                link = self.db.query(RedirectLink).filter_by(id=LL.redirect).first()
                if not link:
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

        return env.get_template('list.html').render(L=[], keyword=keyword, popularLinks=[])

    @cherrypy.expose
    def special(self):
        LL = self.db.query(RedirectLink).filter_by(regex=True).all()

        return env.get_template('list.html').render(L=LL, keyword="special", popularLinks=LL)

    @cherrypy.expose
    def _login_(self, redirect=""):
        if redirect:
            return self.redirect(redirect)
        return self.undirect()

    @cherrypy.expose
    def me(self):
        return self.redirect(getSSOUsername())


    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        # _add_?ll=tag1
        _ll = kwargs.get('ll', '')

        LL = self.db.query(RedirectList).filter_by(name=_ll).all()
        if LL:
            return env.get_template("editlink.html").render(L=[], lists=[l.__dict__ for l in LL], returnto=_ll, **kwargs)

        return env.get_template("editlink.html").render(L=[], lists=[{'name': _ll}], returnto=_ll, **kwargs)

    @cherrypy.expose
    def _edit_(self, _id, **kwargs):

        link = self.db.query(RedirectLink).filter_by(id=_id).first()

        if link:
            return env.get_template("editlink.html").render(L=link, lists=link.lists, **kwargs)

        # edit new link
        # TODO redirect to _add_
        return env.get_template("editlink.html").render(L=[], error=error, **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword):
        LL = self.db.query(RedirectList).filter_by(name=keyword).first()
        return env.get_template("list.html").render(L=LL, keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        LL = self.db.query(RedirectList).filter_by(name=keyword).first()
        if LL:
            LL.redirect = kwargs.get('behavior')
            self.db.add(LL)
            self.db.commit()

        return self.redirect("/." + keyword)

    @cherrypy.expose
    # TODO use CRUD methods in rewrite
    @cherrypy.tools.allow(methods=['POST'])
    def _delete_(self, _id, returnto=""):

        link = self.db.query(RedirectLink).filter_by(id=_id).first()

        if link:
            self.db.delete(link)
            try:
                self.db.commit()
            except IntegrityError:
                cherrypy.log('Unable to delete RedirectLink with ID {}'.format(_id))

        return self.redirect("/." + returnto)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def _modify_(self, **kwargs):

        title = kwargs.get('title', '')
        url = ''.join(kwargs.get('url', '').split())
        cherrypy.log(kwargs.get('returnto', ''))
        lists = [kwargs.get('lists', [])]
        lists.extend([set(kwargs.get('otherlists', []).split())])

        if title and url:
            link = self.db.query(RedirectLink).filter_by(url=url).first()
            if link:
                return self._edit_(error='Link found with duplicate URL', _id=link.id)

            if kwargs.get('linkid', ''):
                link = self.db.query(RedirectLink).filter_by(id=kwargs['linkid']).first()
            else:
                link = RedirectLink()

            if '{*}' in url:
                link.regex = True

            link.title = title
            link.url = url

            link.lists.clear()


            for l in lists:
                if link.regex and not l.endswith('/'):
                    l += '/'

                LL = self.db.query(RedirectList).filter_by(name=l).first()

                if not LL:
                    LL = RedirectList(name=l)

                LL.links.append(link)
                self.db.add(LL)

            self.db.add(link)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                cherrypy.log("IntegrityError, unable to commit to database", traceback=True)
                return self._add_(**kwargs)

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
        topLinks = self.db.query(RedirectLink).order_by(RedirectLink.no_clicks.desc()).limit(n).all()
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
    def _set_variable_(self):

        return self.redirect("/variables")


def main():

    config = get_config()

    env.filters['time_t'] = prettytime
    env.filters['int'] = int
    env.filters['escapekeyword'] = escapekeyword

    env.globals["enumerate"] = enumerate
    env.globals["sample"] = random.sample
    env.globals["len"] = len
    env.globals["min"] = min
    env.globals["str"] = str
    env.globals.update(globals())

    #if config.get('cfg_sslEnabled', False):
    #    server.socket_host = '0.0.0.0'
    #    server.socket_port = 443
    #    server.ssl_certificate = config.get('cfg_sslCertificate', '')
    #    server.ssl_private_key = config.get('cfg_sslPrivateKey', '')
    cherrypy.request.query_string_encoding = 'latin1'

    file_path = os.getcwd().replace("\\", "/")
    conf = {'/favicon.ico': {'tools.staticfile.on': True,
                             'tools.staticfile.filename': file_path + '/static/favicon.ico'},
            '/css': {'tools.staticdir.on': True,
                     'tools.staticdir.dir': file_path + '/static/css'},
            '/js': {'tools.staticdir.on': True,
                    'tools.staticdir.dir': file_path + '/static/js'},
            '/': {'tools.db.on': True,
                  'tools.sessions.on': True}
           }

    print("Cherrypy conf: %s" % conf)

    cherrypy.tree.mount(Root(), "/", config=conf)

    cherrypy.tools.db = SQLAlchemyTool()
    dbpath = os.environ.get('GO_DATABASE') or config.get('cfg_fnDatabase', 'sqlite:///f5go.db')
    sqlalchemy_plugin = SQLAlchemyPlugin(cherrypy.engine, Base, dbpath, echo=True)
    sqlalchemy_plugin.subscribe()
    sqlalchemy_plugin.create()
    cherrypy.engine.start()
    cherrypy.engine.block()


if __name__ == "__main__":
    main()
