import os
import textwrap
import time
import logging
import types
import shutil
import json
import fcntl
import tempfile
from io import StringIO
import urllib.parse
from pywebdav.lib.constants import COLLECTION, OBJECT, DAV_NAMESPACE, MAX_PROPERTY_COUNT, MAX_PROPERTY_VALUE_SIZE, MAX_PROPERTY_TOTAL_SIZE
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
        Get the path to the .props file for a resource with security validation

        Properties are stored in JSON files with .props extension
        alongside the resource files.

        Raises DAV_Forbidden if the path escapes the base directory.
        """
        local_path = self.uri2local(uri)
        props_path = local_path + '.props'

        # Security: Validate path BEFORE resolving symlinks to prevent bypass
        # An attacker could create a symlink within the allowed directory
        # that points outside - realpath() would follow it and bypass the check
        normalized_base = os.path.normpath(os.path.abspath(self.directory))
        normalized_props = os.path.normpath(os.path.abspath(props_path))

        if not normalized_props.startswith(normalized_base + os.sep) and normalized_props != normalized_base:
            log.error(f'Path traversal attempt: {props_path} escapes {self.directory}')
            raise DAV_Forbidden('Invalid path')

        return props_path

    def _lock_props_file(self, file_handle):
        """
        Acquire exclusive lock on property file to prevent race conditions
        """
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
        except IOError as e:
            log.error(f'Failed to lock property file: {e}')
            raise DAV_Error(500, 'Cannot lock property file')

    def _unlock_props_file(self, file_handle):
        """
        Release lock on property file
        """
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
        except IOError:
            pass  # Best effort unlock

    def _normalize_props_for_json(self, props):
        """
        Convert props dict for JSON storage: None namespace → "null" string

        JSON doesn't support None as dict keys, so we use the string "null"
        """
        normalized = {}
        for ns, propdict in props.items():
            json_key = "null" if ns is None else ns
            normalized[json_key] = propdict
        return normalized

    def _normalize_props_from_json(self, props):
        """
        Convert props dict from JSON storage: "null" string → None namespace

        This reverses _normalize_props_for_json()
        """
        normalized = {}
        for ns, propdict in props.items():
            python_key = None if ns == "null" else ns
            normalized[python_key] = propdict
        return normalized

    def _validate_property_limits(self, props):
        """
        Validate that properties don't exceed resource limits

        Raises DAV_Error(507) if limits are exceeded
        """
        total_count = sum(len(propdict) for propdict in props.values())
        if total_count > MAX_PROPERTY_COUNT:
            raise DAV_Error(507, f'Property count exceeds limit of {MAX_PROPERTY_COUNT}')

        # Approximate total size by summing value lengths + overhead
        # This avoids expensive JSON serialization just for size checking
        # Overhead approximation: 50 bytes per property for JSON structure
        total_size = sum(
            len(propname) + len(value) + len(ns or '') + 50
            for ns, propdict in props.items()
            for propname, value in propdict.items()
        )
        if total_size > MAX_PROPERTY_TOTAL_SIZE:
            raise DAV_Error(507, f'Total property size exceeds limit of {MAX_PROPERTY_TOTAL_SIZE} bytes')

        # Check individual property value sizes
        for ns, propdict in props.items():
            for propname, value in propdict.items():
                if len(value) > MAX_PROPERTY_VALUE_SIZE:
                    raise DAV_Error(507, f'Property value size exceeds limit of {MAX_PROPERTY_VALUE_SIZE} bytes')

    def get_dead_props(self, uri):
        """
        Load dead properties from .props file with file locking

        Returns a dict: {namespace: {propname: value, ...}, ...}
        Namespace can be None for properties with xmlns=""
        """
        props_file = self._get_props_file(uri)
        if not os.path.exists(props_file):
            return {}

        try:
            with open(props_file, 'r') as f:
                self._lock_props_file(f)
                try:
                    props = json.load(f)
                    # Convert "null" string back to None for null namespaces
                    props = self._normalize_props_from_json(props)
                finally:
                    self._unlock_props_file(f)
                return props
        except (IOError, json.JSONDecodeError) as e:
            log.error(f'Error reading props file: {e}')
            return {}

    def _atomic_write_props(self, props_file, props):
        """
        Atomically write properties to file using temp file + rename

        This provides atomicity: either the write succeeds completely or not at all.
        Converts None namespace to "null" string for JSON compatibility.
        """
        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(props_file),
            prefix='.props.tmp.',
            suffix='.json'
        )

        try:
            with os.fdopen(temp_fd, 'w') as f:
                # Convert None to "null" for JSON, use compact JSON to reduce file size
                json_props = self._normalize_props_for_json(props)
                json.dump(json_props, f)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is on disk

            # Atomic rename
            os.rename(temp_path, props_file)

        except Exception as e:
            # Clean up temp file on failure
            try:
                os.unlink(temp_path)
            except:
                pass
            raise e

    def set_prop(self, uri, ns, propname, value):
        """
        Set a dead property value with proper locking and validation

        Properties are stored in JSON format in .props files.
        Uses file locking to prevent race conditions.
        """
        # Reject protected DAV: namespace properties
        if ns == DAV_NAMESPACE:
            raise DAV_Forbidden('Cannot modify DAV: properties')

        # Validate property value size
        if len(value) > MAX_PROPERTY_VALUE_SIZE:
            raise DAV_Error(507, f'Property value too large (max {MAX_PROPERTY_VALUE_SIZE} bytes)')

        # Check if resource exists
        local_path = self.uri2local(uri)
        if not os.path.exists(local_path):
            raise DAV_NotFound

        props_file = self._get_props_file(uri)

        # Create parent directory if needed
        props_dir = os.path.dirname(props_file)
        if not os.path.exists(props_dir):
            os.makedirs(props_dir, exist_ok=True)

        # Atomically open file for read/write, creating if needed
        # This avoids TOCTOU race between existence check and open
        try:
            # Try to open existing file
            f = open(props_file, 'r+')
        except FileNotFoundError:
            # File doesn't exist - create it atomically
            # Use 'x' mode for exclusive creation (fails if exists)
            try:
                f = open(props_file, 'x+')
            except FileExistsError:
                # Another process created it - open for read/write
                f = open(props_file, 'r+')

        # Now we have an open file handle - acquire lock and load
        with f:
            self._lock_props_file(f)
            try:
                f.seek(0)
                content = f.read()
                if content:
                    props = json.loads(content)
                    # Convert "null" string back to None for null namespaces
                    props = self._normalize_props_from_json(props)
                else:
                    props = {}
            except json.JSONDecodeError:
                props = {}

        try:
            # Set the property
            if ns not in props:
                props[ns] = {}
            props[ns][propname] = value

            # Validate limits
            self._validate_property_limits(props)

            # Atomic write
            self._atomic_write_props(props_file, props)

        finally:
            # Unlock is handled by file close, but explicit for clarity
            pass

        return True

    def del_prop(self, uri, ns, propname):
        """
        Delete a dead property with proper locking

        This is idempotent - succeeds even if property doesn't exist.
        Uses file locking to prevent race conditions.
        """
        # Check if resource exists
        local_path = self.uri2local(uri)
        if not os.path.exists(local_path):
            raise DAV_NotFound

        props_file = self._get_props_file(uri)

        # Try to open file atomically - if it doesn't exist, operation is already done
        try:
            f = open(props_file, 'r+')
        except FileNotFoundError:
            return True  # Idempotent: file doesn't exist, property already removed

        # Lock and load properties
        with f:
            self._lock_props_file(f)
            try:
                props = json.load(f)
                # Convert "null" string back to None for null namespaces
                props = self._normalize_props_from_json(props)
            except json.JSONDecodeError:
                props = {}

            # Remove the property if it exists
            if ns in props and propname in props[ns]:
                del props[ns][propname]

                # Remove empty namespace
                if not props[ns]:
                    del props[ns]

        # If no properties left, remove the .props file
        if not props:
            try:
                os.remove(props_file)
            except IOError as e:
                log.error(f'Error removing props file: {e}')
        else:
            # Save remaining properties atomically
            self._atomic_write_props(props_file, props)

        return True

    def _copy_props_file(self, src_uri, dst_uri):
        """
        Copy .props file from source to destination

        Used internally by COPY operation to preserve properties.
        Non-fatal: If property copy fails, resource is still copied.
        """
        try:
            src_props = self._get_props_file(src_uri)
            dst_props = self._get_props_file(dst_uri)

            if os.path.exists(src_props):
                shutil.copy2(src_props, dst_props)
        except Exception as e:
            log.warning(f'Failed to copy properties from {src_uri} to {dst_uri}: {e}', exc_info=True)

    def _move_props_file(self, src_uri, dst_uri):
        """
        Move .props file from source to destination

        Used internally by MOVE operation to preserve properties.
        Non-fatal: If property move fails, resource is still moved.
        """
        try:
            src_props = self._get_props_file(src_uri)
            dst_props = self._get_props_file(dst_uri)

            if os.path.exists(src_props):
                shutil.move(src_props, dst_props)
        except Exception as e:
            log.warning(f'Failed to move properties from {src_uri} to {dst_uri}: {e}', exc_info=True)

    def _delete_props_file(self, uri):
        """
        Delete .props file for a resource

        Used internally by DELETE operation.
        Non-fatal: If property file deletion fails, resource is still deleted.
        """
        try:
            props_file = self._get_props_file(uri)
            if os.path.exists(props_file):
                os.remove(props_file)
        except Exception as e:
            log.warning(f'Failed to delete properties for {uri}: {e}', exc_info=True)

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
        Override to check properties - live properties take precedence

        Dead properties should never shadow live (computed) properties.
        """
        # Try live properties first
        try:
            return super().get_prop(uri, ns, propname)
        except DAV_NotFound:
            pass

        # Fall back to dead properties only if live property doesn't exist
        dead_props = self.get_dead_props(uri)
        if ns in dead_props and propname in dead_props[ns]:
            return dead_props[ns][propname]

        # Property not found in either
        raise DAV_NotFound

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
        """ delete a normal resource and its properties """
        path=self.uri2local(uri)
        if not os.path.exists(path):
            raise DAV_NotFound

        try:
            os.unlink(path)
            # Also delete associated .props file
            self._delete_props_file(uri)
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
        """ copy a resource from src to dst, including properties """

        srcfile=self.uri2local(src)
        dstfile=self.uri2local(dst)
        try:
            shutil.copy(srcfile, dstfile)
            # Also copy associated .props file
            self._copy_props_file(src, dst)
        except (OSError, IOError):
            log.info('copy: forbidden')
            raise DAV_Error(409)

    def copycol(self, src, dst):
        """ copy a collection, including properties

        As this is not recursive (the davserver recurses itself)
        we will only create a new directory here and copy properties.
        """
        result = self.mkcol(dst)
        # Copy collection properties
        self._copy_props_file(src, dst)
        return result

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
