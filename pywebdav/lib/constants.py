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

# WebDAV namespace
DAV_NAMESPACE = "DAV:"

# Property storage limits
MAX_PROPERTY_COUNT = 1000  # Maximum properties per resource
MAX_PROPERTY_VALUE_SIZE = 1024 * 1024  # 1MB per property value
MAX_PROPERTY_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB total per resource
