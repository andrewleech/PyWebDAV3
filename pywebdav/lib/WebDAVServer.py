"""DAV HTTP Server

This module builds on BaseHTTPServer and implements DAV commands

"""
from __future__ import absolute_import
from . import AuthServer
from six.moves import urllib
import logging

from .propfind import PROPFIND
from .report import REPORT
from .delete import DELETE
from .davcopy import COPY
from .davmove import MOVE

from .utils import rfc1123_date, IfParser, tokenFinder
from .errors import DAV_Error, DAV_NotFound

from .constants import DAV_VERSION_1, DAV_VERSION_2
from .locks import LockManager
import gzip
import io

from pywebdav import __version__

from xml.parsers.expat import ExpatError
import six

log = logging.getLogger(__name__)

BUFFER_SIZE = 128 * 1000  # 128 Ko


class DAVRequestHandler(AuthServer.AuthRequestHandler, LockManager):
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
    encode_threshold = 1400  # common MTU

    def send_body(self, DATA, code=None, msg=None, desc=None,
                  ctype='application/octet-stream', headers={}):
        """ send a body in one part """
        log.debug("Use send_body method")

        self.send_response(code, message=msg)
        self.send_header("Connection", "close")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header('Date', rfc1123_date())

        self._send_dav_version()

        for a, v in headers.items():
            v = v.encode() if isinstance(v, six.text_type) else v
            self.send_header(a, v)

        if DATA:
            try:
                if 'gzip' in self.headers.get('Accept-Encoding', '').split(',') \
                        and len(DATA) > self.encode_threshold:
                    buffer = io.BytesIO()
                    output = gzip.GzipFile(mode='wb', fileobj=buffer)
                    if isinstance(DATA, str) or isinstance(DATA, six.text_type):
                        output.write(DATA)
                    else:
                        for buf in DATA:
                            output.write(buf)
                    output.close()
                    buffer.seek(0)
                    DATA = buffer.getvalue()
                    self.send_header('Content-Encoding', 'gzip')

                self.send_header('Content-Length', len(DATA))
                self.send_header('Content-Type', ctype)
            except Exception as ex:
                log.exception(ex)
        else:
            self.send_header('Content-Length', 0)

        self.end_headers()
        if DATA:
            if isinstance(DATA, str) or isinstance(DATA, six.text_type) or isinstance(DATA, bytes):
                log.debug("Don't use iterator")
                self.wfile.write(DATA)
            else:
                if self._config.DAV.getboolean('http_response_use_iterator'):
                    # Use iterator to reduce using memory
                    log.debug("Use iterator")
                    for buf in DATA:
                        self.wfile.write(buf)
                        self.wfile.flush()
                else:
                    # Don't use iterator, it's a compatibility option
                    log.debug("Don't use iterator")
                    res = DATA.read()
                    if isinstance(res,bytes):
                        self.wfile.write(res)
                    else:
                        self.wfile.write(res.encode('utf8'))
        return None

    def send_body_chunks_if_http11(self, DATA, code, msg=None, desc=None,
                                   ctype='text/xml; encoding="utf-8"',
                                   headers={}):
        if (self.request_version == 'HTTP/1.0' or
            not self._config.DAV.getboolean('chunked_http_response')):
            self.send_body(DATA, code, msg, desc, ctype, headers)
        else:
            self.send_body_chunks(DATA, code, msg, desc, ctype, headers)

    def send_body_chunks(self, DATA, code, msg=None, desc=None,
                         ctype='text/xml"', headers={}):
        """ send a body in chunks """

        self.responses[207] = (msg, desc)
        self.send_response(code, message=msg)
        self.send_header("Content-type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header('Date', rfc1123_date())

        self._send_dav_version()

        for a, v in headers.items():
            self.send_header(a, v)

        GZDATA = None
        if DATA:
            if ('gzip' in self.headers.get('Accept-Encoding', '').split(',')
                and len(DATA) > self.encode_threshold):
                buffer = io.BytesIO()
                output = gzip.GzipFile(mode='wb', fileobj=buffer)
                if isinstance(DATA, bytes):
                    output.write(DATA)
                else:
                    for buf in DATA:
                        buf = buf.encode() if isinstance(buf, six.text_type) else buf
                        output.write(buf)
                output.close()
                buffer.seek(0)
                GZDATA = buffer.getvalue()
                self.send_header('Content-Encoding', 'gzip')

            self.send_header('Content-Length', len(DATA))
            self.send_header('Content-Type', ctype)

        else:
            self.send_header('Content-Length', 0)

        self.end_headers()

        if GZDATA:
            self.wfile.write(GZDATA)

        elif DATA:
            DATA = DATA.encode() if isinstance(DATA, six.text_type) else DATA
            if isinstance(DATA, six.binary_type):
                self.wfile.write(b"%s\r\n" % hex(len(DATA))[2:].encode())
                self.wfile.write(DATA)
                self.wfile.write(b"\r\n")
                self.wfile.write(b"0\r\n")
                self.wfile.write(b"\r\n")
            else:
                if self._config.DAV.getboolean('http_response_use_iterator'):
                    # Use iterator to reduce using memory
                    for buf in DATA:
                        buf = buf.encode() if isinstance(buf, six.text_type) else buf
                        self.wfile.write((hex(len(buf))[2:] + "\r\n").encode())
                        self.wfile.write(buf)
                        self.wfile.write(b"\r\n")

                    self.wfile.write(b"0\r\n")
                    self.wfile.write(b"\r\n")
                else:
                    # Don't use iterator, it's a compatibility option
                    self.wfile.write((hex(len(DATA))[2:] + "\r\n").encode())
                    self.wfile.write(DATA.read())
                    self.wfile.write(b"\r\n")
                    self.wfile.write(b"0\r\n")
                    self.wfile.write(b"\r\n")

    def _send_dav_version(self):
        if self._config.DAV.getboolean('lockemulation'):
            self.send_header('DAV', DAV_VERSION_2['version'])
        else:
            self.send_header('DAV', DAV_VERSION_1['version'])

    ### HTTP METHODS called by the server

    def do_OPTIONS(self):
        """return the list of capabilities """

        self.send_response(200)
        self.send_header("Content-Length", 0)

        if self._config.DAV.getboolean('lockemulation'):
            self.send_header('Allow', DAV_VERSION_2['options'])
        else:
            self.send_header('Allow', DAV_VERSION_1['options'])

        self._send_dav_version()

        self.send_header('MS-Author-Via', 'DAV')  # this is for M$
        self.end_headers()

    def _HEAD_GET(self, with_body=False):
        """ Returns headers and body for given resource """

        dc = self.IFACE_CLASS
        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        headers = {}

        # get the last modified date (RFC 1123!)
        try:
            headers['Last-Modified'] = dc.get_prop(
                uri, "DAV:", "getlastmodified")
        except DAV_NotFound:
            pass

        # get the ETag if any
        try:
            headers['Etag'] = dc.get_prop(uri, "DAV:", "getetag")
        except DAV_NotFound:
            pass

        # get the content type
        try:
            if uri.endswith(b'/'):
                # we could do away with this very non-local workaround for
                # _get_listing if the data could have a type attached
                content_type = 'text/html;charset=utf-8'
            else:
                content_type = dc.get_prop(uri, "DAV:", "getcontenttype")
        except DAV_NotFound:
            content_type = "application/octet-stream"

        range = None
        status_code = 200
        if 'Range' in self.headers:
            p = self.headers['Range'].find("bytes=")
            if p != -1:
                range = self.headers['Range'][p + 6:].split("-")
                status_code = 206

        # get the data
        try:
            data = dc.get_data(uri, range)
        except DAV_Error as error:
            (ec, dd) = error.args
            self.send_status(ec)
            return ec

        # send the data
        if with_body is False:
            data = None

        if isinstance(data, str) or isinstance(data, six.text_type):
            self.send_body(data, status_code, None, None, content_type,
                           headers)
        else:
            headers['Keep-Alive'] = 'timeout=15, max=86'
            headers['Connection'] = 'Keep-Alive'
            self.send_body_chunks_if_http11(data, status_code, None, None,
                                            content_type, headers)

        return status_code

    def do_HEAD(self):
        """ Send a HEAD response: Retrieves resource information w/o body """

        return self._HEAD_GET(with_body=False)

    def do_GET(self):
        """Serve a GET request."""

        log.debug(self.headers)

        try:
            status_code = self._HEAD_GET(with_body=True)
            self.log_request(status_code)
            return status_code
        except IOError as e:
            if e.errno == 32:
                self.log_request(206)
            else:
                raise

    def do_TRACE(self):
        """ This will always fail because we can not reproduce HTTP requests.
        We send back a 405=Method Not Allowed. """

        self.send_body(None, 405, 'Method Not Allowed', 'Method Not Allowed')

    def do_POST(self):
        """ Replacement for GET response. Not implemented here. """

        self.send_body(None, 405, 'Method Not Allowed', 'Method Not Allowed')

    def do_PROPPATCH(self):
        # currently unsupported
        return self.send_status(423)

    def do_PROPFIND(self):
        """ Retrieve properties on defined resource. """

        dc = self.IFACE_CLASS

        # read the body containing the xml request
        # iff there is no body then this is an ALLPROP request
        body = None
        if 'Content-Length' in self.headers:
            l = self.headers['Content-Length']
            body = self.rfile.read(int(l))

        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        try:
            pf = PROPFIND(uri, dc, self.headers.get('Depth', 'infinity'), body)
        except ExpatError:
            # parse error
            return self.send_status(400)

        try:
            DATA = b'%s\n' % pf.createResponse()
        except DAV_Error as error:
            (ec, dd) = error.args
            return self.send_status(ec)

        # work around MSIE DAV bug for creation and modified date
        # taken from Resource.py @ Zope webdav
        if (self.headers.get('User-Agent') ==
            'Microsoft Data Access Internet Publishing Provider DAV 1.1'):
            DATA = DATA.replace(b'<ns0:getlastmodified xmlns:ns0="DAV:">',
                                b'<ns0:getlastmodified xmlns:n="DAV:" '
                                b'xmlns:b="urn:uuid:'
                                b'c2f41010-65b3-11d1-a29f-00aa00c14882/" '
                                b'b:dt="dateTime.rfc1123">')
            DATA = DATA.replace(b'<ns0:creationdate xmlns:ns0="DAV:">',
                                b'<ns0:creationdate xmlns:n="DAV:" '
                                b'xmlns:b="urn:uuid:'
                                b'c2f41010-65b3-11d1-a29f-00aa00c14882/" '
                                b'b:dt="dateTime.tz">')

        self.send_body_chunks_if_http11(DATA, 207, 'Multi-Status',
                                        'Multiple responses')

    def do_REPORT(self):
        """ Query properties on defined resource. """

        dc = self.IFACE_CLASS

        # read the body containing the xml request
        # iff there is no body then this is an ALLPROP request
        body = None
        if 'Content-Length' in self.headers:
            l = self.headers['Content-Length']
            body = self.rfile.read(int(l))

        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        rp = REPORT(uri, dc, self.headers.get('Depth', '0'), body)

        try:
            DATA = '%s\n' % rp.createResponse()
        except DAV_Error as error:
            (ec, dd) = error.args
            return self.send_status(ec)

        self.send_body_chunks_if_http11(DATA, 207, 'Multi-Status',
                                        'Multiple responses')

    def do_MKCOL(self):
        """ create a new collection """

        # according to spec body must be empty
        body = None
        if 'Content-Length' in self.headers:
            l = self.headers['Content-Length']
            body = self.rfile.read(int(l))

        if body:
            return self.send_status(415)

        dc = self.IFACE_CLASS
        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        try:
            dc.mkcol(uri)
            self.send_status(201)
            self.log_request(201)
        except DAV_Error as error:
            (ec, dd) = error.args
            self.log_request(ec)
            return self.send_status(ec)

    def do_DELETE(self):
        """ delete an resource """

        dc = self.IFACE_CLASS
        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        # hastags not allowed
        if uri.find(b'#') >= 0:
            return self.send_status(404)

        # locked resources are not allowed to delete
        if self._l_isLocked(uri):
            return self.send_body(None, 423, 'Locked', 'Locked')

        # Handle If-Match
        if 'If-Match' in self.headers:
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
                self.log_request(412)
                return

        # Handle If-None-Match
        if 'If-None-Match' in self.headers:
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
                self.log_request(412)
                return

        try:
            dl = DELETE(uri, dc)
            if dc.is_collection(uri):
                res = dl.delcol()
                if res:
                    self.send_status(207, body=res)
                else:
                    self.send_status(204)
            else:
                res = dl.delone() or 204
                self.send_status(res)
        except DAV_NotFound:
            self.send_body(None, 404, 'Not Found', 'Not Found')

    def do_PUT(self):
        dc = self.IFACE_CLASS
        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri).encode()

        log.debug("do_PUT: uri = %s" % uri)
        log.debug('do_PUT: headers = %s' % self.headers)
        # Handle If-Match
        if 'If-Match' in self.headers:
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
                self.log_request(412)
                return

        # Handle If-None-Match
        if 'If-None-Match' in self.headers:
            log.debug("do_PUT: If-None-Match %s" %
                      self.headers['If-None-Match'])

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
                self.log_request(412)
                return

        # locked resources are not allowed to be overwritten
        ifheader = self.headers.get('If')
        if (
            (self._l_isLocked(uri)) and
            (not ifheader)
        ):
            return self.send_body(None, 423, 'Locked', 'Locked')

        if self._l_isLocked(uri) and ifheader:
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
                res = self.send_body(None, 423, 'Locked', 'Locked')
                self.log_request(423)
                return res

        # Handle expect
        expect = self.headers.get('Expect', '')
        if (expect.lower() == '100-continue' and
                self.protocol_version >= 'HTTP/1.1' and
                self.request_version >= 'HTTP/1.1'):
            self.send_status(100)

        content_type = None
        if 'Content-Type' in self.headers:
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
            self.send_body(None, 201, 'Created', '', headers=headers)

            dc.put(uri, self._readChunkedData(), content_type)
        else:
            # read the body
            body = None
            if 'Content-Length' in self.headers:
                l = self.headers['Content-Length']
                log.debug("do_PUT: Content-Length = %s" % l)
                body = self._readNoChunkedData(int(l))
            else:
                log.debug("do_PUT: Content-Length = empty")

            try:
                dc.put(uri, body, content_type)
            except DAV_Error as error:
                (ec, dd) = error.args
                return self.send_status(ec)

            self.send_body(None, 201, 'Created', '', headers=headers)
            self.log_request(201)

    def _readChunkedData(self):
        l = int(self.rfile.readline(), 16)
        while l > 0:
            buf = self.rfile.read(l)
            yield buf
            self.rfile.readline()
            l = int(self.rfile.readline(), 16)

    def _readNoChunkedData(self, content_length):
        if self._config.DAV.getboolean('http_request_use_iterator'):
            # Use iterator to reduce using memory
            return self.__readNoChunkedDataWithIterator(content_length)
        else:
            # Don't use iterator, it's a compatibility option
            return self.__readNoChunkedDataWithoutIterator(content_length)

    def __readNoChunkedDataWithIterator(self, content_length):
        while True:
            if content_length > BUFFER_SIZE:
                buf = self.rfile.read(BUFFER_SIZE)
                content_length -= BUFFER_SIZE
                yield buf
            else:
                buf = self.rfile.read(content_length)
                yield buf
                break

    def __readNoChunkedDataWithoutIterator(self, content_length):
        return self.rfile.read(content_length)

    def do_COPY(self):
        """ copy one resource to another """
        try:
            self.copymove(COPY)
        except DAV_Error as error:
            (ec, dd) = error.args
            return self.send_status(ec)

    def do_MOVE(self):
        """ move one resource to another """
        try:
            self.copymove(MOVE)
        except DAV_Error as error:
            (ec, dd) = error.args
            return self.send_status(ec)

    def copymove(self, CLASS):
        """ common method for copying or moving objects """
        dc = self.IFACE_CLASS

        # get the source URI
        source_uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        source_uri = urllib.parse.unquote(source_uri).encode()

        # get the destination URI
        dest_uri = self.headers['Destination']
        dest_uri = urllib.parse.unquote(dest_uri).encode()

        # check locks on source and dest
        if self._l_isLocked(source_uri) or self._l_isLocked(dest_uri):
            return self.send_body(None, 423, 'Locked', 'Locked')

        # Overwrite?
        overwrite = 1
        result_code = 204
        if 'Overwrite' in self.headers:
            if self.headers['Overwrite'] == "F":
                overwrite = None
                result_code = 201

        # instanciate ACTION class
        cp = CLASS(dc, source_uri, dest_uri, overwrite)

        # Depth?
        d = "infinity"
        if 'Depth' in self.headers:
            d = self.headers['Depth']

            if d != "0" and d != "infinity":
                self.send_status(400)
                return

            if d == "0":
                res = cp.single_action()
                self.send_status(res or 201)
                return

        # now it only can be "infinity" but we nevertheless check for a
        # collection
        if dc.is_collection(source_uri):
            try:
                res = cp.tree_action()
            except DAV_Error as error:
                (ec, dd) = error.args
                self.send_status(ec)
                return
        else:
            try:
                res = cp.single_action()
            except DAV_Error as error:
                (ec, dd) = error.args
                self.send_status(ec)
                return

        if res:
            self.send_body_chunks_if_http11(res, 207, self.responses[207][0],
                                            self.responses[207][1],
                                            ctype='text/xml; charset="utf-8"')
        else:
            self.send_status(result_code)

    def get_userinfo(self, user, pw):
        """ Dummy method which lets all users in """
        return 1

    def send_status(self, code=200, mediatype='text/xml;  charset="utf-8"',
                    msg=None, body=None):

        if not msg:
            msg = self.responses.get(code, ['', ''])[1]

        self.send_body(body, code, self.responses.get(code, [''])[0], msg,
                       mediatype)

    def get_baseuri(self, dc):
        baseuri = dc.baseuri
        if 'Host' in self.headers:
            uparts = list(urllib.parse.urlparse(dc.baseuri))
            uparts[1] = self.headers['Host']
            baseuri = urllib.parse.urlunparse(uparts)
        return baseuri
