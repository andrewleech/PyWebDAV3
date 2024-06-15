"""

basic interface class

use this for subclassing when writing your own interface
class.

"""

from xml.dom import minidom
from .locks import LockManager
from .errors import *

import time

class dav_interface:
    """ interface class for implementing DAV servers """

    ### defined properties (modify this but let the DAV stuff there!)
    ### the format is namespace: [list of properties]

    PROPS={"DAV:" : ('creationdate',
                     'displayname',
                     'getcontentlanguage',
                     'getcontentlength',
                     'getcontenttype',
                     'getetag',
                     'getlastmodified',
                     'lockdiscovery',
                     'resourcetype',
                     'source',
                     'supportedlock'),
           "NS2" : ("p1","p2")
           }

    # here we define which methods handle which namespace
    # the first item is the namespace URI and the second one
    # the method prefix
    # e.g. for DAV:getcontenttype we call dav_getcontenttype()
    M_NS={"DAV:" : "_get_dav",
          "NS2"  : "ns2" }

    def get_propnames(self,uri):
        """ return the property names allowed for the given URI

        In this method we simply return the above defined properties
        assuming that they are valid for any resource.
        You can override this in order to return a different set
        of property names for each resource.

        """
        return self.PROPS

    def get_prop2(self,uri,ns,pname):
        """ return the value of a property

        """
        if ns.lower() == "dav:":
            return self.get_dav(uri,pname)

        raise DAV_NotFound

    def get_prop(self,uri,ns,propname):
        """ return the value of a given property

        uri        -- uri of the object to get the property of
        ns        -- namespace of the property
        pname        -- name of the property
        """
        if ns in self.M_NS:
            prefix=self.M_NS[ns]
        else:
            raise DAV_NotFound
        mname=prefix+"_"+propname.replace('-', '_')
        try:
            m=getattr(self,mname)
            r=m(uri)
            return r
        except AttributeError:
            raise DAV_NotFound

    ###
    ### DATA methods (for GET and PUT)
    ###

    def get_data(self, uri, range=None):
        """ return the content of an object

        return data or raise an exception

        """
        raise DAV_NotFound

    def put(self, uri, data, content_type=None):
        """ write an object to the repository

        return the location uri or raise an exception
        """

        raise DAV_Forbidden

    ###
    ### LOCKing information
    ###
    def _get_dav_supportedlock(self, uri):

        txt = ('<main xmlns:D="http://dummy/d" xmlns:ns1="http://webdav.de/ns1"><D:lockentry>\n'
                '<D:lockscope><D:exclusive></D:exclusive></D:lockscope>\n'
                '<D:locktype><D:write></D:write></D:locktype>\n'
                '</D:lockentry></main>\n')
        xml = minidom.parseString(txt)
        return xml.firstChild.firstChild

    def _get_dav_lockdiscovery(self, uri):
        lcm = LockManager()
        if lcm._l_isLocked(uri):
            lock = lcm._l_getLockForUri(uri)
            txt = lock.asXML(discover=True, namespace='D')

            txtwithns = '<main xmlns:D="http://dummy/D" xmlns:n="http://webdav.de/N">%s</main>'
            xml = minidom.parseString(txtwithns % txt)
            return xml.firstChild.firstChild

        return ''

    ###
    ### Methods for DAV properties
    ###

    def _get_dav_creationdate(self,uri):
        """ return the creationdate of a resource """
        d=self.get_creationdate(uri)
        # format it
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(d))

    def _get_dav_getlastmodified(self,uri):
        """ return the last modified date of a resource """
        d=self.get_lastmodified(uri)
        # format it
        return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(d))


    ###
    ### OVERRIDE THESE!
    ###

    def get_creationdate(self,uri):
        """ return the creationdate of the resource """
        return time.time()

    def get_lastmodified(self,uri):
        """ return the last modification date of the resource """
        return time.time()


    ###
    ### COPY MOVE DELETE
    ###

    ### methods for deleting a resource

    def rmcol(self,uri):
        """ delete a collection 

        This should not delete any children! This is automatically done
        before by the DELETE class in DAV/delete.py

        return a success code or raise an exception

        """
        raise DAV_NotFound

    def rm(self,uri):
        """ delete a single resource 

        return a success code or raise an exception

        """
        raise DAV_NotFound

    """

    COPY/MOVE HANDLER

    These handler are called when a COPY or MOVE method is invoked by
    a client. In the default implementation it works as follows:

    - the davserver receives a COPY/MOVE method
    - the davcopy or davmove module will be loaded and the corresponding
      class will be initialized
    - this class parses the query and decides which method of the interface class
      to call:

      copyone for a single resource to copy
      copytree for a tree to copy (collection)
      (the same goes for move of course).

    - the interface class has now two options:
        1. to handle the action directly (e.g. cp or mv on filesystems)
        2. to let it handle via the copy/move methods in davcmd.

    ad 1) The first approach can be used when we know that no error can 
          happen inside a tree or when the action can exactly tell which
          element made which error. We have to collect these and return
          it in a dict of the form {uri: error_code, ...}

    ad 2) The copytree/movetree/... methods of davcmd.py will do the recursion
          themselves and call for each resource the copy/move method of the
          interface class. Thus method will then only act on a single resource.
          (Thus a copycol on a normal unix filesystem actually only needs to do
          an mkdir as the content will be copied by the davcmd.py function.
          The davcmd.py method will also automatically collect all errors and
          return the dictionary described above.
          When you use 2) you also have to implement the copy() and copycol()
          methods in your interface class. See the example for details.

    To decide which approach is the best you have to decide if your application
    is able to generate errors inside a tree. E.g. a function which completely
    fails on a tree if one of the tree's childs fail is not what we need. Then
    2) would be your way of doing it.
    Actually usually 2) is the better solution and should only be replaced by
    1) if you really need it.

    The remaining question is if we should do the same for the DELETE method.

    """

    ### MOVE handlers

    def moveone(self,src,dst,overwrite):
        """ move one resource with Depth=0 """
        return moveone(self,src,dst,overwrite)

    def movetree(self,src,dst,overwrite):
        """ move a collection with Depth=infinity """
        return movetree(self,src,dst,overwrite)

    ### COPY handlers

    def copyone(self,src,dst,overwrite):
        """ copy one resource with Depth=0 """
        return copyone(self,src,dst,overwrite)

    def copytree(self,src,dst,overwrite):
        """ copy a collection with Depth=infinity """
        return copytree(self,src,dst,overwrite)


    ### low level copy methods (you only need these for method 2)
    def copy(self,src,dst):
        """ copy a resource with depth==0 

        You don't need to bother about overwrite or not.
        This has been done already.

        return a success code or raise an exception if something fails
        """
        return 201


    def copycol(self,src,dst):
        """ copy a resource with depth==infinity 

        You don't need to bother about overwrite or not.
        This has been done already.

        return a success code or raise an exception if something fails
        """
        return 201

    ### some utility functions you need to implement

    def exists(self,uri):
        """ return 1 or None depending on if a resource exists """
        return None # no

    def is_collection(self,uri):
        """ return 1 or None depending on if a resource is a collection """
        return None # no

