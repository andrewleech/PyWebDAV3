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

status codes for DAV services


"""


STATUS_CODES={
        100:    "Continue",
        102:    "Processing",
        200:    "Ok",
        201:    "Created",
        204:    "No Content",
        207:    "Multi-Status",
        201:    "Created",
        400:    "Bad Request",
        403:    "Forbidden",
        404:    "Not Found",
        405:    "Method Not Allowed",
        409:    "Conflict",
        412:    "Precondition failed",
        423:    "Locked",
        415:    "Unsupported Media Type",
        507:    "Insufficient Storage",
        422:    "Unprocessable Entity",
        423:    "Locked",
        424:    "Failed Dependency",
        502:    "Bad Gateway",
        507:    "Insufficient Storage"
}
