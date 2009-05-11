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

This module builds on AuthServer by implementing the standard DAV
methods.

Subclass this class and specify an IFACE_CLASS. See example.

"""

DEBUG=None

from DAV.utils import VERSION, AUTHOR
__version__ = VERSION
__author__  = AUTHOR


import os
import sys
import time
import socket
import string
import posixpath
import base64
import AuthServer
import urlparse
import urllib
import random

from propfind import PROPFIND
from delete import DELETE
from davcopy import COPY
from davmove import MOVE

from string import atoi,split
from errors import *

class DAVRequestHandler(AuthServer.BufferedAuthRequestHandler):
    """Simple DAV request handler with 
    
    - GET
    - HEAD
    - PUT
    - OPTIONS
    - PROPFIND
    - PROPPATCH
    - MKCOL

    experimental
    - LOCK
    - UNLOCK

    It uses the resource/collection classes for serving and
    storing content.
    
    """

    server_version = "DAV/" + __version__

    ### utility functions
    def _log(self, message):
        pass

    def send_body(self,DATA,code,msg,desc,ctype='application/octet-stream',headers={}):
        """ send a body in one part """

        self.send_response(code,message=msg)
        self.send_header("Connection", "close")
        self.send_header("Accept-Ranges", "bytes")
        
        for a,v in headers.items():
            self.send_header(a,v)
        
        if DATA:
            self.send_header("Content-Length", str(len(DATA)))
            self.send_header("Content-Type", ctype)
        else:
            self.send_header("Content-Length", "0")
        
        self.end_headers()
        if DATA:
            self._append(DATA)

    def send_body_chunks(self,DATA,code,msg,desc,ctype='text/xml; encoding="utf-8"'):
        """ send a body in chunks """
        
        self.responses[207]=(msg,desc)
        self.send_response(code,message=msg)
        self.send_header("Content-type", ctype)
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        self._append(hex(len(DATA))[2:]+"\r\n")
        self._append(DATA)
        self._append("\r\n")
        self._append("0\r\n")
        self._append("\r\n")

    ### HTTP METHODS called by the server

    def do_OPTIONS(self):
        """return the list of capabilities """
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")

        if self._config.DAV.lockemulation is True:
            if self._config.DAV.verbose is True:
                print >>sys.stderr, 'Activated LOCK,UNLOCK emulation for this connection (NOT known to work currently)'

            self.send_header('Allow', 'GET, HEAD, COPY, MOVE, POST, PUT, PROPFIND, PROPPATCH, OPTIONS, MKCOL, DELETE, TRACE, LOCK, UNLOCK')
            self.send_header('DAV', '1,2')

        else:
            self.send_header("Allow", "GET, HEAD, COPY, MOVE, POST, PUT, PROPFIND, PROPPATCH, OPTIONS, MKCOL, DELETE, TRACE")
            self.send_header('DAV', '1')

        self.send_header('MS-Author-Via', 'DAV') # this is for M$
        self.end_headers()

    def _init_locks(self):
        if not hasattr(self, '_lock_table'):
            self._lock_table = {}

        return self._lock_table

    def is_locked(self, uri):
        table = self._init_locks()
        return table.has_key(uri)

    def do_LOCK(self):
        """ Locking is implemented via in-memory caches. No data is written.  """

        if self._config.DAV.verbose is True:
            print >>sys.stderr, 'LOCKing resource %s' % self.headers

        # XXX this is not finished and'll be replaced soon
        token = str(random.randint(123, 12345678))
        header = {'Lock-Token' : token}
        return self.send_status(body=str(token))

    def do_UNLOCK(self):
        """ Always send OK with no content = Status 204 """

        if self.DAV._config.DAV.verbose is True:
            print >>sys.stderr, 'UNLOCKing resource %s' % self.headers

        return self.send_status(204)

    def do_PROPFIND(self):

        dc=self.IFACE_CLASS

        # read the body
        body=None
        if self.headers.has_key("Content-Length"):
            l=self.headers['Content-Length']
            body=self.rfile.read(atoi(l))

        # which Depth?
        if self.headers.has_key('Depth'):
            d=self.headers['Depth']
        else:
            d="infinity"

        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)
        pf=PROPFIND(uri,dc,d)

        if body:    
            pf.read_propfind(body)


        try:
            DATA=pf.createResponse()
            DATA=DATA+"\n"
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

        # work around MSIE DAV bug for creation and modified date
        # taken from Resource.py @ Zope webdav
        if (self.headers.get('User-Agent') ==
            'Microsoft Data Access Internet Publishing Provider DAV 1.1'):
            result = result.replace('<ns0:getlastmodified xmlns:ns0="DAV:">',
                                    '<ns0:getlastmodified xmlns:n="DAV:" xmlns:b="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/" b:dt="dateTime.rfc1123">')
            result = result.replace('<ns0:creationdate xmlns:ns0="DAV:">',
                                    '<ns0:creationdate xmlns:n="DAV:" xmlns:b="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/" b:dt="dateTime.tz">')

        self.send_body_chunks(DATA,'207','Multi-Status','Multiple responses')

    def do_GET(self):
        """Serve a GET request."""

        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        # get the last modified date
        try:
            lm=dc.get_prop(uri,"DAV:","getlastmodified")
        except:
            lm="Sun, 01 Dec 2014 00:00:00 GMT"  # dummy!
        headers={"Last-Modified":lm}

        # get the ETag
        try:
            etag = dc.get_prop(uri, "DAV:", "getetag")
            headers['ETag'] = etag
        except:
            pass

        # get the content type
        try:
            ct=dc.get_prop(uri,"DAV:","getcontenttype")
        except:
            ct="application/octet-stream"

        # get the data
        try:
            data=dc.get_data(uri)
        except DAV_Error, (ec,dd):
            self.send_status(ec)
            return 

        # send the data
        self.send_body(data,"200","OK","OK",ct,headers)

    def do_HEAD(self):
        """ Send a HEAD response """

        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        # get the last modified date
        try:
            lm=dc.get_prop(uri,"DAV:","getlastmodified")
        except:
            lm="Sun, 01 Dec 2014 00:00:00 GMT"  # dummy!

        headers={"Last-Modified":lm}

        # get the ETag
        try:
            etag = dc.get_prop(uri, "DAV:", "getetag")
            headers['ETag'] = etag
        except:
            pass

        # get the content type
        try:
            ct=dc.get_prop(uri,"DAV:","getcontenttype")
        except:
            ct="application/octet-stream"

        try:
            data=dc.get_data(uri)
            headers["Content-Length"]=str(len(data))
        except DAV_NotFound:
            self.send_body(None,"404","Not Found","")
            return

        self.send_body(None,"200","OK","OK",ct,headers)

    def do_POST(self):
        self.send_error(404,"File not found")

    def do_MKCOL(self):
        """ create a new collection """

        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)
        try:
            dc.mkcol(uri)
            self.send_status(200)
        except DAV_Error, (ec,dd):
            self.send_status(ec)

    def do_DELETE(self):
        """ delete an resource """
        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        # Handle If-Match
        if self.headers.has_key('If-Match'):
            test = False
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass
            for match in self.headers['If-Match'].split(','):
                if match == '*':
                    if dc.exists(uri):
                        test = True
                        break
                else:
                    if match == etag:
                        test = True
                        break
            if not test:
                self.send_status(412)
                return

        # Handle If-None-Match
        if self.headers.has_key('If-None-Match'):
            test = True
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass
            for match in self.headers['If-None-Match'].split(','):
                if match == '*':
                    if dc.exists(uri):
                        test = False
                        break
                else:
                    if match == etag:
                        test = False
                        break
            if not test:
                self.send_status(412)
                return

        dl=DELETE(uri,dc)
        if dc.is_collection(uri):
            res=dl.delcol()
        else:
            res=dl.delone()

        if res:
            self.send_status(207,body=res)
        else:
            self.send_status(204)

    def do_PUT(self):
        dc=self.IFACE_CLASS

        # Handle If-Match
        if self.headers.has_key('If-Match'):
            test = False
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass
            for match in self.headers['If-Match'].split(','):
                if match == '*':
                    if dc.exists(uri):
                        test = True
                        break
                else:
                    if match == etag:
                        test = True
                        break
            if not test:
                self.send_status(412)
                return

        # Handle If-None-Match
        if self.headers.has_key('If-None-Match'):
            test = True
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass
            for match in self.headers['If-None-Match'].split(','):
                if match == '*':
                    if dc.exists(uri):
                        test = False
                        break
                else:
                    if match == etag:
                        test = False
                        break
            if not test:
                self.send_status(412)
                return

        # Handle expect
        expect = self.headers.get('Expect', '')
        if (expect.lower() == '100-continue' and
                self.protocol_version >= 'HTTP/1.1' and
                self.request_version >= 'HTTP/1.1'):
            self.send_status(100)
            self._flush()

        # read the body
        body=None
        if self.headers.has_key("Content-Length"):
            l=self.headers['Content-Length']
            body=self.rfile.read(atoi(l))
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        ct=None
        if self.headers.has_key("Content-Type"):
            ct=self.headers['Content-Type']
        try:
            location = dc.put(uri,body,ct)
        except DAV_Error, (ec,dd):
            self.send_status(ec)
            return
        headers = {}
        if location:
            headers['Location'] = location

        try:
            etag = dc.get_prop(location or uri, "DAV:", "getetag")
            headers['ETag'] = etag
        except:
            pass

        self.send_body(None, '201', 'Created', '', headers=headers)

    def do_COPY(self):
        """ copy one resource to another """
        try:
            self.copymove(COPY)
        except DAV_Error, (ec,dd):
            self.send_status(ec)

    def do_MOVE(self):
        """ move one resource to another """
        try:
            self.copymove(MOVE)
        except DAV_Error, (ec,dd):
            self.send_status(ec)

    def copymove(self,CLASS):
        """ common method for copying or moving objects """
        dc=self.IFACE_CLASS

        # get the source URI
        source_uri=urlparse.urljoin(self.get_baseuri(dc),self.path)
        source_uri=urllib.unquote(source_uri)

        # get the destination URI
        dest_uri=self.headers['Destination']
        dest_uri=urllib.unquote(dest_uri)

        # Overwrite?
        overwrite=1
        result_code=204
        if self.headers.has_key("Overwrite"):
            if self.headers['Overwrite']=="F":
                overwrite=None
                result_code=201

        # instanciate ACTION class
        cp=CLASS(dc,source_uri,dest_uri,overwrite)

        # Depth?
        d="infinity"
        if self.headers.has_key("Depth"):
            d=self.headers['Depth']
            
            if d!="0" and d!="infinity": 
                self.send_status(400)
                return
            
            if d=="0":  
                res=cp.single_action()
                self.send_status(res)
                return

        # now it only can be "infinity" but we nevertheless check for a collection
        if dc.is_collection(source_uri):
            try:
                res=cp.tree_action()
            except DAV_Error, (ec,dd):
                self.send_status(ec)
                return
        else:
            try:
                res=cp.single_action()
            except DAV_Error, (ec,dd):
                self.send_status(ec)
                return

        if res:
            self.send_body_chunks(res,207,self.responses[207][0],
                            self.responses[207][1],
                            ctype='text/xml; charset="utf-8"')
        else:
            self.send_status(result_code)

    def get_userinfo(self,user,pw):
        """ Dummy method which lets all users in """

        return 1

    def send_status(self,code=200,mediatype='text/xml;  charset="utf-8"', \
                                msg=None,body=None):

        if not msg: msg=self.responses[code][1]
        self.send_body(body,code,self.responses[code][0],msg,mediatype)

    def get_baseuri(self, dc):
        baseuri = dc.baseuri
        if self.headers.has_key('Host'):
            uparts = list(urlparse.urlparse(dc.baseuri))
            uparts[1] = self.headers['Host']
            baseuri = urlparse.urlunparse(uparts)
        return baseuri
