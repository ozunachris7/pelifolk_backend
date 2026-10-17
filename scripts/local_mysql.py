"""Owned local MySQL instance for recovery drills; never reads application settings."""
from contextlib import contextmanager
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile
import time
import pymysql


@contextmanager
def temporary_mysql():
    binary = shutil.which('mysqld')
    if not binary:
        raise RuntimeError('Install MySQL Server locally to verify a backup')
    version = subprocess.check_output([binary, '--no-defaults', '--version'], text=True)
    if 'MariaDB' in version:
        raise RuntimeError('Recovery verification requires MySQL, not MariaDB')
    root = Path(tempfile.mkdtemp(prefix='pelifolk-recovery-'))
    data = root / 'data'
    data.mkdir()
    socket = str(root / 'mysql.sock')
    base = [binary, '--no-defaults', '--user=' + pwd.getpwuid(os.getuid()).pw_name,
            '--datadir=' + str(data)]
    process = None
    try:
        with (root / 'initialize.log').open('w') as log:
            subprocess.run(base + ['--initialize-insecure'], stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=60)
        with (root / 'launcher.log').open('w') as log:
            process = subprocess.Popen(base + ['--skip-networking', '--mysqlx=OFF',
                '--socket=' + socket, '--pid-file=' + str(root / 'mysql.pid'),
                '--log-error=' + str(root / 'mysql.log'), '--innodb-buffer-pool-size=128M'],
                stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('Temporary MySQL stopped; inspect ' + str(root))
            try:
                connection = pymysql.connect(unix_socket=socket, user='root', connect_timeout=1)
                connection.close()
                break
            except pymysql.MySQLError:
                time.sleep(.2)
        else:
            raise RuntimeError('Temporary MySQL startup timed out; inspect ' + str(root))
        yield root, socket
    finally:
        if process is not None and process.poll() is None:
            connection = pymysql.connect(unix_socket=socket, user='root', connect_timeout=5)
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SHUTDOWN')
            finally:
                connection.close()
            process.wait(timeout=30)
        if process is not None and process.poll() is None:
            raise RuntimeError('Could not confirm temporary MySQL shutdown: ' + str(root))
        # Keep diagnostics and recovery data private for review; no live server is left running.
        print('Recovery instance stopped. Private artifacts:', root, flush=True)
