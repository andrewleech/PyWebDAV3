
from __future__ import absolute_import
import pkg_resources

# get version from package
package = pkg_resources.require('PyWebDAV3')[0]
VERSION = package.version

# author hardcoded here
AUTHOR = 'Andrew Leech <andrew@alelec.net>, Simon Pamies <spamsch@gmail.com>'
