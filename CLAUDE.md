# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyWebDAV3 is a Python 3.8+ implementation of a WebDAV server and library supporting WebDAV levels 1 and 2 (including LOCK/UNLOCK). The project provides both a standalone server (`davserver`) and a library for integrating WebDAV capabilities into applications.

## Architecture

The codebase is organized into two main packages:

### pywebdav/lib/ - Core WebDAV Library
- **WebDAVServer.py**: Main DAV request handler class (`DAVRequestHandler`) that inherits from `AuthServer.AuthRequestHandler` and `LockManager`. Implements HTTP methods (GET, HEAD, PUT, OPTIONS, PROPFIND, PROPPATCH, MKCOL, REPORT, LOCK, UNLOCK).
- **AuthServer.py**: Provides HTTP Basic Authentication layer on top of standard HTTP server.
- **iface.py**: Abstract interface class (`dav_interface`) that defines the contract for backend data sources. Any custom backend must implement this interface to handle property retrieval, data access, and resource management.
- **propfind.py, report.py, davcopy.py, davmove.py, delete.py**: Separate classes for each DAV method that handle XML parsing and response generation.
- **davcmd.py**: Utility functions for DAV operations (copyone, copytree, moveone, movetree, delone, deltree).
- **locks.py**: `LockManager` class implementing WebDAV level 2 locking functionality.
- **INI_Parse.py**: Configuration file parser for server settings.
- **dbconn.py**: Database connection utilities for optional MySQL support.
- **utils.py, status.py, errors.py, constants.py**: Utility functions and definitions.

### pywebdav/server/ - Reference Server Implementation
- **server.py**: Entry point for the standalone server. Contains `run()` function (CLI wrapper with argument parsing) and `runserver()` function (internal server startup). The `davserver` console script calls `run()`.
- **fshandler.py**: `FilesystemHandler` class implements the `dav_interface` for serving files from a local filesystem. This serves as the reference implementation for custom backends.
- **fileauth.py**: `DAVAuthHandler` - authentication handler implementation.
- **mysqlauth.py**: `MySQLAuthHandler` - optional MySQL-based authentication.
- **daemonize.py**: Unix daemon support for server.

### Key Architectural Pattern
The WebDAVServer class requires an interface class (implementing `dav_interface`) to connect to actual data. This separation allows backends for filesystems, databases, or other storage. The interface class is instantiated by WebDAVServer and called for property retrieval, resource creation, data access, etc. XML parsing for each DAV method is factored into dedicated classes (propfind.py, etc.) which obtain data through the interface class.

## Development Commands

### Build and Package
```bash
python -m build                    # Build distribution packages (requires build module)
twine check dist/*                 # Validate package format
```

### Installation
```bash
pip install -e .                   # Development installation
pip install PyWebDAV3              # Install from PyPI
```

### Running the Server
```bash
davserver -D /tmp -n -J            # Run server: -D=directory, -n=no auth, -J=no lock
davserver -D /path -u user -p pass # Run with authentication
davserver --help                   # Full options list
```

Common options:
- `-D/--directory`: Root directory to serve (default: /tmp)
- `-H/--host`: Listen host (default: localhost)
- `-P/--port`: Port number (default: 8008)
- `-u/--user`, `-p/--password`: Authentication credentials
- `-n/--noauth`: Disable authentication
- `-J/--nolock`: Disable LOCK/UNLOCK (WebDAV level 2)
- `-M/--nomime`: Disable mimetype sniffing
- `-T/--noiter`: Disable iterator (fixes some corruption issues)
- `-v/--verbose`: Verbose output
- `-l/--loglevel`: Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `-d/--daemon`: Daemon mode (start|stop|restart|status)

### Testing
```bash
python test/test_litmus.py         # Run litmus WebDAV compliance tests (from repo root)
```

The test suite uses litmus 0.13, a C-based WebDAV server protocol compliance test suite originally by Joe Orton. The test harness (`test/test_litmus.py`) automatically:
1. Extracts and compiles litmus from `test/litmus-0.13.tar.gz` on first run (`./configure && make`)
2. Starts a temporary davserver instance on port 38028
3. Runs the full litmus test battery via `make check`
4. Verifies both authenticated (user: test, pass: pass) and non-authenticated modes

#### Litmus Test Suites
Litmus comprises 5 separate test executables that each verify different WebDAV functionality:

- **basic**: Core WebDAV level 1 operations
  - OPTIONS (DAV: header checking)
  - PUT, GET with byte-level comparison
  - MKCOL (collection creation)
  - DELETE (both collections and non-collections)
  - put_no_parent (error handling)

- **copymove**: COPY and MOVE operations testing all combinations
  - Overwrite true/false
  - Destination exists/doesn't exist
  - Collection/non-collection resources
  - Depth: 0 COPY of collections

- **props**: Property manipulation and querying (PROPFIND, PROPPATCH)
  - Set, delete, replace properties
  - Dead property persistence across COPY
  - Namespace handling
  - Unicode values in property values
  - PROPPATCH propertyupdate evaluation order

- **locks**: WebDAV level 2 locking (LOCK, UNLOCK)
  - Lock/unlock operations
  - Exclusive vs shared locks
  - Lock discovery
  - Attempts to modify locked resources (as owner vs non-owner)
  - PROPPATCH on locked resources
  - Collection locking
  - If: header handling with lock-tokens and etags

- **http**: HTTP protocol-level tests
  - Conditional requests
  - expect100 handling
  - Non-ASCII characters in URIs

Each test adds an `X-Litmus-One` header to requests for debugging. After running, `debug.log` contains full network traces. Tests run against a temporary directory and require ability to create a `litmus` collection at the target URL.

#### Manual Litmus Testing
To run litmus tests manually for debugging:
```bash
cd test/litmus-0.13
sh ./configure && make                    # Compile litmus (one-time)
davserver -D /tmp/davtest -n &            # Start server in background
make URL=http://localhost:8008/ check     # Run all test suites
make URL=http://localhost:8008/ CREDS="user pass" check  # With auth
./basic http://localhost:8008/            # Run single test suite
./locks http://localhost:8008/ user pass  # Single suite with credentials
```
After tests complete, examine `debug.log` for full request/response traces.

### CI/CD
GitHub Actions workflow (`.github/workflows/python-package.yml`) runs on push/PR to master:
- Tests Python 3.8, 3.9, 3.10
- Builds package and validates with twine
- Runs litmus test suite

## Version Management
Uses `git-versioner` for version numbers from git tags. Version is read from `pywebdav.__version__` which is populated by the versioner.

## Dependencies
- `six`: Python 2/3 compatibility (maintained for legacy reasons)
- `git-versioner`: Version management from git tags

Optional:
- MySQL support requires MySQLdb (install separately: `pip install mysqlclient`)
