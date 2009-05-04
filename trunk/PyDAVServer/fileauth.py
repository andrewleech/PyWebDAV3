#!/usr/bin/env python

"""
Python WebDAV Server.
Copyright (C) 1999 Christian Scholz (ruebe@aachen.heimat.de)

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


from DAV.WebDAVServer import DAVRequestHandler
from fshandler import FilesystemHandler
import sys
from DAV.dbconn import Mconn

class DAVAuthHandler(DAVRequestHandler):
    """
    Provides authentication based on parameters. The calling
    class has to inject password and username into this.
    (Variables: auth_user and auth_pass)
    """
    
    # Do not forget to set IFACE_CLASS by caller
    # ex.: IFACE_CLASS = FilesystemHandler('/tmp', 'http://localhost/')
    verbose = False
    
    def _log(self, message):
        if self.verbose:
            print >>sys.stderr, '>> (DAVAuthHandler) %s' % message

    def get_userinfo(self,user,pw,command):
        """ authenticate user """

        if user == self._config.DAV.user and pw == self._config.DAV.password:
            self._log('Successfully authenticated user %s' % user)
            return 1

        self._log('Authentication failed for user %s' % user)
        return 0

