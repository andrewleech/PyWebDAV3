import os
import textwrap
import time
import logging
import types
import shutil
import json
from io import StringIO
import urllib.parse
from pywebdav.lib.constants import COLLECTION, OBJECT
from pywebdav.lib.errors import DAV_Error, DAV_Forbidden, DAV_NotFound, DAV_Requested_Range_Not_Satisfiable, DAV_Secret
from pywebdav.lib.iface import dav_interface
from pywebdav.lib.davcmd import copyone, copytree, moveone, movetree, delone, deltree
from html import escape

log = logging.getLogger(__name__)

BUFFER_SIZE = 128 * 1000
# include magic support to correctly determine mimetypes
MAGIC_AVAILABLE = False
try:
    import mimetypes
    MAGIC_AVAILABLE = True
    log.info('Mimetype support ENABLED')
except ImportError:
    log.info('Mimetype support DISABLED')
    pass

class Resource:
    # XXX this class is ugly
    def __init__(self, fp, file_size):
        self.__fp = fp
        self.__file_size = file_size

    def __len__(self):
        return self.__file_size

    def __iter__(self):
        while 1:
            data = self.__fp.read(BUFFER_SIZE)
            if not data:
                break
            yield data
            time.sleep(0.005)
        self.__fp.close()

    def read(self, length = 0):
        if length == 0:
            length = self.__file_size

        data = self.__fp.read(length)
        return data


