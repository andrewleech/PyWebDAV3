import re
import os
import sys
import time
import shutil
import signal
import tarfile
import tempfile
import subprocess

testdir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(testdir, '..'))

import pywebdav.server.server

def test_run_litmus():

    # Run davserver
    user = 'test'
    password = 'pass'
    port = 38028
    rundir = tempfile.mkdtemp()
    result = []
    proc = None
    try:
        print('Starting davserver')
        davserver_cmd = [sys.executable, os.path.join(testdir,'..','pywebdav','server','server.py'),'-D', rundir, '-u', user, '-p', password, '-H', 'localhost', '--port', str(port)]
        proc = subprocess.Popen(davserver_cmd)

        #  Compile litmus
        litmus_dist = os.path.join(testdir, 'litmus-0.13')
        litmus = os.path.join(litmus_dist, 'litmus')
        if not os.path.exists(litmus):
            print('Compiling litmus test suite')

            if os.path.exists(litmus_dist):
                shutil.rmtree(litmus_dist)
            with tarfile.open(litmus_dist+'.tar.gz') as tf:
                tf.extractall(path=testdir)
            ret = subprocess.call('./configure', shell=True, cwd=litmus_dist)
            assert ret == 0
            ret = subprocess.call('make', shell=True, cwd=litmus_dist)
            assert ret == 0
            litmus = os.path.join(litmus_dist, 'litmus')
            assert os.path.exists(litmus)
        else:
            # Ensure davserver has time to start
            time.sleep(1)

        # Run Litmus
        print('Running litmus')
        try:
            results = subprocess.check_output([litmus, 'http://localhost:%d' % port, user, password])
        except subprocess.CalledProcessError as ex:
            results = ex.output
        lines = results.decode().split('\n')
        for line in lines:
            line = line.split('\r')[-1]
            result.append(line)
            if len(re.findall('^ *\d+\.', line)):
                assert line.endswith('pass'), line

    finally:
        print('\n'.join(result))
        if proc:
            proc.kill()
        # os.killpg(0, signal.SIGKILL)  # kill all processes in my group
        shutil.rmtree(rundir)
