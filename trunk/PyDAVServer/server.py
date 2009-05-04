#!/usr/bin/env python

"""
Python WebDAV Server.
Copyright (C) 1999-2005 Christian Scholz (cs@comlounge.net)

    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Library General Public
    License as published by the Free Software Foundation; either
    version 2 of the License, or (at your option) any later version.

    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Library General Public License for more details.

    You should have received a copy of the GNU Library General Public
    License along with this library; if not, write to the Free
    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

This is an example implementation of a DAVserver using the DAV package.

"""

import getopt, sys, os
import BaseHTTPServer

try:
    import DAV
except ImportError:
    print 'DAV package not found! Please install into site-packages or set PYTHONPATH!'
    sys.exit(2)

from DAV.utils import VERSION, AUTHOR
__version__ = VERSION
__author__  = AUTHOR

from fileauth import DAVAuthHandler
from mysqlauth import MySQLAuthHandler
from fshandler import FilesystemHandler
from daemonize import startstop
from DAV.INI_Parse import Configuration

def runserver(
         port = 8008, host='localhost',
         directory='/tmp',
         verbose = False,
         noauth = False,
         user = '',
         password = '',
         handler = DAVAuthHandler,
         server = BaseHTTPServer.HTTPServer):

    directory = directory.strip()
    host = host.strip()
   
    if not os.path.isdir(directory):
        print >>sys.stderr, '>> ERROR: %s is not a valid directory!' % directory
        return sys.exit(233)
    
    # basic checks against wrong hosts
    if host.find('/') != -1 or host.find(':') != -1:
        print >>sys.stderr, '>> ERROR: Malformed host %s' % host
        return sys.exit(233)

    # no root directory
    if directory == '/':
        print >>sys.stderr, '>> ERROR: Root directory not allowed!'
        sys.exit(233)
        
    # dispatch directory and host to the filesystem handler
    # This handler is responsible from where to take the data
    handler.IFACE_CLASS = FilesystemHandler(directory, 'http://%s:%s/' % (host, port), verbose )

    # put some extra vars
    handler.verbose = verbose
    if noauth:
        print >>sys.stderr, '>> ATTENTION: Authentication disabled!'
        handler.DO_AUTH = False

    print >>sys.stderr, '>> Serving data from %s' % directory
   
    # initialize server on specified port
    runner = server( (host, port), handler )
    print >>sys.stderr, '>> Listening on %s (%i)' % (host, port)

    if verbose:
        print >>sys.stderr, '>> Verbose mode ON'

    print ''

    try:
        runner.serve_forever()
    except KeyboardInterrupt:
        print >>sys.stderr, '\n>> Killed by user'

usage = """PyWebDAV server (version %s)
Standalone WebDAV server based on python

Usage: ./server.py [OPTIONS]
Parameters:
    -c, --config    Specify a file where configuration is specified. In this
                    file you can specify options for a running server.
                    For an example look at the config.ini in this directory.
    -D, --directory Directory where to serve data from
                    The user that runs this server must have permissions
                    on that directory. NEVER run as root!
                    Default directory is /tmp
    -H, --host      Host where to listen on (default: localhost)
    -P, --port      Port to bind server to  (default: 8008)
    -u, --user      Username for authentication
    -p, --password  Password for given user
    -n, --noauth    Pass parameter if server should not ask for authentication
                    This means that every user has access
    -m, --mysql     Pass this parameter if you want MySQL based authentication.
                    If you want to use MySQL then the usage of a configuration
                    file is mandatory.
    -J, --lockemu   Activate experimental lock and unlock emulation. Currently
                    no real locking is done. It is only to satisfy clients
                    needing DAV 2 compliant server for read/write access 
                    (Mac OS X Finder).
    -i, --icounter  If you want to run multiple instances then you have to
                    give each instance it own number so that logfiles and such
                    can be identified. Default is 0
    -d, --daemon    Make server act like a daemon. That means that it is going
                    to background mode. All messages are redirected to
                    logfiles (default: /tmp/pydav.log and /tmp/pydav.err).
                    You need to pass one of the following values to this parameter
                        start   - Start daemon
                        stop    - Stop daemon
                        restart - Restart complete server
                        status  - Returns status of server
                        
    -v, --verbose   Be verbose
    -h, --help      Show this screen
    
Please send bug reports and feature requests to %s
""" % (__version__, __author__)

