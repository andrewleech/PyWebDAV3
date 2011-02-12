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

import logging

log = logging.getLogger(__name__)

try:
    import MySQLdb
except ImportError:
    pass

import sys

class Mconn:
    def connect(self,username,userpasswd,host,port,db):
        try: connection = MySQLdb.connect(host=host, port=int(port), user=username, passwd=userpasswd,db=db)
        except MySQLdb.OperationalError, message:
            log.error("%d:\n%s" % (message[ 0 ], message[ 1 ] ))
            return 0
        else:
            self.db = connection.cursor()

            return 1

    def execute(self,qry):
        if self.db:
            try: res=self.db.execute(qry)
            except MySQLdb.OperationalError, message:
                log.error("Error %d:\n%s" % (message[ 0 ], message[ 1 ] ))
                return 0

            except MySQLdb.ProgrammingError, message:
                log.error("Error %d:\n%s" % (message[ 0 ], message[ 1 ] ))
                return 0

            else:
                log.debug('Query Returned '+str(res)+' results')
                return self.db.fetchall()

    def create_user(self,user,passwd):
        qry="select * from Users where User='%s'"%(user)
        res=self.execute(qry)
        if not res or len(res) ==0:
            qry="insert into Users (User,Pass) values('%s','%s')"%(user,passwd)
            res=self.execute(qry)
        else:
            log.debug("Username already in use")

    def create_table(self):
        qry="""CREATE TABLE `Users` (
                  `uid` int(10) NOT NULL auto_increment,
                  `User` varchar(60) default NULL,
                  `Pass` varchar(60) default NULL,
            `Write` tinyint(1) default '0',
                  PRIMARY KEY  (`uid`)
                ) ENGINE=MyISAM DEFAULT CHARSET=latin1"""
        self.execute(qry)


    def first_run(self,user,passwd):
        res= self.execute('select * from Users')
        if res or type(res)==type(()) :
            pass
        else:
            self.create_table()
            self.create_user(user,passwd)


    def __init__(self,user,password,host,port,db):
        self.db=0
        self.connect(user,password,host,port,db)
