
# The F5 Go Redirector

[![Build Status](https://travis-ci.org/layertwo/f5go.svg?branch=master)](https://travis-ci.org/layertwo/f5go)

*A simple service for redirecting mnemonic terms to destination urls.*

Features include:

  - anyone can add terms easily
  - regex parsing for "special cases" (using regular expressions)
  - automatically appends everything after the second slash to the destination url
  - tracks and displays term usage frequency on frontpage with fontsize
  - variables allow destination URLs to change en masse (e.g. project name)

## Required Packages

```
jinja2
cherrypy
CherryPy-SQLAlchemy
psycopg2-binary
```

## Tips

To run, execute go.py and go to localhost:8080 in a browser.

---
contributed by Saul Pwanson, Lucas Messenger