if __name__ == '__main__':

    verbose = False
    directory = '/tmp'
    port = 8008
    host = 'localhost'
    noauth = False
    user = ''
    password = ''
    daemonize = False
    daemonaction = 'start'
    counter = 0
    mysql = False
    lockemulation = False
    configfile = ''
    
    # parse commandline
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'P:D:H:d:u:p:nvhmJi:c:', 
                ['host=', 'port=', 'directory=', 'user=', 'password=','daemon=', 'noauth', 'help', 'verbose', 
                 'mysql', 'icounter=', 'config=', 'lockemu'])
    except getopt.GetoptError, e:
        print usage
        print '>>>> ERROR: %s' % str(e)
        sys.exit(2)
    
    for o,a in opts:
        if o in ['-i', '--icounter']:
            counter = int(str(a).strip())

        if o in ['-m', '--mysql']:
            mysql = True

        if o in ['-J', '--lockemu']:
            lockemulation = True

        if o in ['-c', '--config']:
            configfile = a

        if o in ['-D', '--directory']:
            directory = a

        if o in ['-H', '--host']:
            host = a

        if o in ['-P', '--p']:
            port = a

        if o in ['-v', '--verbose']:
            verbose = True

        if o in ['-h', '--help']:
            print usage
            sys.exit(2)
    
        if o in ['-n', '--noauth']:
            noauth = True

        if o in ['-u', '--user']:
            user = a

        if o in ['-p', '--password']:
            password = a

        if o in ['-d', '--daemon']:
            daemonize = True
            daemonaction = a

    conf = None
    if configfile != '':
        print >>sys.stderr, 'Reading configuration from %s' % configfile
        conf = Configuration(configfile)

        dv = conf.DAV
        verbose = bool(int(dv.verbose))
        directory = dv.directory
        port = dv.port
        host = dv.host
        noauth = bool(int(dv.noauth))
        user = dv.user
        password = dv.password
        daemonize = bool(int(dv.daemonize))
        if daemonaction != 'stop':
            daemonaction = dv.daemonaction
        counter = int(dv.counter)

    else:

        class DummyConfigDAV:
            verbose = verbose
            directory = directory
            port = port
            host = host
            noauth = noauth
            user = user
            password = password
            daemonize = daemonize
            daemonaction = daemonaction
            counter = counter
            lockemulation = lockemulation

        class DummyConfig:
            DAV = DummyConfigDAV()
    
        conf = DummyConfig()

    if mysql == True and configfile == '':
        print >>sys.stderr, '>> ERROR: You can only use MySQL with configuration file!'
        sys.exit(3)

    if daemonaction != 'stop':
        print >>sys.stderr, 'Starting up PyWebDAV server (version %s)' % __version__
    else:
        print >>sys.stderr, 'Stopping PyWebDAV server (version %s)' % __version__

    if not noauth and daemonaction not in ['status', 'stop']:
        if not user:
            print >>sys.stderr, '>> ERROR: Please specify an username or pass parameter --noauth (get options with --help)'
            sys.exit(3)
  
    if daemonaction == 'status':
        print >>sys.stdout, 'Checking for state...'
   
    if type(port) == type(''):
        port = int(port.strip())
   
    if daemonize:

        # check if pid file exists
        if os.path.exists('/tmp/pydav%s.pid' % counter) and daemonaction != 'stop':
            print >>sys.stderr, \
                  '>> ERROR: Found another instance! Either use -i to specifiy another instance number or remove /tmp/pydav%s.pid!' % counter
            sys.exit(3)

        startstop(stdout='/tmp/pydav%s.log' % counter, 
                    stderr='/tmp/pydav%s.err' % counter, 
                    pidfile='/tmp/pydav%s.pid' % counter, 
                    startmsg='>> Started PyWebDAV (PID: %s)',
                    action=daemonaction)
  
    # start now
    handler = DAVAuthHandler
    if mysql == True:
        handler = MySQLAuthHandler

    # injecting options
    handler._config = conf

    runserver(port, host, directory, verbose, noauth, user, password, handler=handler)
