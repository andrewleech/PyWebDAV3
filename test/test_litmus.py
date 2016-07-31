import re
import os
import sys
import time
import shutil
import tarfile
import tempfile
import threading
import subprocess

testdir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(testdir, '..'))

import pywebdav.server.server

def test_run_litmus():

    #  Compile litmus
    litmus_dist = os.path.join(testdir, 'litmus-0.13')
    litmus = os.path.join(litmus_dist, 'litmus')
    if not os.path.exists(litmus):
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

    # Run davserver
    user = 'test'
    password = 'pass'
    rundir = tempfile.mkdtemp()
    result = []
    try:

        sys.argv = sys.argv[0:1] + ['-D', rundir, '-u', user, '-p', password, '-H', 'localhost', '--port', '8078']
        davthread = threading.Thread(target=pywebdav.server.server.run)
        davthread.daemon = True
        davthread.start()
        time.sleep(2)

        # Run Litmus
        try:
            results = subprocess.check_output([litmus, 'http://localhost:8078', user, password])
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
        shutil.rmtree(rundir)
