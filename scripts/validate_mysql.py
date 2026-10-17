"""Run reproducible MySQL checks in an owned temporary server, without application DB credentials."""
import argparse
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time

import pymysql
from sqlalchemy.engine import URL


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',choices=('all','migrations','concurrency','volume'),default='all')
    args=parser.parse_args()
    binary=shutil.which('mysqld')
    if not binary:
        parser.error('MySQL Server is required locally (mysqld); this command never connects to DATABASE_URL')
    version=subprocess.run([binary,'--no-defaults','--version'],check=True,capture_output=True,text=True).stdout.strip()
    if 'MariaDB' in version:
        parser.error('Use MySQL 8 or later; MariaDB is not the engine validated by this suite')
    root=Path(tempfile.mkdtemp(prefix='pelifolk-mysql-validation-'))
    data=root/'data';data.mkdir()
    socket=str(root/'mysql.sock')
    user=pwd.getpwuid(os.getuid()).pw_name
    base=[binary,'--no-defaults','--user='+user,'--datadir='+str(data)]
    process=None
    summary={'mysql_version':version,'suite':args.suite,'network':'disabled','result':'initializing'}
    print('Instancia MySQL aislada, sin puerto de red. Artefactos:',root,flush=True)
    try:
        with (root/'initialize.log').open('w') as log:
            initialized=subprocess.run(base+['--initialize-insecure'],stdout=log,stderr=subprocess.STDOUT,timeout=60)
        if initialized.returncode:
            raise RuntimeError('MySQL initialization failed; inspect '+str(root/'initialize.log'))
        with (root/'launcher.log').open('w') as log:
            process=subprocess.Popen(base+['--skip-networking','--mysqlx=OFF','--socket='+socket,
                '--pid-file='+str(root/'mysql.pid'),'--log-error='+str(root/'mysql.log'),
                '--innodb-buffer-pool-size=128M'],stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Temporary MySQL stopped; inspect '+str(root/'mysql.log'))
            try:
                conn=pymysql.connect(unix_socket=socket,user='root',connect_timeout=1)
                with conn.cursor() as cursor:
                    cursor.execute('SELECT VERSION()');summary['server_version']=cursor.fetchone()[0]
                conn.close();break
            except pymysql.MySQLError:
                time.sleep(.2)
        else:
            raise RuntimeError('Temporary MySQL did not become ready within 40 seconds')
        env=os.environ.copy()
        env['PELIFOLK_TEST_MYSQL_URL']=URL.create('mysql+pymysql',username='root',query={'unix_socket':socket}).render_as_string(hide_password=False)
        env['PYTEST_ADDOPTS']=''
        junit=root/'results.xml'
        command=[sys.executable,'-m','pytest']
        if args.suite=='all':command+=['tests','--mysql-api']
        elif args.suite=='migrations':command+=['tests/test_migrations.py','-k','mysql']
        else:command+=['tests/test_mysql_validation.py','--mysql-api','-k','mysql_concurrent' if args.suite=='concurrency' else 'mysql_volume','-s']
        command+=['-q','--tb=short','--junitxml='+str(junit)]
        started=time.perf_counter()
        with (root/'pytest.log').open('w') as logfile:
            child=subprocess.Popen(command,cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            try:
                for line in child.stdout:
                    print(line,end='',flush=True);logfile.write(line)
                code=child.wait()
            except BaseException:
                child.terminate();child.wait(timeout=30);raise
        summary.update(result='passed' if code==0 else 'failed',exit_code=code,duration_seconds=round(time.perf_counter()-started,2))
        return code
    finally:
        shutdown_error=None
        if process is not None and process.poll() is None:
            try:
                # Some MySQL/AppArmor installations reject Unix signals even for the launcher.
                # The isolated local administrator can request the normal SQL shutdown instead.
                conn=pymysql.connect(unix_socket=socket,user='root',connect_timeout=5)
                try:
                    with conn.cursor() as cursor:cursor.execute('SHUTDOWN')
                finally:conn.close()
                process.wait(timeout=30)
            except (pymysql.MySQLError, subprocess.TimeoutExpired) as exc:
                shutdown_error=type(exc).__name__
        summary['server_stopped']=process is None or process.poll() is not None
        if shutdown_error:summary['shutdown_error']=shutdown_error
        (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print('MySQL temporal detenido.' if summary['server_stopped'] else 'MySQL temporal pendiente de cierre.',
              'Logs, resultados y datos conservados en:',root,flush=True)
        if not summary['server_stopped']:
            raise RuntimeError('Could not confirm temporary server shutdown; inspect '+str(root/'summary.json'))


if __name__=='__main__':
    raise SystemExit(main())
