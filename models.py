from sqlalchemy import Boolean, Column, Integer, String, DateTime, Table, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

association_table = Table('association', Base.metadata,
                          Column('list_id', Integer, ForeignKey('redirect_lists.id')),
                          Column('link_id', Integer, ForeignKey('redirect_links.id')))


class RedirectList(Base):
    __tablename__ = 'redirect_lists'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=True)
    redirect = Column(String, default='freshest')
    last_used = Column(DateTime, onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    links = relationship('RedirectLink', back_populates="lists", secondary=association_table)


class RedirectLink(Base):
    __tablename__ = 'redirect_links'
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    no_clicks = Column(Integer, default=0)
    regex = Column(Boolean, default=False)
    last_used = Column(DateTime, onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    edits = relationship('Edit')
    lists = relationship('RedirectList', back_populates='links', secondary=association_table)


class Edit(Base):
    __tablename__ = 'edits'
    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey('redirect_links.id'))
    editor = Column(String)
    created_at = Column(DateTime, server_default=func.now())

