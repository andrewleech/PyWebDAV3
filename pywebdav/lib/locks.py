import time
import urllib.parse
import uuid

import logging

log = logging.getLogger(__name__)

import xml.dom
from xml.dom import minidom

from .utils import rfc1123_date, IfParser, tokenFinder

tokens_to_lock = {}  # {token_string: LockItem}
uris_to_locks = {}   # {uri: [LockItem, ...]} - supports multiple shared locks

class LockManager:
    """ Implements the locking backend and serves as MixIn for DAVRequestHandler """

    def _init_locks(self):
        return tokens_to_lock, uris_to_locks

    def _l_isLocked(self, uri):
        tokens, uris = self._init_locks()
        return uri in uris and len(uris[uri]) > 0

    def _l_hasLock(self, token):
        tokens, uris = self._init_locks()
        return token in tokens

    def _l_getLockForUri(self, uri):
        """Get the first lock for a URI (for backward compatibility)"""
        tokens, uris = self._init_locks()
        locks = uris.get(uri, [])
        return locks[0] if locks else None

    def _l_getLocksForUri(self, uri):
        """Get all locks for a URI (supports shared locks)"""
        tokens, uris = self._init_locks()
        return uris.get(uri, [])

    def _l_getLock(self, token):
        tokens, uris = self._init_locks()
        return tokens.get(token, None)

    def _l_delLock(self, token):
        tokens, uris = self._init_locks()
        if token in tokens:
            lock = tokens[token]
            uri = lock.uri
            # Remove from uri -> locks mapping
            if uri in uris:
                uris[uri] = [l for l in uris[uri] if l.token != token]
                # Clean up empty list
                if not uris[uri]:
                    del uris[uri]
            # Remove from token -> lock mapping
            del tokens[token]

    def _l_setLock(self, lock):
        tokens, uris = self._init_locks()
        tokens[lock.token] = lock
        # Append to list of locks for this URI (supports shared locks)
        if lock.uri not in uris:
            uris[lock.uri] = []
        uris[lock.uri].append(lock)

    def _lock_unlock_parse(self, body):
        doc = minidom.parseString(body)

        data = {}
        info = doc.getElementsByTagNameNS('DAV:', 'lockinfo')[0]
        data['lockscope'] = info.getElementsByTagNameNS('DAV:', 'lockscope')[0]\
                                .firstChild.localName
        data['locktype'] = info.getElementsByTagNameNS('DAV:', 'locktype')[0]\
                                .firstChild.localName
        data['lockowner'] = info.getElementsByTagNameNS('DAV:', 'owner')
        return data

    def _lock_unlock_create(self, uri, creator, depth, data):
        lock = LockItem(uri, creator, **data)
        iscollection = uri[-1] == '/' # very dumb collection check

        result = ''
        if depth == 'infinity' and iscollection:
            # locking of children/collections not yet supported
            pass

        # Check if we can add this lock based on existing locks
        existing_locks = self._l_getLocksForUri(uri)

        if existing_locks:
            # Resource already has locks - check compatibility
            for existing in existing_locks:
                # If any existing lock is exclusive, reject
                if existing.lockscope == 'exclusive':
                    log.info(f'Cannot lock {uri}: exclusive lock exists')
                    raise Exception('Resource is exclusively locked')

                # If we're trying to get exclusive lock but shared locks exist, reject
                if lock.lockscope == 'exclusive':
                    log.info(f'Cannot get exclusive lock on {uri}: shared locks exist')
                    raise Exception('Resource has shared locks')

            # All existing locks are shared and new lock is shared - OK
            # (This path only reached if all above conditions pass)

        # No conflicts - set the lock
        self._l_setLock(lock)

        # because we do not handle children we leave result empty
        return lock.token, result

    def do_UNLOCK(self):
        """ Unlocks given resource """

        dc = self.IFACE_CLASS

        if self._config.DAV.getboolean('verbose') is True:
            log.info('UNLOCKing resource %s' % self.headers)

        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri)

        # check lock token - must contain a dash
        if not self.headers.get('Lock-Token', '').find('-')>0:
            return self.send_status(400)

        token = tokenFinder(self.headers.get('Lock-Token'))
        if self._l_isLocked(uri):
            self._l_delLock(token)

        self.send_body(None, 204, 'OK', 'OK')

    def do_LOCK(self):
        """ Locking is implemented via in-memory caches. No data is written to disk.  """

        dc = self.IFACE_CLASS

        log.info('LOCKing resource %s' % self.headers)

        body = None
        if 'Content-Length' in self.headers:
            l = self.headers['Content-Length']
            body = self.rfile.read(int(l))

        depth = self.headers.get('Depth', 'infinity')

        uri = urllib.parse.urljoin(self.get_baseuri(dc), self.path)
        uri = urllib.parse.unquote(uri)
        log.info('do_LOCK: uri = %s' % uri)

        ifheader = self.headers.get('If')
        alreadylocked = self._l_isLocked(uri)
        log.info('do_LOCK: alreadylocked = %s' % alreadylocked)

        if body and alreadylocked:
            # Full LOCK request but resource already locked
            self.responses[423] = ('Locked', 'Already locked')
            return self.send_status(423)

        elif body and not ifheader:
            # LOCK with XML information
            data = self._lock_unlock_parse(body)
            token, result = self._lock_unlock_create(uri, 'unknown', depth, data)

            if result:
                self.send_body(bytes(result, 'utf-8'), 207, 'Error', 'Error',
                                'text/xml; charset="utf-8"')

            else:
                lock = self._l_getLock(token)
                self.send_body(bytes(lock.asXML(), 'utf-8'), 200, 'OK', 'OK',
                                'text/xml; charset="utf-8"',
                                {'Lock-Token' : '<opaquelocktoken:%s>' % token})


        else:
            # refresh request - refresh lock timeout
            taglist = IfParser(ifheader)
            found = 0
            for tag in taglist:
                for listitem in tag.list:
                    token = tokenFinder(listitem)
                    if token and self._l_hasLock(token):
                        lock = self._l_getLock(token)
                        timeout = self.headers.get('Timeout', 'Infinite')
                        lock.setTimeout(timeout) # automatically refreshes
                        found = 1

                        self.send_body(bytes(lock.asXML(), 'utf-8'),
                                        200, 'OK', 'OK', 'text/xml; encoding="utf-8"')
                        break
                if found:
                    break

            # we didn't find any of the tokens mentioned - means
            # that table was cleared or another error
            if not found:
                self.send_status(412) # precondition failed

