from sqlalchemy import Boolean, Column, Integer, String, DateTime, Table, ForeignKey, func
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

association_table = Table('association', Base.metadata,
                          Column('list_id', Integer, ForeignKey('listoflinks.id')),
                          Column('link_id', Integer, ForeignKey('links.id')))


class ListOfLinks(Base):
    __tablename__ = 'listoflinks'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    mode = Column(String, default='freshest')
    last_used = Column(DateTime, onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    links = relationship('Link', back_populates="lists", secondary=association_table)


class Link(Base):
    __tablename__ = 'links'
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    no_clicks = Column(Integer, default=0)
    regex = Column(Boolean, default=False)
    last_used = Column(DateTime, onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    # 1 to many
    edits = relationship('Edit')
    # many to many
    lists = relationship('ListOfLinks', back_populates='links', secondary=association_table)


class Edit(Base):
    __tablename__ = 'edits'
    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey('links.id'))
    editor = Column(String)
    created_at = Column(DateTime, server_default=func.now())

