import re
import os
import sys
import time
import shutil
import tarfile
import tempfile
import unittest
import subprocess
from subprocess import run

testdir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(testdir, '..'))

import pywebdav.server.server

# Run davserver
user = 'test'
password = 'pass'
port = 38028


class Test(unittest.TestCase):
    def setUp(self):

        self.rundir = tempfile.mkdtemp()
        self._ensure_litmus()

    def _ensure_litmus(self):

        self.litmus_dist = os.path.join(testdir, 'litmus-0.13')
        self.litmus = os.path.join(self.litmus_dist, 'litmus')
        if not os.path.exists(self.litmus):
            print('Compiling litmus test suite')

            if os.path.exists(self.litmus_dist):
                shutil.rmtree(self.litmus_dist)
            with tarfile.open(self.litmus_dist + '.tar.gz') as tf:
                tf.extractall(path=testdir)
            ret = run(['sh', './configure'], cwd=self.litmus_dist)
            # assert ret == 0
            ret = run(['make'], cwd=self.litmus_dist)
            # assert ret == 0
            litmus = os.path.join(self.litmus_dist, 'litmus')
            # assert os.path.exists(litmus)

    def tearDown(self):
        print("Cleaning up tempdir")
        shutil.rmtree(self.rundir)

    def test_run_litmus(self):

        result = []
        proc = None
        try:
            print('Starting davserver')
            davserver_cmd = [sys.executable, os.path.join(testdir, '..', 'pywebdav', 'server', 'server.py'), '-D',
                             self.rundir, '-u', user, '-p', password, '-H', 'localhost', '--port', str(port)]
            self.davserver_proc = subprocess.Popen(davserver_cmd)
            # Ensure davserver has time to startup
            time.sleep(1)

            # Run Litmus
            print('Running litmus')
            try:
                ret = run(["make", "URL=http://localhost:%d" % port, 'CREDS="%s %s"' % (user, password), "check"], cwd=self.litmus_dist, capture_output=True)
                results = ret.stdout
            except subprocess.CalledProcessError as ex:
                results = ex.output
            lines = results.decode().split('\n')
            assert len(lines), "No litmus output"
            for line in lines:
                line = line.split('\r')[-1]
                result.append(line)
                if len(re.findall('^ *\d+\.', line)):
                    assert line.endswith('pass'), line

        finally:
            print('\n'.join(result))

            print('Stopping davserver')
            self.davserver_proc.kill()


    def test_run_litmus_noauth(self):

        result = []
        proc = None
        try:
            print('Starting davserver')
            davserver_cmd = [sys.executable, os.path.join(testdir, '..', 'pywebdav', 'server', 'server.py'), '-D',
                             self.rundir, '-n', '-H', 'localhost', '--port', str(port)]
            self.davserver_proc = subprocess.Popen(davserver_cmd)
            # Ensure davserver has time to startup
            time.sleep(1)

            # Run Litmus
            print('Running litmus')
            try:
                ret = run(["make", "URL=http://localhost:%d" % port, "check"], cwd=self.litmus_dist, capture_output=True)
                results = ret.stdout
                
            except subprocess.CalledProcessError as ex:
                results = ex.output
            lines = results.decode().split('\n')
            assert len(lines), "No litmus output"
            for line in lines:
                line = line.split('\r')[-1]
                result.append(line)
                if len(re.findall('^ *\d+\.', line)):
                    assert line.endswith('pass'), line

        finally:
            print('\n'.join(result))

            print('Stopping davserver')
            self.davserver_proc.kill()
            
if __name__ == "__main__":
    unittest.main()
    