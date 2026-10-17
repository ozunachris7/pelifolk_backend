"""Restore a trusted Pelifolk backup in a NEW local MySQL with networking disabled."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import pymysql
from scripts.backup import IDENTIFIER, checksum
from scripts.local_mysql import temporary_mysql


def read_manifest(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / 'manifest.json').read_text())
    if (manifest.get('format') != 1 or manifest.get('file') != 'database.sql.gz' or
            not IDENTIFIER.fullmatch(str(manifest.get('database', ''))) or
            not re.fullmatch(r'[0-9a-f]{64}', str(manifest.get('sha256', '')))):
        raise ValueError('Invalid backup manifest')
    archive = folder / 'database.sql.gz'
    if archive.stat().st_size != manifest.get('bytes') or checksum(archive) != manifest['sha256']:
        raise ValueError('Backup integrity check failed; do not restore this file')
    return manifest, archive


def inventory(socket, database):
    """Hash every row and list programmable objects; no clinical values enter the report."""
    connection = pymysql.connect(unix_socket=socket, user='root', database=database)
    result = {'tables': {}, 'views': [], 'routines': [], 'triggers': [], 'events': []}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SHOW FULL TABLES')
            tables = cursor.fetchall()
            for name, kind in tables:
                escaped = '`' + name.replace('`', '``') + '`'
                if kind == 'VIEW':
                    # Evaluate views too: catches unresolved definers and schema references.
                    cursor.execute('SELECT * FROM ' + escaped + ' LIMIT 1')
                    cursor.fetchall()
                    result['views'].append(name)
                    continue
                with connection.cursor(pymysql.cursors.SSCursor) as rows:
                    rows.execute('SELECT * FROM ' + escaped)
                    hashes = [sha256(repr(row).encode()).digest() for row in rows]
                digest = sha256(b''.join(sorted(hashes))).hexdigest()
                result['tables'][name] = {'rows': len(hashes), 'sha256': digest}
            for key, query in [
                ('routines', 'SELECT ROUTINE_NAME, ROUTINE_TYPE FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA=%s'),
                ('triggers', 'SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s'),
                ('events', 'SELECT EVENT_NAME FROM information_schema.EVENTS WHERE EVENT_SCHEMA=%s'),
            ]:
                cursor.execute(query, (database,))
                result[key] = sorted([list(row) for row in cursor.fetchall()])
            result['views'].sort()
        return result
    finally:
        connection.close()


def verify_backup(folder, *, validate=None):
    manifest, archive = read_manifest(folder)
    binary = shutil.which('mysql')
    if not binary:
        raise RuntimeError('Install the MySQL command-line client')
    started = time.monotonic()
    with temporary_mysql() as (root, socket):
        database = manifest['database']
        connection = pymysql.connect(unix_socket=socket, user='root')
        try:
            with connection.cursor() as cursor:
                cursor.execute('CREATE DATABASE `' + database + '` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
        finally:
            connection.close()
        sql = root / 'restore.sql'
        try:
            with gzip.open(archive, 'rb') as source, sql.open('xb') as target:
                sql.chmod(0o600)
                shutil.copyfileobj(source, target)
            with sql.open('rb') as source, (root / 'restore.log').open('wb') as log:
                result = subprocess.run([binary, '--no-defaults', '--no-login-paths',
                    '--protocol=SOCKET', '--socket=' + socket, '--user=root', database],
                    stdin=source, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError('Restore failed; inspect private diagnostics in ' + str(root))
        finally:
            sql.unlink(missing_ok=True)
        restored = inventory(socket, database)
        if validate is not None:
            validate(socket, database, restored)
        report = {'result': 'restored', 'network': 'disabled',
                  'backup_sha256': manifest['sha256'], 'inventory': restored,
                  'elapsed_seconds': round(time.monotonic() - started, 2)}
        (root / 'restoration.json').write_text(json.dumps(report, indent=2) + '\n')
    # Only report success after confirmed shutdown of the owned server.
    report['server_stopped'] = True
    (root / 'restoration.json').write_text(json.dumps(report, indent=2) + '\n')
    return report, root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup_folder', help='Trusted backup folder containing manifest.json and database.sql.gz')
    args = parser.parse_args()
    report, root = verify_backup(args.backup_folder)
    print('Backup restored and views queried in isolation. Report:', root / 'restoration.json')
    print('This verifies readability, not equality to the current live database or live recovery time.')


if __name__ == '__main__':
    main()
