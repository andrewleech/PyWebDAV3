#!/usr/bin/python
#Copyright (c) 2009 Simon Pamies (s.pamies@banality.de)
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

from ConfigParser import SafeConfigParser

class Configuration:
    def __init__ (self, fileName):
        cp = SafeConfigParser()
        cp.read(fileName)
        self.__parser = cp
        self.fileName = fileName

    def __getattr__ (self, name):
        if name in self.__parser.sections():
            return Section(name, self.__parser)
        else:
            return None

    def __str__ (self):
        p = self.__parser
        result = []
        result.append('<Configuration from %s>' % self.fileName)
        for s in p.sections():
            result.append('[%s]' % s)
            for o in p.options(s):
                result.append('%s=%s' % (o, p.get(s, o)))
        return '\n'.join(result)

class Section:
    def __init__ (self, name, parser):
        self.name = name
        self.__parser = parser
    def __getattr__ (self, name):
        return self.__parser.get(self.name, name)

    def getboolean(self, name):
        return self.__parser.getboolean(self.name, name)

    def __contains__(self, name):
        return self.__parser.has_option(self.name, name)

    def get(self, name, default):
        if name in self:
            return self.__getattr__(name)
        else:
            return default

# Test
if __name__ == '__main__':
    c = Configuration('Importador.ini')
    print c.Origem.host, c.Origem.port
