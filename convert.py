#! /usr/bin/env python

import pickle
import datetime
import time
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models import Base, RedirectList, RedirectLink, Edit


class Clickable:
    def __init__(self):
        self.archivedClicks = 0
        self.clickData = {}

    def __repr__(self):
        return '%s(archivedClicks=%s, clickData=%s)' % (self.__class__.__name__,
                                                        self.archivedClicks,
                                                        self.clickData)

    def __getattr__(self, attrname):
        if attrname == "totalClicks":
            return self.archivedClicks + sum(self.clickData.values())
        if attrname == "recentClicks":
            return sum(self.clickData.values())
        if attrname == "lastClickTime":
            if not self.clickData:
                return 0
            maxk = max(self.clickData.keys())
            return time.mktime(datetime.date.fromordinal(maxk).timetuple())
        if attrname == "lastClickDay":
            if not self.clickData:
                return 0
            return max(self.clickData.keys())

        raise AttributeError(attrname)


class Link(Clickable):
    def __init__(self, linkid=0, url="", title=""):
        Clickable.__init__(self)

        self.linkid = linkid
        self._url = url
        self.title = title

        self.edits = []    # (edittime, editorname); [-1] is most recent
        self.lists = []    # List() instances

    def __repr__(self):
        return '%s(linkid=%s, url=%s, title=%s, edits=%s, lists=%s)' % (self.__class__.__name__,
                                                                        self.linkid, self._url,
                                                                        self.title, self.edits,
                                                                        self.lists)

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


class RegexList(ListOfLinks):
    def __init__(self, linkid=0, regex=""):
        ListOfLinks.__init__(self, linkid, regex)

        self.regex = regex

    def __repr__(self):
        return '%s(linkid=%s, regex=%s)' % (self.__class__.__name__,
                                            self.linkid, self.regex)


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

def main():
    engine = create_engine('sqlite:///f5go.db')
    Base.metadata.create_all(engine)
    session = scoped_session(sessionmaker(bind=engine))

    logging.basicConfig(level=logging.INFO)

    with open('godb.pickle', 'rb') as p:
        db = pickle.load(p)
        for l in db.lists.values():

            redir_list = RedirectList(name=l.name)
            link_redir = False

            try:
                # redirect to individual link
                int(l._url)
                link_redir = True
            except ValueError:
                redir_list.redirect = l._url

            for li in l.links:
                s = session.query(RedirectLink).filter_by(url=li._url).first()

                if not s:

                    s = RedirectLink(url=li._url,
                                     title=li.title,
                                     no_clicks=li.archivedClicks)
                    if '{*}' in li._url:
                        s.regex = True

                    li_dates = sorted([datetime.date.fromordinal(c) for c in li.clickData.keys()], reverse=True)
                    if li_dates:
                        s.last_used = li_dates[0]

                    for e in li.edits:
                        edit = Edit(editor=e[1],
                                    created_at=datetime.datetime.fromtimestamp(e[0]))
                        s.edits.append(edit)

                session.add(s)
                session.flush()

                if link_redir and int(l._url) == li.linkid:
                    logging.info('setting redirect for RedirectList to RedirectLink ID %s', s.id)
                    redir_list.redirect = s.id

                redir_list.links.append(s)

            l_dates = sorted([datetime.date.fromordinal(d) for d in l.clickData.keys()], reverse=True)
            if l_dates:
                redir_list.last_used = l_dates[0]

            session.add(redir_list)
            try:
                session.commit()
                logging.info('added list %s with %s links', l.name, len(redir_list.links))
            except Exception as err:
                logging.error('unable to add list %s', l.name)
                logging.error(err)


if __name__ == '__main__':
    main()
