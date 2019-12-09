"""

davcmd.py
---------

containts commands like copy, move, delete for normal
resources and collections

"""

from __future__ import absolute_import
from six.moves import urllib

from .utils import create_treelist, is_prefix
from .errors import *
from six.moves import range
import os

def deltree(dc,uri,exclude={}):
    """ delete a tree of resources

    dc  -- dataclass to use
    uri -- root uri to delete
    exclude -- an optional list of uri:error_code pairs which should not
           be deleted.

    returns dict of uri:error_code tuples from which
    another method can create a multistatus xml element.

    Also note that we only know Depth=infinity thus we don't have
    to test for it.

    """

    tlist=create_treelist(dc,uri)
    result={}

    for i in range(len(tlist),0,-1):
        problem_uris=list(result.keys())
        element=tlist[i-1]

        # test here, if an element is a prefix of an uri which
        # generated an error before.
        # note that we walk here from childs to parents, thus
        # we cannot delete a parent if a child made a problem.
        # (see example in 8.6.2.1)
        ok=1
        for p in problem_uris:
            if is_prefix(element,p):
                ok=None
                break

            if not ok: continue

        # here we test for the exclude list which is the other way round!
        for p in exclude.keys():
            if is_prefix(p,element):
                ok=None
                break

            if not ok: continue

        # now delete stuff
        try:
            delone(dc,element)
        except DAV_Error as error:
            (ec,dd) = error.args
            result[element]=ec

    return result

def delone(dc,uri):
    """ delete a single object """
    if dc.is_collection(uri):
        return dc.rmcol(uri)   # should be empty
    else:
        return dc.rm(uri)

###
### COPY
###

# helper function

def copy(dc,src,dst):
    """ only copy the element

    This is just a helper method factored out from copy and
    copytree. It will not handle the overwrite or depth header.

    """

    # destination should have been deleted before
    if dc.exists(dst): 
        raise DAV_Error(412)

    # source should exist also
    if not dc.exists(src): 
        raise DAV_NotFound

    if dc.is_collection(src):
        dc.copycol(src, dst) # an exception will be passed thru
    else:
        dc.copy(src, dst)  # an exception will be passed thru

# the main functions

def copyone(dc,src,dst,overwrite=None):
    """ copy one resource to a new destination """

    if overwrite and dc.exists(dst):
        delres = deltree(dc, dst)
    else:
        delres={}

    # if we cannot delete everything, then do not copy!
    if delres: 
        return delres

    try:
        copy(dc, src, dst)    # pass thru exceptions
    except DAV_Error as error:
        (ec, dd) = error.args
        return ec

def copytree(dc,src,dst,overwrite=None):
    """ copy a tree of resources to another location

    dc  -- dataclass to use
    src -- src uri from where to copy
    dst -- dst uri
    overwrite -- if True then delete dst uri before

    returns dict of uri:error_code tuples from which
    another method can create a multistatus xml element.

    """

    # first delete the destination resource
    if overwrite and dc.exists(dst):
        delres=deltree(dc,dst)
    else:
        delres={}

    # if we cannot delete everything, then do not copy!
    if delres: 
        return delres

    # get the tree we have to copy
    tlist = create_treelist(dc,src)
    result = {}

    # Extract the path out of the source URI.
    src_path = urllib.parse.urlparse(src).path

    # Parse the destination URI.
    # We'll be using it to construct destination URIs,
    # so we don't just retain the path, like we did with
    # the source.
    dst_parsed = urllib.parse.urlparse(dst)

    for element in tlist:
        problem_uris = list(result.keys())

        # now URIs get longer and longer thus we have
        # to test if we had a parent URI which we were not
        # able to copy in problem_uris which is the prefix
        # of the actual element. If it is, then we cannot
        # copy this as well but do not generate another error.
        ok=True
        for p in problem_uris:
            if is_prefix(p,element):
                ok=False
                break

        if not ok:
            continue

        # Find the element's path relative to the source.
        element_path = urllib.parse.urlparse(element).path
        element_path_rel = os.path.relpath(element_path, start=src_path)
        # Append this relative path to the destination.
        if element_path_rel == '.':
            # os.path.relpath("/somedir", start="/somedir") returns
            # a result of ".", which we don't want to append to the
            # destination path.
            dst_path = dst_parsed.path
        else:
            dst_path = os.path.join(dst_parsed.path, element_path_rel)

        # Generate destination URI using our derived destination path.
        dst_uri = urllib.parse.urlunparse(dst_parsed._replace(path=os.path.join(dst_parsed.path, element_path_rel)))


        # now copy stuff
        try:
            copy(dc,element,dst_uri)
        except DAV_Error as error:
            (ec,dd) = error.args
            result[element]=ec

    return result


###
### MOVE
###


def moveone(dc,src,dst,overwrite=None):
    """ move a single resource

    This is done by first copying it and then deleting
    the original.
    """

    # first copy it
    copyone(dc, src, dst, overwrite)

    # then delete it
    dc.rm(src)

def movetree(dc,src,dst,overwrite=None):
    """ move a collection

    This is done by first copying it and then deleting
    the original.

    PROBLEM: if something did not copy then we have a problem
    when deleting as the original might get deleted!
    """

    # first copy it
    res = copytree(dc,src,dst,overwrite)

    # TODO: shouldn't we check res for errors and bail out before
    # the delete if we find any?
    # TODO: or, better yet, is there anything preventing us from
    # reimplementing this using `shutil.move()`?

    # then delete it
    res = deltree(dc,src,exclude=res)

    return res

