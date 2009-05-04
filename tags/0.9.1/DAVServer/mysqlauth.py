from fileauth import DAVAuthHandler

class MySQLAuthHandler(DAVAuthHandler):
    """
    Provides authentication based on a mysql table
    """

    def get_userinfo(self,user,pw,command):
        """ authenticate user """

        # Commands that need write access
        nowrite=['OPTIONS','PROPFIND','GET']

        Mysql=self._config.MySQL
        DB=Mconn(Mysql.user,Mysql.passwd,Mysql.host,Mysql.port,Mysql.dbtable)
        if self.verbose:
            print >>sys.stderr,user,command

        qry="select * from %s.Users where User='%s' and Pass='%s'"%(Mysql.dbtable,user,pw)
        Auth=DB.execute(qry)
        
        if len(Auth) == 1:
            can_write=Auth[0][3]
            if not can_write and not command in nowrite:
                self._log('Authentication failed for user %s using command %s' %(user,command))
                return 0
            else:
                self._log('Successfully authenticated user %s writable=%s' % (user,can_write))
                return 1
        else:
            self._log('Authentication failed for user %s' % user)
            return 0
            
        self._log('Authentication failed for user %s' % user)
        return 0

