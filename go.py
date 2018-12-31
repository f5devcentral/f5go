#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This is the Go Redirector. It uses short mnemonics as redirects to otherwise
long URLs. Few remember how to write in cursive, most people don't remember
common phone numbers, and just about everyone needs a way around bookmarks.
"""

__author__ = "Saul Pwanson <saul@pwanson.com>"
__credits__ = "Bill Booth, Bryce Bockman, treebird, Sean Smith"

import base64
import datetime
import os
import pickle
import random
import re
import string
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import configparser
import cherrypy
import jinja2
import shutil
import html


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


def randomlink():
    return random.choice([x for x in list(g_db.linksById.values()) if not x.isGenerative() and x.usage()])


def today():
    return datetime.date.today().toordinal()


def escapekeyword(kw):
    return urllib.parse.quote_plus(kw, safe="/")


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


class Clickable:
    def __init__(self):
        self.archivedClicks = 0
        self.clickData = {}

    def __repr__(self):
        return '%s(archivedClicks=%s, clickData=%s)' % (self.__class__.__name__,
                                                        self.archivedClicks,
                                                        self.clickData)

    def clickinfo(self):
        return "%s recent clicks (%s total); last visited %s" % (self.recentClicks, self.totalClicks, prettyday(self.lastClickDay))

    def __getattr__(self, attrname):
        if attrname == "totalClicks":
            return self.archivedClicks + sum(self.clickData.values())
        elif attrname == "recentClicks":
            return sum(self.clickData.values())
        elif attrname == "lastClickTime":
            if not self.clickData:
                return 0
            maxk = max(self.clickData.keys())
            return time.mktime(datetime.date.fromordinal(maxk).timetuple())
        elif attrname == "lastClickDay":
            if not self.clickData:
                return 0
            return max(self.clickData.keys())
        else:
            raise AttributeError(attrname)

    def clicked(self, n=1):
        """
        :param n: The number of clicks to record
        :return:
        """
        todayord = today()
        if todayord not in self.clickData:
            # partition clickdata around 30 days ago
            archival = []
            recent = []
            for od, nclicks in list(self.clickData.items()):
                if todayord - 30 > od:
                    archival.append((od, nclicks))
                else:
                    recent.append((od, nclicks))

            # archive older samples
            if archival:
                self.archivedClicks += sum(nclicks for od, nclicks in archival)

            # recent will have at least one sample if it was ever clicked
            recent.append((todayord, n))
            self.clickData = dict(recent)
        else:
            self.clickData[todayord] += n

    def _export(self):
        return "%d,%s" % (self.archivedClicks, "".join(str(self.clickData).split()))

    def _import(self, s):
        archivedClicks, clickdict = s.split(",", 1)
        self.archivedClicks = int(archivedClicks)
        self.clickData = eval(clickdict)
        return self


class Link(Clickable):
    def __init__(self, linkid=0, url="", title=""):
        Clickable.__init__(self)

        self.linkid = linkid
        self._url = canonicalUrl(url)
        self.title = title

        self.edits = []    # (edittime, editorname); [-1] is most recent
        self.lists = []    # List() instances

    def __repr__(self):
        return '%s(linkid=%s, url=%s, title=%s, edits=%s, lists=%s)' % (self.__class__.__name__,
                                                                        self.linkid, self._url,
                                                                        self.title, self.edits,
                                                                        self.lists)

    def isGenerative(self):
        return any([K.isGenerative() for K in self.lists])

    def listnames(self):
        return [x.name for x in self.lists]

    def _export(self):
        a = "+".join(self._url.split())
        b = "||".join([x.name for x in self.lists]) or "None"
        c = Clickable._export(self)
        d = ",".join(["%d/%s" % x for x in self.edits]) or "None"
        e = self.title

        return "link %s %s %s %s %s" % (a, b, c, d, e)

    def _dump(self):
        a = "|".join([x.name for x in self.lists]) or "None"
        b = self.title
        c = self._url

        return "%s\t%s\t%s" % (a, b, c)

    def _import(self, line):
        self._url, lists, clickdata, edits, title = line.split(" ", 4)
        print(">>", line)
        print(self._url)
        if self._url in g_db.linksByUrl:
            self._url = g_db.linksByUrl[self._url].linkid
            print("XYZ", self._url)

        if lists != "None":
            for listname in lists.split("||"):
                if "{*}" in self._url:
                    if listname[-1] != "/":
                        listname += "/"
                g_db.getList(listname, create=True).addLink(self)

        self.title = title.strip()

        Clickable._import(self, clickdata)

        if edits != "None":
            edits = [x.split("/") for x in edits.split(",")]
            self.edits = [(float(x[0]), x[1]) for x in edits]

    def editedBy(self, editor):
        self.edits.append((time.time(), editor))

    def lastEdit(self):
        if not self.edits:
            return (0, "")

        return self.edits[-1]

    def href(self):
        if self.isGenerative():
            kw = self.mainKeyword()
            if kw:
                return "/.%s" % escapekeyword(kw.name)
            else:
                return ""
        else:
            if self.linkid > 0:
                return "/_link_/%s" % self.linkid
            else:
                return self._url

    def url(self, keyword=None, args=None):
        remainingPath = (keyword or cherrypy.request.path_info).split("/")[2:]
        d = {"*": "/".join(remainingPath), "0": keyword}
        d.update(g_db.variables)
        d.update(getDictFromCookie("variables"))

        while True:
            try:
                return string.Formatter().vformat(self._url, args or remainingPath, d)
            except KeyError as e:
                missingKey = e.args[0]
                d[missingKey] = "{%s}" % missingKey
            except IndexError:
                return None

    def mainKeyword(self):
        goesStraightThere = [LL for LL in self.lists if LL.goesDirectlyTo(self)]

        if not goesStraightThere:
            return None

        return byClicks(goesStraightThere)[0]

    def usage(self):
        kw = self.mainKeyword()
        if kw is None:
            return ""
        return kw.usage()

    def opacity(self, todayord):
        """goes from 1.0 (today) to 0.2 (a month ago)"""
        dtDays = todayord - self.lastClickDay
        c = min(1.0, max(0.2, (30.0 - dtDays) / 30))
        return "%.02f" % c


class ListOfLinks(Link):
    # for convenience, inherits from Link.  most things that apply
    # to Link applies to a ListOfLinks too
    def __init__(self, linkid=0, name="", redirect="freshest"):
        Link.__init__(self, linkid)
        self.name = name
        self._url = redirect  # list | freshest | top | random
        self.links = []

    def __repr__(self):
        return '%s(linkid=%s, name=%s, redirect=%s, links=%s)' % (self.__class__.__name__,
                                                                  self.linkid, self.name,
                                                                  self._url, self.links)


    def isGenerative(self):
        return self.name[-1] == "/"

    def usage(self):
        if self.isGenerative():  # any([ L.isGenerative() for L in self.links ]):
            return "%s..." % self.name

        return self.name

    def addLink(self, link):
        if link not in self.links:
            self.links.insert(0, link)
            link.lists.append(self)

    def removeLink(self, link):
        if link in self.links:
            self.links.remove(link)
        if self in link.lists:
            link.lists.remove(self)

    def getRecentLinks(self):
        return self.links

    def getPopularLinks(self):
        return byClicks(self.links)

    def getLinks(self, nDaysOfRecentEdits=1):
        earliestRecentEdit = time.time() - nDaysOfRecentEdits * 24 * 3600

        recent = [x for x in self.links if x.lastEdit()[0] > earliestRecentEdit]
        popular = self.getPopularLinks()

        for L in recent:
            popular.remove(L)

        return recent, popular

    def getDefaultLink(self):
        if not self._url or self._url == "list":
            return None
        elif self._url == "top":
            return self.getPopularLinks()[0]
        elif self._url == "random":
            return random.choice(self.links)
        elif self._url == "freshest":
            return self.getRecentLinks()[0]
        else:
            return g_db.getLink(self._url)

    def url(self, keyword=None, args=None):
        if not self._url or self._url == "list":
            return None
        elif self._url == "top":
            return self.getPopularLinks()[0].url(keyword, args)
        elif self._url == "random":
            return random.choice(self.links).url(keyword, args)
        elif self._url == "freshest":
            return self.getRecentLinks()[0].url(keyword, args)
        else:  # should be a linkid
            return "/_link_/" + self._url

    def goesDirectlyTo(self, link):
        return self._url == str(link.linkid) or self.url() == link.url()

    def _export(self):
        if isinstance(self._url, int): # linkid needs to be converted for export
            L = g_db.getLink(self._url)
            if L and L in self.links:
                print(L)
                self._url = L._url
            else:
                print("fixing unknown dest linkid for", self.name)
                self._url = "list"

        return ("list %s " % self.name) + Link._export(self)

    def _import(self, line):
        self.name, _, rest = line.split(" ", 2)
        assert _ == "link"
        g_db._addList(self)
        Link._import(self, rest)


class RegexList(ListOfLinks):
    def __init__(self, linkid=0, regex=""):
        ListOfLinks.__init__(self, linkid, regex)

        self.regex = regex

    def __repr__(self):
        return '%s(linkid=%s, regex=%s)' % (self.__class__.__name__,
                                            self.linkid, self.regex)

    def usage(self):
        return self.regex

    def isGenerative(self):
        return True

    def matches(self, kw=None):
        if kw is None:
            kw = cherrypy.request.path_info.split("/")[1]

        ret = []

        m = re.match(self.regex, kw, re.IGNORECASE)
        if m:
            deflink = self.getDefaultLink()
            for L in deflink and [deflink] or self.links:
                url = L.url(keyword=kw, args=(m.group(0), ) + m.groups())
                ret.append((L, Link(0, url, L.title)))

        return ret

    def url(self, kw=None):

        if kw is None:
            kw = cherrypy.request.path_info.split("/")[1]

        m = re.match(self.regex, kw, re.IGNORECASE)
        if not m:
            return None

        return ListOfLinks.url(self, keyword=kw, args=(m.group(0), ) + m.groups())

    def _export(self):
        return ("regex %s " % self.regex) + ListOfLinks._export(self)

    def _import(self, line):
        self.regex, _, rest = line.split(" ", 2)
        assert _ == "list"
        ListOfLinks._import(self, rest)


class LinkDatabase:
    def __init__(self):
        self.regexes = {}        # regex -> RegexList
        self.lists = {}          # listname -> ListOfLinks
        self.variables = {}      # varname -> value
        self.linksById = {}      # link.linkid -> Link
        self.linksByUrl = {}     # link._url -> Link
        self._nextlinkid = 1

    def __repr__(self):
        return '%s(regexes=%s, lists=%s, vars=%s, byId=%s, byUrl=%s)' % (self.__class__.__name__,
                                                                         self.regexes, self.lists,
                                                                         self.variables,
                                                                         self.linksById,
                                                                         self.linksByUrl)


    @staticmethod
    def load(db=cfg_fnDatabase):
        """Attempt to load the database defined at cfg_fnDatabase. Create a
        new one if the database doesn't already exist.
        """
        try:
            print("Loading DB from %s" % db)
            return pickle.load(open(db, 'rb'))
        except IOError:
            print(sys.exc_info()[1])
            print("Creating new database...")
            return LinkDatabase()

    def save(self):
        #TODO: Make this get saved to a database, this is a temporary solution to prevent corruption
        tmpfile = cfg_fnDatabase + '.tmp'
        pickle.dump(self, open(tmpfile, "wb"))
        shutil.copyfile(tmpfile, cfg_fnDatabase)
        os.remove(tmpfile)

    def nextlinkid(self):
        r = self._nextlinkid
        self._nextlinkid += 1
        return r

    def addRegexList(self, regex=None, url=None, desc=None, owner=""):
        r = RegexList(self.nextlinkid(), regex)
        r._url = url
        self._addRegexList(r, owner)

    def _addRegexList(self, r, owner):
        self.regexes[r.regex] = r
        self._addList(r)     # add to all indexes

    def addLink(self, lists, url, title, owner=""):
        if url in self.linksByUrl:
            raise RuntimeError("existing url")

        if type(lists) == str:
            lists = lists.split()

        link = Link(self.nextlinkid(), url, title)

        for kw in lists:
            self.getList(kw, create=True).addLink(link)

        self._addLink(link, owner)

        return link

    def _addLink(self, link, editor=None):
        if editor:
            link.editedBy(editor)

        self.linksById[link.linkid] = link
        self.linksByUrl[link._url] = link

    def _changeLinkUrl(self, link, newurl):
        if link._url in self.linksByUrl:
            del self.linksByUrl[link._url]
        link._url = newurl
        self.linksByUrl[newurl] = link

    def _addList(self, LL):
        self.lists[LL.name] = LL

    def deleteLink(self, link):
        for LL in list(link.lists):
            LL.removeLink(link)
            if not LL.links:  # auto-delete lists with no links
                self.deleteList(LL)

        self._removeLinkFromUrls(link._url)

        if link.linkid in self.linksById:
            del self.linksById[link.linkid]

        if isinstance(link, RegexList):
            del self.regexes[link.regex]

        return "deleted go/%s" % link.linkid

    def _removeLinkFromUrls(self, url):
        if url in self.linksByUrl:
            del self.linksByUrl[url]

    def deleteList(self, LL):
        for link in list(LL.links):
            LL.removeLink(link)

        del self.lists[LL.name]
        self.deleteLink(LL)
        return "deleted go/%s" % LL.name

    def getLink(self, linkid):
        return self.linksById.get(int(linkid), None)

    def getAllLists(self):
        return byClicks(list(self.lists.values()))

    def getSpecialLinks(self):
        links = set()
        for R in list(g_db.regexes.values()):
            links.update(R.links)

        links.update(self.getFolders())

        return list(links)

    def getFolders(self):
        return [x for x in list(self.linksById.values()) if x.isGenerative()]

    def getNonFolders(self):
        return [x for x in list(self.linksById.values()) if not x.isGenerative()]

    def getList(self, listname, create=False):
        if "\\" in listname:  # is a regex
            return self.getRegex(listname, create)

        sanelistname = sanitary(listname)

        if not sanelistname:
            raise InvalidKeyword("keyword '%s' not sanitary" % listname)

        if sanelistname not in self.lists:
            if not create:
                return None
            self._addList(ListOfLinks(self.nextlinkid(), sanelistname, redirect="freshest"))

        return self.lists[sanelistname]

    def getRegex(self, listname, create=False):
        try:
            re.compile(listname)
        except:
            raise InvalidKeyword(listname)

        if listname not in self.regexes:
            if not create:
                return None
            self._addRegexList(RegexList(self.nextlinkid(), listname), "")

        return self.regexes[listname]

    def renameList(self, LL, newname):
        assert newname not in self.lists
        oldname = LL.name
        self.lists[newname] = self.lists[oldname]
        del self.lists[oldname]
        LL.name = newname
        return "renamed go/%s to go/%s" % (oldname, LL.name)

    def _export(self, fn):
        print("exporting to %s" % fn)
        with open(fn, "w") as f:
            for k, v in list(self.variables.items()):
                f.write("variable %s %s\n" % (k, v))

            for L in list(self.linksById.values()):
                f.write(L._export() + "\n")

            for LL in list(self.lists.values()):
                f.write(LL._export() + "\n")

    # for the tsv dumper
    def _dump(self, fh):
        for link in list(self.linksById.values()):
            fh.write(link._dump() + "\n")

    def _import(self, fn):
        print("importing from %s" % fn)
        with open(fn, "r") as f:
            for l in f.readlines():
                if not l.strip(): continue
                print(l.strip())
                a, b = string.split(l, " ", 1)
                if a == "regex":
                    R = RegexList(self.nextlinkid())
                    R._import(b)
                elif a == "link":
                    L = Link(self.nextlinkid())
                    L._import(b)
                    self._addLink(L)
                elif a == "list":
                    listname, rest = string.split(b, " ", 1)
                    if listname in self.lists:
                        LL = self.lists[listname]
                    else:
                        LL = ListOfLinks(self.nextlinkid())
                    LL._import(b)
                elif a == "variable":
                    k, v = b.split(" ", 1)
                    self.variables[k] = v.strip()

        assert self._nextlinkid == max(self.linksById.keys()) + 1

        self.save()


class Root:
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
        luckylink = random.choice(g_db.getNonFolders())
        luckylink.clicked()
        return self.redirect(deampify(luckylink.url()))

    @cherrypy.expose
    def index(self, **kwargs):
        self.redirectIfNotFullHostname()

        if "keyword" in kwargs:
            return self.redirect("/" + kwargs["keyword"])

        return env.get_template('index.html').render(now=today())

    @cherrypy.expose
    def default(self, *rest, **kwargs):
        self.redirectIfNotFullHostname()

        keyword = rest[0]
        rest = rest[1:]

        forceListDisplay = False
        #action = kwargs.get("action", "list")

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

        # try it as a list
        try:
            ll = g_db.getList(keyword, create=False)
        except InvalidKeyword as e:
            return self.notfound(str(e))

        if not ll:  # nonexistent list
            # check against all special cases
            matches = []
            for R in list(g_db.regexes.values()):
                matches.extend([(R, L, genL) for L, genL in R.matches(keyword)])

            if not matches:
                kw = sanitary(keyword)
                if not kw:
                    return self.notfound("No match found for '%s'" % keyword)

                # serve up empty fake list
                return env.get_template('list.html').render(L=ListOfLinks(0), keyword=kw)
            elif len(matches) == 1:
                R, L, genL = matches[0]  # actual regex, generated link
                R.clicked()
                L.clicked()
                return self.redirect(deampify(genL.url()))
            else:  # len(matches) > 1
                LL = ListOfLinks(-1)  # -1 means non-editable
                LL.links = [genL for R, L, genL in matches]
                return env.get_template('list.html').render(L=LL, keyword=keyword)

        listtarget = ll.getDefaultLink()

        if listtarget and not forceListDisplay:
            ll.clicked()
            listtarget.clicked()
            return self.redirect(deampify(listtarget.url()))

        tmplList = env.get_template('list.html')
        return tmplList.render(L=ll, keyword=keyword)

    @cherrypy.expose
    def special(self):
        LL = ListOfLinks(-1)
        LL.name = "Smart Keywords"
        LL.links = g_db.getSpecialLinks()

        env.globals['g_db'] = g_db
        return env.get_template('list.html').render(L=LL, keyword="special")

    @cherrypy.expose
    def _login_(self, redirect=""):
        if redirect:
            return self.redirect(redirect)
        return self.undirect()

    @cherrypy.expose
    def me(self):
        username = getSSOUsername()
        return self.redirect(username)

    @cherrypy.expose
    def _link_(self, linkid):
        link = g_db.getLink(linkid)
        if link:
            link.clicked()
            return self.redirect(link.url(), status=301)

        cherrypy.response.status = 404
        return self.notfound("Link %s does not exist" % linkid)

    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        # _add_/tag1/tag2/tag3
        link = Link()
        link.lists = [g_db.getList(listname, create=False) or ListOfLinks(0, listname) for listname in args]
        return env.get_template("editlink.html").render(L=link, returnto=(args and args[0] or None), **kwargs)

    @cherrypy.expose
    def _edit_(self, linkid, **kwargs):
        link = g_db.getLink(linkid)
        if link:
            return env.get_template("editlink.html").render(L=link, **kwargs)

        # edit new link
        return env.get_template("editlink.html").render(L=Link(), **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        K = g_db.getList(keyword, create=False)
        if not K:
            K = ListOfLinks()
        return env.get_template("list.html").render(L=K, keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        K = g_db.getList(keyword, create=False)

        if "behavior" in kwargs:
            K._url = kwargs["behavior"]

        return self.redirectToEditList(keyword)

    @cherrypy.expose
    def _delete_(self, linkid, returnto=""):

        g_db.deleteLink(g_db.getLink(linkid))

        return self.redirect("/." + returnto)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def _modify_(self, **kwargs):
        username = getSSOUsername()

        linkid = kwargs.get("linkid", "")
        title = escapeascii(kwargs.get("title", ""))
        lists = kwargs.get("lists", [])
        url = kwargs.get("url", "")
        otherlists = kwargs.get("otherlists", "")

        returnto = kwargs.get("returnto", "")

        # remove any whitespace/newlines in url
        url = "".join(url.split())

        if type(lists) not in [tuple, list]:
            lists = [lists]

        lists.extend(otherlists.split())

        if linkid:
            link = g_db.getLink(linkid)
            if link._url != url:
                g_db._changeLinkUrl(link, url)
            link.title = title

            newlistset = []
            for listname in lists:
                if "{*}" in url:
                    if listname[-1] != "/":
                        listname += "/"
                try:
                    newlistset.append(g_db.getList(listname, create=True))
                except:
                    return self.redirectToEditLink(error="invalid keyword '%s'" % listname, **kwargs)

            for LL in newlistset:
                if LL not in link.lists:
                    LL.addLink(link)

            for LL in [x for x in link.lists]:
                if LL not in newlistset:
                    LL.removeLink(link)
                    if not LL.links:
                        g_db.deleteList(LL)

            link.lists = newlistset

            link.editedBy(username)

            g_db.save()

            return self.redirect("/." + returnto)

        if not lists:
            return self.redirectToEditLink(error="delete links that have no lists", **kwargs)

        if not url:
            return self.redirectToEditLink(error="URL required", **kwargs)

        # if url already exists, redirect to that link's edit page
        if url in g_db.linksByUrl:
            link = g_db.linksByUrl[url]

            # only modify lists; other fields will only be set if there
            # is no original

            combinedlists = set([x.name for x in link.lists]) | set(lists)

            fields = {'title': link.title or title,
                      'lists': " ".join(combinedlists),
                      'linkid': str(link.linkid)
                      }

            return self.redirectToEditLink(error="found identical existing URL; confirm changes and re-submit", **fields)

        link = g_db.addLink(lists, url, title, username)

        g_db.save()
        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n="100"):
        return env.get_template("toplinks.html").render(n=int(n))

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
        if varname and value:
            g_db.variables[varname] = value
            g_db.save()

        return self.redirect("/variables")


env = jinja2.Environment(loader=jinja2.FileSystemLoader("./html"))


def main():
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

    # checkpoint the database every 60 seconds
    cherrypy.process.plugins.BackgroundTask(60, lambda: g_db.save()).start()

    file_path = os.getcwd().replace("\\", "/")
    conf = {'/images': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/images"},
            '/css': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/css"},
            '/js': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/js"}}
    print("Cherrypy conf: %s" % conf)
    cherrypy.quickstart(Root(), "/", config=conf)


if __name__ == "__main__":

    g_db = LinkDatabase.load()

    if "import" in sys.argv:
        g_db._import("newterms.txt")

    elif "export" in sys.argv:
        g_db._export("newterms.txt")

    elif "dump" in sys.argv:
        g_db._dump(sys.stdout)

    else:
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
