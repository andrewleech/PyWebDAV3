PyWebDAV is a standards compliant WebDAV server and library written in Python
This alternate package has been updated for python 3 support. It should still work with 2.7

DESCRIPTION
-----------

Python WebDAV implementation (level 1 and 2) that features a library that enables you
to integrate WebDAV server capabilities to your application

A fully working example on how to use the library is included. You can find the server in the DAVServer package. Upon installation a script called davserver is created in your $PYTHON/bin directory.

If you search an easy to use WebDAV server that supports most clients (cadaver, Mac OS X Finder, Windows Explorer, ...) then try out PyWebDAV.


INSTALLATION
------------

Installation and setup of server can be as easy as follows:

$ pip install PyWebDAV3
$ davserver -D /tmp -n -J

If you're living on the bleeding edge then check out the sourcecode from
https://github.com/andrewleech/PyWebDAV3

After having downloaded code simply install a development egg:

$ git clone https://github.com/andrewleech/PyWebDAV3
$ cd PyWebDAV3
$ python setup.py develop
$ davserver --help

Any updates, fork and pull requests against my github page

If you want to use the library then have a look at the DAVServer package that
holds all code for a full blown server. Also doc/ARCHITECURE has information for you.


QUESTIONS?
---------

Ask here https://github.com/andrewleech/PyWebDAV3
or send an email to the maintainer.


REQUIREMENTS
------------

- Python 2.7  or higher (www.python.org)
- PyXML 0.66 (pyxml.sourceforge.net)


LICENSE
-------

General Public License v2
see doc/LICENSE


AUTHOR(s)
------

Andrew Leech [*]
Melbourne, Australia
andrew@alelec.net

Simon Pamies
Bielefeld, Germany
s.pamies@banality.de

Christian Scholz
Aachen, Germany
mrtopf@webdav.de

Vince Spicer
Ontario, Canada
vince@vince.ca

[*]: Current Maintainer


OPTIONAL
--------

- MySQLdb (http://sourceforge.net/projects/mysql-python)
- Mysql server 4.0+ for Mysql authentication with
  with read/write access to one database


NOTES
-----

Look inside the file doc/TODO for things which needs to be done and may be done
in the near future. 

Have a look at doc/ARCHITECTURE to understand what's going on under the hood
