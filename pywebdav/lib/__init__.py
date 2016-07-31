
from __future__ import absolute_import
import pkg_resources

# try to get version from package (if installed)
try:
    package = pkg_resources.require('PyWebDAV3')[0]
    VERSION = package.version
except pkg_resources.DistributionNotFound:
    # Not running from installed version
    VERSION = "DEVELOPMENT"

# author hardcoded here
AUTHOR = 'Andrew Leech <andrew@alelec.net>, Simon Pamies <spamsch@gmail.com>'