class LockItem:
    """ Lock with support for exclusive write locks. Some code taken from
    webdav.LockItem from the Zope project. """

    def __init__(self, uri, creator, lockowner, depth=0, timeout='Infinite',
                    locktype='write', lockscope='exclusive', token=None, **kw):

        self.uri = uri
        self.creator = creator
        self.owner = lockowner
        self.depth = depth
        self.timeout = timeout
        self.locktype = locktype
        self.lockscope = lockscope
        self.token = token and token or self.generateToken()
        self.modified = time.time()

    def getModifiedTime(self):
        return self.modified

    def refresh(self):
        self.modified = time.time()

    def isValid(self):
        now = time.time()
        modified = self.modified
        timeout = self.timeout
        return (modified + timeout) > now

    def generateToken(self):
        return str(uuid.uuid4())

    def getTimeoutString(self):
        t = str(self.timeout)
        if t[-1] == 'L': t = t[:-1]
        return 'Second-%s' % t

    def setTimeout(self, timeout):
        self.timeout = timeout
        self.modified = time.time()

    def asXML(self, namespace='d', discover=False):
        owner_str = ''
        if isinstance(self.owner, str):
            owner_str = self.owner
        elif isinstance(self.owner, xml.dom.minicompat.NodeList) and len(self.owner):
            owner_str = "".join([node.toxml() for node in self.owner[0].childNodes])

        token = self.token
        base = ('<%(ns)s:activelock>\n'
             '  <%(ns)s:locktype><%(ns)s:%(locktype)s/></%(ns)s:locktype>\n'
             '  <%(ns)s:lockscope><%(ns)s:%(lockscope)s/></%(ns)s:lockscope>\n'
             '  <%(ns)s:depth>%(depth)s</%(ns)s:depth>\n'
             '  <%(ns)s:owner>%(owner)s</%(ns)s:owner>\n'
             '  <%(ns)s:timeout>%(timeout)s</%(ns)s:timeout>\n'
             '  <%(ns)s:locktoken>\n'
             '   <%(ns)s:href>opaquelocktoken:%(locktoken)s</%(ns)s:href>\n'
             '  </%(ns)s:locktoken>\n'
             ' </%(ns)s:activelock>\n'
             ) % {
               'ns': namespace,
               'locktype': self.locktype,
               'lockscope': self.lockscope,
               'depth': self.depth,
               'owner': owner_str,
               'timeout': self.getTimeoutString(),
               'locktoken': token,
               }

        if discover is True:
            return base

        s = """<?xml version="1.0" encoding="utf-8" ?>
<d:prop xmlns:d="DAV:">
 <d:lockdiscovery>
  %s
 </d:lockdiscovery>
</d:prop>""" % base

        return s