class FilesystemHandler(dav_interface):
    """
    Model a filesystem for DAV

    This class models a regular filesystem for the DAV server

    The basic URL will be http://localhost/
    And the underlying filesystem will be /tmp

    Thus http://localhost/gfx/pix will lead
    to /tmp/gfx/pix

    """

    def __init__(self, directory, uri, verbose=False):
        self.setDirectory(directory)
        self.setBaseURI(uri)

        # should we be verbose?
        self.verbose = verbose
        log.info('Initialized with %s %s' % (directory, uri))

    def setDirectory(self, path):
        """ Sets the directory """

        if not os.path.isdir(path):
            raise Exception('%s not must be a directory!' % path)

        self.directory = path

    def setBaseURI(self, uri):
        """ Sets the base uri """

        self.baseuri = uri

    def uri2local(self,uri):
        """ map uri in baseuri and local part """
        uparts=urllib.parse.urlparse(uri)
        fileloc=uparts[2][1:]
        filename=os.path.join(self.directory, fileloc)
        filename=os.path.normpath(filename)
        return filename

    def local2uri(self,filename):
        """ map local filename to self.baseuri """

        pnum=len(self.directory.replace("\\","/").split("/"))
        parts=filename.replace("\\","/").split("/")[pnum:]
        sparts="/"+"/".join(parts)
        uri=urllib.parse.urljoin(self.baseuri,sparts)
        return uri


    def get_childs(self, uri, filter=None):
        """ return the child objects as self.baseuris for the given URI """

        fileloc=self.uri2local(uri)
        filelist=[]

        if os.path.exists(fileloc):
            if os.path.isdir(fileloc):
                try:
                    files=os.listdir(fileloc)
                except:
                    raise DAV_NotFound

                for file in files:
                    newloc=os.path.join(fileloc,file)
                    filelist.append(self.local2uri(newloc))

                log.info('get_childs: Childs %s' % filelist)

        return filelist

    def _get_listing(self, path):
        """Return a directory listing similar to http.server's"""

        template = textwrap.dedent("""
            <html>
                <head><title>Directory listing for {path}</title></head>
                <body>
                    <h1>Directory listing for {path}</h1>
                    <hr>
                    <ul>
                    {items}
                    </ul>
                    <hr>
                </body>
            </html>
            """)
        escapeditems = (escape(i) + ('/' if os.path.isdir(os.path.join(path, i)) else '') for i in os.listdir(path) if not i.startswith('.'))
        htmlitems = "\n".join('<li><a href="{i}">{i}</a></li>'.format(i=i) for i in escapeditems)

        return template.format(items=htmlitems, path=path)

    def get_data(self,uri, range = None):
        """ return the content of an object """

        path=self.uri2local(uri)
        if os.path.exists(path):
            if os.path.isfile(path):
                file_size = os.path.getsize(path)
                if range is None:
                    fp=open(path,"rb")
                    log.info('Serving content of %s' % uri)
                    return Resource(fp, file_size)
                else:
                    if range[1] == '':
                        range[1] = file_size
                    else:
                        range[1] = int(range[1])

                    if range[0] == '':
                        range[0] = file_size - range[1]
                    else:
                        range[0] = int(range[0])

                    if range[0] > file_size:
                        raise DAV_Requested_Range_Not_Satisfiable

                    if range[1] > file_size:
                        range[1] = file_size

                    fp=open(path,"rb")
                    fp.seek(range[0])
                    log.info('Serving range %s -> %s content of %s' % (range[0], range[1], uri))
                    return Resource(fp, range[1] - range[0])
            elif os.path.isdir(path):
                msg = self._get_listing(path)
                return Resource(StringIO(msg), len(msg))
            else:
                # also raise an error for collections
                # don't know what should happen then..
                log.info('get_data: %s not found' % path)

        raise DAV_NotFound

    def _get_dav_resourcetype(self,uri):
        """ return type of object """
        path=self.uri2local(uri)
        if os.path.isfile(path):
            return OBJECT

        elif os.path.isdir(path):
            return COLLECTION

        raise DAV_NotFound

    def _get_dav_displayname(self,uri):
        raise DAV_Secret    # do not show

    def _get_dav_getcontentlength(self,uri):
        """ return the content length of an object """
        path=self.uri2local(uri)
        if os.path.exists(path):
            if os.path.isfile(path):
                s=os.stat(path)
                return str(s[6])

        return '0'

    def get_lastmodified(self,uri):
        """ return the last modified date of the object """
        path=self.uri2local(uri)
        if os.path.exists(path):
            s=os.stat(path)
            date=s[8]
            return date

        raise DAV_NotFound

    def get_creationdate(self,uri):
        """ return the creation date of the object """
        path=self.uri2local(uri)
        if os.path.exists(path):
            s=os.stat(path)
            date=s[9]
            return date

        raise DAV_NotFound

    def _get_dav_getcontenttype(self, uri):
        """ find out yourself! """

        path=self.uri2local(uri)
        if os.path.exists(path):
            if os.path.isfile(path):
                if MAGIC_AVAILABLE is False \
                        or self.mimecheck is False:
                    return 'application/octet-stream'
                else:
                    ret, encoding = mimetypes.guess_type(path)

                    # for non mimetype related result we
                    # simply return an appropriate type
                    if ret.find('/')==-1:
                        if ret.find('text')>=0:
                            return 'text/plain'
                        else:
                            return 'application/octet-stream'
                    else:
                        return ret

            elif os.path.isdir(path):
                return "httpd/unix-directory"

        raise DAV_NotFound('Could not find %s' % path)

    def put(self, uri, data, content_type=None):
        """ put the object into the filesystem """
        path=self.uri2local(uri)
        try:
            with open(path, "bw+") as fp:
                if isinstance(data, types.GeneratorType):
                    for d in data:
                        fp.write(d)
                else:
                    if data:
                        fp.write(data)
            log.info('put: Created %s' % uri)
        except Exception as e:
            log.info('put: Could not create %s, %r', uri, e)
            raise DAV_Error(424)

        return None

    ###
    ### Dead Property Storage (PROPPATCH support)
    ###

    def _get_props_file(self, uri):
        """
        Get the path to the .props file for a resource

        Properties are stored in JSON files with .props extension
        alongside the resource files.
        """
        local_path = self.uri2local(uri)
        return local_path + '.props'

    def get_dead_props(self, uri):
        """
        Load dead properties from .props file

        Returns a dict: {namespace: {propname: value, ...}, ...}
        """
        props_file = self._get_props_file(uri)
        if os.path.exists(props_file):
            try:
                with open(props_file, 'r') as f:
                    return json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                log.error('Error reading props file %s: %s' % (props_file, str(e)))
                return {}
        return {}

    def set_prop(self, uri, ns, propname, value):
        """
        Set a dead property value

        Properties are stored in JSON format in .props files
        """
        # Reject protected DAV: namespace properties
        if ns == "DAV:":
            raise DAV_Forbidden('Cannot modify DAV: properties')

        # Check if resource exists
        local_path = self.uri2local(uri)
        if not os.path.exists(local_path):
            raise DAV_NotFound

        # Load existing properties
        props = self.get_dead_props(uri)

        # Set the property
        if ns not in props:
            props[ns] = {}
        props[ns][propname] = value

        # Save properties
        props_file = self._get_props_file(uri)
        try:
            with open(props_file, 'w') as f:
                json.dump(props, f, indent=2)
        except IOError as e:
            log.error('Error writing props file %s: %s' % (props_file, str(e)))
            raise DAV_Error(500, 'Cannot save properties')

        return True

    def del_prop(self, uri, ns, propname):
        """
        Delete a dead property

        This is idempotent - succeeds even if property doesn't exist
        """
        # Check if resource exists
        local_path = self.uri2local(uri)
        if not os.path.exists(local_path):
            raise DAV_NotFound

        # Load existing properties
        props = self.get_dead_props(uri)

        # Remove the property if it exists
        if ns in props and propname in props[ns]:
            del props[ns][propname]

            # Remove empty namespace
            if not props[ns]:
                del props[ns]

            props_file = self._get_props_file(uri)

            # If no properties left, remove the .props file
            if not props:
                if os.path.exists(props_file):
                    try:
                        os.remove(props_file)
                    except IOError as e:
                        log.error('Error removing props file %s: %s' % (props_file, str(e)))
            else:
                # Save remaining properties
                try:
                    with open(props_file, 'w') as f:
                        json.dump(props, f, indent=2)
                except IOError as e:
                    log.error('Error writing props file %s: %s' % (props_file, str(e)))
                    raise DAV_Error(500, 'Cannot save properties')

        return True

    def get_propnames(self, uri):
        """
        Override to include dead properties

        Returns a dict: {namespace: [propname1, propname2, ...], ...}
        """
        # Get live properties from parent class
        live_props = super().get_propnames(uri)

        # Get dead properties
        dead_props = self.get_dead_props(uri)

        # Merge
        all_props = dict(live_props)
        for ns, propdict in dead_props.items():
            if ns in all_props:
                # Merge with existing namespace
                all_props[ns] = list(set(all_props[ns]) | set(propdict.keys()))
            else:
                # Add new namespace
                all_props[ns] = list(propdict.keys())

        return all_props

    def get_prop(self, uri, ns, propname):
        """
        Override to check dead properties first

        This allows dead properties to shadow live properties
        """
        # Try dead properties first
        dead_props = self.get_dead_props(uri)
        if ns in dead_props and propname in dead_props[ns]:
            return dead_props[ns][propname]

        # Fall back to live properties
        return super().get_prop(uri, ns, propname)

    def mkcol(self,uri):
        """ create a new collection """
        path=self.uri2local(uri)

        # remove trailing slash
        if path[-1]=="/": path=path[:-1]

        # test if file already exists
        if os.path.exists(path):
            raise DAV_Error(405)

        # test if parent exists
        h,t=os.path.split(path)
        if not os.path.exists(h):
            raise DAV_Error(409)

        # test, if we are allowed to create it
        try:
            os.mkdir(path)
            log.info('mkcol: Created new collection %s' % path)
            return 201
        except:
            log.info('mkcol: Creation of %s denied' % path)
            raise DAV_Forbidden

    ### ?? should we do the handler stuff for DELETE, too ?
    ### (see below)

    def rmcol(self,uri):
        """ delete a collection """
        path=self.uri2local(uri)
        if not os.path.exists(path):
            raise DAV_NotFound

        try:
            shutil.rmtree(path)
        except OSError:
            raise DAV_Forbidden # forbidden

        return 204

    def rm(self,uri):
        """ delete a normal resource """
        path=self.uri2local(uri)
        if not os.path.exists(path):
            raise DAV_NotFound

        try:
            os.unlink(path)
        except OSError as ex:
            log.info('rm: Forbidden (%s)' % ex)
            raise DAV_Forbidden # forbidden

        return 204

    ###
    ### DELETE handlers (examples)
    ### (we use the predefined methods in davcmd instead of doing
    ### a rm directly
    ###

    def delone(self,uri):
        """ delete a single resource

        You have to return a result dict of the form
        uri:error_code
        or None if everything's ok

        """
        return delone(self,uri)

    def deltree(self,uri):
        """ delete a collection

        You have to return a result dict of the form
        uri:error_code
        or None if everything's ok
        """

        return deltree(self,uri)


    ###
    ### MOVE handlers (examples)
    ###

    def moveone(self,src,dst,overwrite):
        """ move one resource with Depth=0
        """

        return moveone(self,src,dst,overwrite)

    def movetree(self,src,dst,overwrite):
        """ move a collection with Depth=infinity
        """

        return movetree(self,src,dst,overwrite)

    ###
    ### COPY handlers
    ###

    def copyone(self,src,dst,overwrite):
        """ copy one resource with Depth=0
        """

        return copyone(self,src,dst,overwrite)

    def copytree(self,src,dst,overwrite):
        """ copy a collection with Depth=infinity
        """

        return copytree(self,src,dst,overwrite)

    ###
    ### copy methods.
    ### This methods actually copy something. low-level
    ### They are called by the davcmd utility functions
    ### copytree and copyone (not the above!)
    ### Look in davcmd.py for further details.
    ###

    def copy(self,src,dst):
        """ copy a resource from src to dst """

        srcfile=self.uri2local(src)
        dstfile=self.uri2local(dst)
        try:
            shutil.copy(srcfile, dstfile)
        except (OSError, IOError):
            log.info('copy: forbidden')
            raise DAV_Error(409)

    def copycol(self, src, dst):
        """ copy a collection.

        As this is not recursive (the davserver recurses itself)
        we will only create a new directory here. For some more
        advanced systems we might also have to copy properties from
        the source to the destination.
        """

        return self.mkcol(dst)

    def exists(self,uri):
        """ test if a resource exists """
        path=self.uri2local(uri)
        if os.path.exists(path):
            return 1
        return None

    def is_collection(self,uri):
        """ test if the given uri is a collection """
        path=self.uri2local(uri)
        if os.path.isdir(path):
            return 1
        else:
            return 0
