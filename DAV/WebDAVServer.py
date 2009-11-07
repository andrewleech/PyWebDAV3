#Copyright (c) 1999 Christian Scholz (ruebe@aachen.heimat.de)
#
#This library is free software; you can redistribute it and/or
#modify it under the terms of the GNU Library General Public
#License as published by the Free Software Foundation; either
#version 2 of the License, or (at your option) any later version.
#
#This library is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#Library General Public License for more details.
#
#You should have received a copy of the GNU Library General Public
#License along with this library; if not, write to the Free
#Software Foundation, Inc., 59 Temple Place - Suite 330, Boston,
#MA 02111-1307, USA

"""
    Python WebDAV Server.

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
import logging

from propfind import PROPFIND
from report import REPORT
from delete import DELETE
from davcopy import COPY
from davmove import MOVE

from utils import rfc1123_date, IfParser, tokenFinder
from string import atoi,split
from errors import *

from constants import DAV_VERSION_1, DAV_VERSION_2
from locks import LockManager
import gzip
import StringIO

log = logging.getLogger(__name__)

class DAVRequestHandler(AuthServer.BufferedAuthRequestHandler, LockManager):
    """Simple DAV request handler with

    - GET
    - HEAD
    - PUT
    - OPTIONS
    - PROPFIND
    - PROPPATCH
    - MKCOL
    - REPORT

    experimental
    - LOCK
    - UNLOCK

    It uses the resource/collection classes for serving and
    storing content.

    """

    server_version = "DAV/" + __version__
    encode_threshold = 1400 # common MTU

    def send_body(self,DATA,code,msg,desc,ctype='application/octet-stream',headers={}):
        """ send a body in one part """

        self.send_response(code,message=msg)
        self.send_header("Connection", "close")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header('Date', rfc1123_date())

        for a,v in headers.items():
            self.send_header(a,v)

        if DATA:
            if 'gzip' in self.headers.get('Accept-Encoding', '').split(',') \
                    and len(DATA) > self.encode_threshold:
                buffer = StringIO.StringIO()
                output = gzip.GzipFile(mode='wb', fileobj=buffer)
                output.write(DATA)
                output.close()
                buffer.seek(0)
                DATA = buffer.getvalue()
                self.send_header('Content-Encoding', 'gzip')

            self.send_header('Content-Length', len(DATA))
            self.send_header('Content-Type', ctype)
        else:
            self.send_header('Content-Length', 0)

        self.end_headers()
        if DATA:
            self._append(DATA)

    def send_body_chunks_if_http11(self, DATA, code, msg, desc, ctype='text/xml; encoding="utf-8"'):
        if self.request_version == 'HTTP/1.0':
            self.send_body(DATA, code, msg, desc, ctype)
        else:
            self.send_body_chunks(DATA, code, msg, desc, ctype)

    def send_body_chunks(self, DATA, code, msg, desc, ctype='text/xml; encoding="utf-8"'):
        """ send a body in chunks """

        self.responses[207]=(msg,desc)
        self.send_response(code,message=msg)
        self.send_header("Content-type", ctype)
        self.send_header("Connection", "close")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header('Date', rfc1123_date())

        if 'gzip' in self.headers.get('Accept-Encoding', '').split(',') \
                and len(DATA) > self.encode_threshold:
                buffer = StringIO.StringIO()
                output = gzip.GzipFile(mode='wb', fileobj=buffer)
                output.write(DATA)
                output.close()
                buffer.seek(0)
                DATA = buffer.getvalue()
                self.send_header('Content-Encoding', 'gzip')

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
        self.send_header("Content-Length", 0)

        if self._config.DAV.getboolean('lockemulation') is True:
            if self._config.DAV.getboolean('verbose') is True:
                log.info('Activated LOCK,UNLOCK emulation (experimental)')

            self.send_header('Allow', DAV_VERSION_2['options'])
            self.send_header('DAV', DAV_VERSION_2['version'])

        else:
            self.send_header('Allow', DAV_VERSION_1['options'])
            self.send_header('DAV', DAV_VERSION_1['version'])

        self.send_header('MS-Author-Via', 'DAV') # this is for M$
        self.end_headers()

    def _HEAD_GET(self, with_body=False):
        """ Returns headers and body for given resource """

        dc = self.IFACE_CLASS
        uri = urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.unquote(uri)

        headers = {}

        # get the last modified date (RFC 1123!)
        try:
            headers['Last-Modified'] = dc.get_prop(uri,"DAV:","getlastmodified")
        except DAV_NotFound: headers['Last-Modified'] = "Sun, 01 Dec 2038 00:00:00 GMT"

        # get the ETag if any
        try:
            headers['Etag'] = dc.get_prop(uri, "DAV:", "getetag")
        except DAV_NotFound: pass

        # get the content type
        try:
            content_type = dc.get_prop(uri,"DAV:","getcontenttype")
        except DAV_NotFound: content_type = "application/octet-stream"

        # get the data
        try:
            data = dc.get_data(uri)
        except DAV_Error, (ec,dd):
            self.send_status(ec)
            return 

        # send the data
        if with_body is False:
            data = None

        self.send_body(data, '200', "OK", "OK", content_type, headers)

    def do_HEAD(self):
        """ Send a HEAD response: Retrieves resource information w/o body """

        return self._HEAD_GET(with_body=False)

    def do_GET(self):
        """Serve a GET request."""

        return self._HEAD_GET(with_body=True)

    def do_TRACE(self):
        """ This will always fail because we can not reproduce HTTP requests. 
        We send back a 405=Method Not Allowed. """

        self.send_body(None, '405', 'Method Not Allowed', 'Method Not Allowed')

    def do_POST(self):
        """ Replacement for GET response. Not implemented here. """

        self.send_body(None, '405', 'Method Not Allowed', 'Method Not Allowed')

    def do_PROPFIND(self):
        """ Retrieve properties on defined resource. """

        dc = self.IFACE_CLASS

        # read the body containing the xml request
        # iff there is no body then this is an ALLPROP request
        body = None
        if self.headers.has_key('Content-Length'):
            l = self.headers['Content-Length']
            body = self.rfile.read(atoi(l))

        uri = urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.unquote(uri)

        pf = PROPFIND(uri, dc, self.headers.get('Depth', 'infinity'), body)

        try:
            DATA = '%s\n' % pf.createResponse()
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

        # work around MSIE DAV bug for creation and modified date
        # taken from Resource.py @ Zope webdav
        if (self.headers.get('User-Agent') ==
            'Microsoft Data Access Internet Publishing Provider DAV 1.1'):
            DATA = DATA.replace('<ns0:getlastmodified xmlns:ns0="DAV:">',
                                    '<ns0:getlastmodified xmlns:n="DAV:" xmlns:b="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/" b:dt="dateTime.rfc1123">')
            DATA = DATA.replace('<ns0:creationdate xmlns:ns0="DAV:">',
                                    '<ns0:creationdate xmlns:n="DAV:" xmlns:b="urn:uuid:c2f41010-65b3-11d1-a29f-00aa00c14882/" b:dt="dateTime.tz">')

        self.send_body_chunks_if_http11(DATA, '207','Multi-Status','Multiple responses')

    def do_REPORT(self):
        """ Query properties on defined resource. """

        dc = self.IFACE_CLASS

        # read the body containing the xml request
        # iff there is no body then this is an ALLPROP request
        body = None
        if self.headers.has_key('Content-Length'):
            l = self.headers['Content-Length']
            body = self.rfile.read(atoi(l))

        uri = urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.unquote(uri)

        rp = REPORT(uri, dc, self.headers.get('Depth', 'infinity'), body)

        try:
            DATA = '%s\n' % rp.createResponse()
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

        self.send_body_chunks_if_http11(DATA, '207','Multi-Status','Multiple responses')

    def do_MKCOL(self):
        """ create a new collection """

        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        try:
            dc.mkcol(uri)
            self.send_status(201)
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

    def do_DELETE(self):
        """ delete an resource """

        dc = self.IFACE_CLASS
        uri = urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.unquote(uri)

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

        # locked resources are not allowed to delete
        if self._l_isLocked(uri):
            return self.send_body(None, '423', 'Locked', 'Locked')

        dl = DELETE(uri,dc)
        if dc.is_collection(uri):
            res=dl.delcol()
            if res:
                self.send_status(207,body=res)
            else:
                self.send_status(204)
        else:
            res=dl.delone() or 204
            self.send_status(res)


    def do_PUT(self):
        dc=self.IFACE_CLASS
        uri=urlparse.urljoin(self.get_baseuri(dc), self.path)
        uri=urllib.unquote(uri)

        log.debug("do_PUT: uri = %s" % uri)
        log.debug('do_PUT: headers = %s' % self.headers)
        # Handle If-Match
        if self.headers.has_key('If-Match'):
            log.debug("do_PUT: If-Match %s" % self.headers['If-Match'])
            test = False
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass

            log.debug("do_PUT: etag = %s" % etag)

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
            log.debug("do_PUT: If-None-Match %s" % self.headers['If-None-Match'])

            test = True
            etag = None
            try:
                etag = dc.get_prop(uri, "DAV:", "getetag")
            except:
                pass

            log.debug("do_PUT: etag = %s" % etag)

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

        # locked resources are not allowed to be overwritten
        ifheader = self.headers.get('If')
        if (
            (self._l_isLocked(uri)) and
            (not ifheader)
        ):
            return self.send_body(None, '423', 'Locked', 'Locked')

        if ((self._l_isLocked(uri)) and (ifheader)):
            uri_token = self._l_getLockForUri(uri)
            taglist = IfParser(ifheader)
            found = False
            for tag in taglist:
                for listitem in tag.list:
                    token = tokenFinder(listitem)
                    if (
                        token and
                        (self._l_hasLock(token)) and
                        (self._l_getLock(token) == uri_token)
                    ):
                        found = True
                        break
                if found:
                    break
            if not found:
                return self.send_body(None, '423', 'Locked', 'Locked')

        # Handle expect
        expect = self.headers.get('Expect', '')
        if (expect.lower() == '100-continue' and
                self.protocol_version >= 'HTTP/1.1' and
                self.request_version >= 'HTTP/1.1'):
            self.send_status(100)
            self._flush()

        content_type = None
        if self.headers.has_key("Content-Type"):
            content_type = self.headers['Content-Type']

        headers = {}
        headers['Location'] = uri

        try:
            etag = dc.get_prop(uri, "DAV:", "getetag")
            headers['ETag'] = etag
        except:
            pass

        expect = self.headers.get('transfer-encoding', '')
        if (
            expect.lower() == 'chunked' and
            self.protocol_version >= 'HTTP/1.1' and
            self.request_version >= 'HTTP/1.1'
        ):
            self.send_body(None, '201', 'Created', '', headers=headers)
            self._flush()

            dc.put(uri, self._readChunkedData(), content_type)
        else:
            # read the body
            body=None
            if self.headers.has_key("Content-Length"):
                l=self.headers['Content-Length']
                log.debug("do_PUT: Content-Length = %s" % l)
                body=self.rfile.read(atoi(l))

            try:
                dc.put(uri, body, content_type)
            except DAV_Error, (ec,dd):
                return self.send_status(ec)


            self.send_body(None, '201', 'Created', '', headers=headers)

    def _readChunkedData(self):
        l = int(self.rfile.readline(), 16)
        while l > 0:
            buf = self.rfile.read(l)
            yield buf
            self.rfile.readline()
            l = int(self.rfile.readline(), 16)

    def do_COPY(self):
        """ copy one resource to another """
        try:
            self.copymove(COPY)
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

    def do_MOVE(self):
        """ move one resource to another """
        try:
            self.copymove(MOVE)
        except DAV_Error, (ec,dd):
            return self.send_status(ec)

    def copymove(self,CLASS):
        """ common method for copying or moving objects """
        dc=self.IFACE_CLASS

        # get the source URI
        source_uri=urlparse.urljoin(self.get_baseuri(dc),self.path)
        source_uri=urllib.unquote(source_uri)

        # get the destination URI
        dest_uri=self.headers['Destination']
        dest_uri=urllib.unquote(dest_uri)

        # check locks on source and dest
        if self._l_isLocked(source_uri) or self._l_isLocked(dest_uri):
            return self.send_body(None, '423', 'Locked', 'Locked')

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
            self.send_body_chunks_if_http11(res,207,self.responses[207][0],
                            self.responses[207][1],
                            ctype='text/xml; charset="utf-8"')
        else:
            self.send_status(result_code)

    def get_userinfo(self,user,pw):
        """ Dummy method which lets all users in """

        return 1

    def send_status(self,code=200,mediatype='text/xml;  charset="utf-8"', \
                                msg=None,body=None):

        if not msg:
            msg=self.responses.get(code, ['', ''])[1]

        self.send_body(body,code,self.responses.get(code, [''])[0],msg,mediatype)

    def get_baseuri(self, dc):
        baseuri = dc.baseuri
        if self.headers.has_key('Host'):
            uparts = list(urlparse.urlparse(dc.baseuri))
            uparts[1] = self.headers['Host']
            baseuri = urlparse.urlunparse(uparts)
        return baseuri

    def log_message(self, *args):
        AuthServer.BufferedAuthRequestHandler.log_message(self, 
            *tuple(('- %s - ' + args[0],) + (self.headers.get('User-Agent', '?'),) + args[1:])
        )
