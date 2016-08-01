import re
import os
import sys
import time
import shutil
import tarfile
import tempfile
import unittest
import subprocess

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
        self._start_davserver()
        self._ensure_litmus()

    def _ensure_litmus(self):

        litmus_dist = os.path.join(testdir, 'litmus-0.13')
        self.litmus = os.path.join(litmus_dist, 'litmus')
        if not os.path.exists(self.litmus):
            print('Compiling litmus test suite')

            if os.path.exists(litmus_dist):
                shutil.rmtree(litmus_dist)
            with tarfile.open(litmus_dist + '.tar.gz') as tf:
                tf.extractall(path=testdir)
            ret = subprocess.call(['sh', './configure'], cwd=litmus_dist)
            assert ret == 0
            ret = subprocess.call(['make'], cwd=litmus_dist)
            assert ret == 0
            litmus = os.path.join(litmus_dist, 'litmus')
            assert os.path.exists(litmus)

    def _start_davserver(self):
        print('Starting davserver')
        davserver_cmd = [sys.executable, os.path.join(testdir, '..', 'pywebdav', 'server', 'server.py'), '-D',
                         self.rundir, '-u', user, '-p', password, '-H', 'localhost', '--port', str(port)]
        self.davserver_proc = subprocess.Popen(davserver_cmd)
        # Ensure davserver has time to startup
        time.sleep(1)

    def tearDown(self):
        print('Stopping davserver')
        self.davserver_proc.kill()

        print("Cleaning up tempdir")
        shutil.rmtree(self.rundir)

    def test_run_litmus(self):

        result = []
        proc = None
        try:
            # Run Litmus
            print('Running litmus')
            try:
                results = subprocess.check_output([self.litmus, 'http://localhost:%d' % port, user, password])
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
