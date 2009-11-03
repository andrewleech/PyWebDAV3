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

    Exceptions for the DAVserver implementation

"""

class DAV_Error(Exception):
    """ in general we can have the following arguments:

    1. the error code
    2. the error result element, e.g. a <multistatus> element
    """

    def __init__(self,*args):
        if len(args)==1:
            self.args=(args[0],"")
        else:
            self.args=args

class DAV_Secret(DAV_Error):
    """ the user is not allowed to know anything about it

    returning this for a property value means to exclude it
    from the response xml element.
    """

    def __init__(self):
        DAV_Error.__init__(self,0)
        pass

class DAV_NotFound(DAV_Error):
    """ a requested property was not found for a resource """

    def __init__(self,*args):
        if len(args):
            DAV_Error.__init__(self,404,args[0])
        else:
            DAV_Error.__init__(self,404)

        pass

class DAV_Forbidden(DAV_Error):
    """ a method on a resource is not allowed """

    def __init__(self,*args):
        if len(args):
            DAV_Error.__init__(self,403,args[0])
        else:
            DAV_Error.__init__(self,403)
        pass

