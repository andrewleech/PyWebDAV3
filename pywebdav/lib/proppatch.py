import xml.dom.minidom
domimpl = xml.dom.minidom.getDOMImplementation()

import logging
import urllib.parse

from . import utils
from .errors import DAV_Error, DAV_NotFound, DAV_Forbidden

log = logging.getLogger(__name__)


class PROPPATCH:
    """
    Parse a PROPPATCH propertyupdate request and execute property operations

    This class handles:
    - Parsing the propertyupdate XML
    - Validating all operations before execution (atomicity)
    - Executing property set/remove operations via the dataclass interface
    - Generating Multi-Status (207) responses
    """

    def __init__(self, uri, dataclass, body):
        self._uri = uri.rstrip('/')
        self._dataclass = dataclass
        self._operations = []
        self._results = {}  # {(ns, propname): (status_code, description)}

        if dataclass.verbose:
            log.info('PROPPATCH: URI is %s' % uri)

        # Parse the XML body
        if body:
            try:
                self._operations = utils.parse_proppatch(body)
            except Exception as e:
                log.error('PROPPATCH: XML parse error: %s' % str(e))
                raise DAV_Error(400, 'Bad Request')

    def validate_and_execute(self):
        """
        Validate all operations and execute them atomically

        Per RFC 4918, either ALL operations succeed or ALL fail.
        We validate everything first, then execute if all are valid.

        Returns True if all operations succeeded
        """
        if not self._operations:
            # No operations - this is technically valid but unusual
            return True

        # Check if resource exists
        if not self._dataclass.exists(self._uri):
            raise DAV_NotFound

        # Phase 1: Validate all operations
        validation_errors = []
        for action, ns, propname, value in self._operations:
            # Check if property is protected (DAV: namespace properties)
            if ns == "DAV:":
                validation_errors.append((ns, propname, 403, 'Forbidden'))
                continue

            # For 'set' operations, check if we can set the property
            if action == 'set':
                try:
                    # Just check the interface has the method
                    if not hasattr(self._dataclass, 'set_prop'):
                        validation_errors.append((ns, propname, 403, 'Forbidden'))
                except Exception as e:
                    validation_errors.append((ns, propname, 500, str(e)))

            # For 'remove' operations, check if we can remove
            elif action == 'remove':
                try:
                    # Just check the interface has the method
                    if not hasattr(self._dataclass, 'del_prop'):
                        validation_errors.append((ns, propname, 403, 'Forbidden'))
                except Exception as e:
                    validation_errors.append((ns, propname, 500, str(e)))

        # If any validation failed, mark all as failed (atomicity)
        if validation_errors:
            for action, ns, propname, value in self._operations:
                # Find if this specific prop had an error
                found_error = None
                for err_ns, err_propname, err_code, err_desc in validation_errors:
                    if err_ns == ns and err_propname == propname:
                        found_error = (err_code, err_desc)
                        break

                if found_error:
                    self._results[(ns, propname)] = found_error
                else:
                    # This operation was valid but failed due to atomicity
                    self._results[(ns, propname)] = (424, 'Failed Dependency')
            return False

        # Phase 2: Execute all operations (all validation passed)
        all_success = True
        for action, ns, propname, value in self._operations:
            try:
                if action == 'set':
                    self._dataclass.set_prop(self._uri, ns, propname, value)
                    self._results[(ns, propname)] = (200, 'OK')
                elif action == 'remove':
                    self._dataclass.del_prop(self._uri, ns, propname)
                    self._results[(ns, propname)] = (200, 'OK')
            except DAV_Forbidden:
                self._results[(ns, propname)] = (403, 'Forbidden')
                all_success = False
            except DAV_NotFound:
                # For remove, this is OK (idempotent)
                if action == 'remove':
                    self._results[(ns, propname)] = (200, 'OK')
                else:
                    self._results[(ns, propname)] = (404, 'Not Found')
                    all_success = False
            except DAV_Error as e:
                code = e.args[0] if e.args else 500
                self._results[(ns, propname)] = (code, str(e))
                all_success = False
            except Exception as e:
                log.error('PROPPATCH: Unexpected error: %s' % str(e))
                self._results[(ns, propname)] = (500, 'Internal Server Error')
                all_success = False

        # If any execution failed, roll back would happen here
        # For now, we don't have transactional support
        return all_success

    def create_response(self):
        """
        Create a Multi-Status (207) XML response

        Format per RFC 4918:
        <?xml version="1.0" encoding="utf-8" ?>
        <D:multistatus xmlns:D="DAV:">
          <D:response>
            <D:href>http://example.com/resource</D:href>
            <D:propstat>
              <D:prop><ns:propname/></D:prop>
              <D:status>HTTP/1.1 200 OK</D:status>
            </D:propstat>
          </D:response>
        </D:multistatus>
        """
        # Create the document
        doc = domimpl.createDocument(None, "multistatus", None)
        ms = doc.documentElement
        ms.setAttribute("xmlns:D", "DAV:")
        ms.tagName = 'D:multistatus'

        # Group results by status code for efficiency
        status_groups = {}
        namespaces = {}
        ns_counter = 0

        for (ns, propname), (status_code, description) in self._results.items():
            if status_code not in status_groups:
                status_groups[status_code] = []
            status_groups[status_code].append((ns, propname))

            # Track namespaces for later
            if ns and ns not in namespaces and ns != "DAV:":
                namespaces[ns] = "ns%d" % ns_counter
                ns_counter += 1

        # Add namespace declarations to root
        for ns, prefix in namespaces.items():
            ms.setAttribute("xmlns:%s" % prefix, ns)

        # Create response element
        re = doc.createElement("D:response")

        # Add href
        href = doc.createElement("D:href")
        huri = doc.createTextNode(urllib.parse.quote(self._uri))
        href.appendChild(huri)
        re.appendChild(href)

        # Create propstat for each status code
        for status_code in sorted(status_groups.keys()):
            ps = doc.createElement("D:propstat")

            # Add prop element with all properties having this status
            gp = doc.createElement("D:prop")
            for ns, propname in status_groups[status_code]:
                if ns == "DAV:" or ns is None:
                    pe = doc.createElement("D:" + propname)
                elif ns in namespaces:
                    pe = doc.createElement(namespaces[ns] + ":" + propname)
                else:
                    pe = doc.createElement(propname)
                gp.appendChild(pe)
            ps.appendChild(gp)

            # Add status
            s = doc.createElement("D:status")
            status_text = utils.gen_estring(status_code)
            t = doc.createTextNode(status_text)
            s.appendChild(t)
            ps.appendChild(s)

            re.appendChild(ps)

        ms.appendChild(re)

        return doc.toxml(encoding="utf-8") + b"\n"
