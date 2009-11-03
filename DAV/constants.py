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

# definition for resourcetype
COLLECTION=1
OBJECT=None

# attributes for resources
DAV_PROPS=['creationdate', 'displayname', 'getcontentlanguage', 'getcontentlength', 'getcontenttype', 'getetag', 'getlastmodified', 'lockdiscovery', 'resourcetype', 'source', 'supportedlock']

# Request classes in propfind
RT_ALLPROP=1
RT_PROPNAME=2
RT_PROP=3

# server mode
DAV_VERSION_1 = {
        'version' : '1',
        'options' : 
        'GET, HEAD, COPY, MOVE, POST, PUT, PROPFIND, PROPPATCH, OPTIONS, MKCOL, DELETE, TRACE, REPORT'
}

DAV_VERSION_2 = {
        'version' : '1,2',
        'options' : 
        DAV_VERSION_1['options'] + ', LOCK, UNLOCK'
}
