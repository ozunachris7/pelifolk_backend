"""Create a logical backup using an explicit private MySQL client file, never .env."""
import argparse
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile


IDENTIFIER = re.compile(r'[A-Za-z0-9_]{1,64}\Z')


def private_client_file(path):
    path = Path(path).resolve()
    if not path.is_file() or path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError('The MySQL client file must exist and have mode 600 (or 400)')
    if path.stat().st_uid != os.getuid():
        raise ValueError('The MySQL client file must belong to the current user')
    return path


def checksum(path):
    digest = sha256()
    with Path(path).open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(client_file, database, output_dir):
    client_file = private_client_file(client_file)
    if not IDENTIFIER.fullmatch(database):
        raise ValueError('Use a database name with letters, numbers or underscores')
    binary = shutil.which('mysqldump')
    if not binary:
        raise RuntimeError('Install the MySQL mysqldump client')
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    if output_dir.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError('Backup output directory must have mode 700')
    folder = Path(tempfile.mkdtemp(prefix='pelifolk-backup-', dir=output_dir))
    sql = folder / 'database.sql'
    archive = folder / 'database.sql.gz'
    command = [binary, '--defaults-file=' + str(client_file), '--no-login-paths',
               '--single-transaction', '--quick', '--routines', '--triggers', '--events',
               '--no-tablespaces', '--set-gtid-purged=OFF', '--column-statistics=0',
               '--hex-blob', '--skip-add-locks', '--skip-comments', database]
    try:
        with sql.open('xb') as file, (folder / 'dump.log').open('xb') as log:
            sql.chmod(0o600)
            (folder / 'dump.log').chmod(0o600)
            result = subprocess.run(command, stdout=file, stderr=log)
        if result.returncode:
            raise RuntimeError('Backup failed; inspect the private dump.log in ' + str(folder))
        with sql.open('rb') as source, archive.open('xb') as target:
            archive.chmod(0o600)
            with gzip.GzipFile(fileobj=target, mode='wb', mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        manifest = {'format': 1, 'database': database, 'file': archive.name,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'sha256': checksum(archive), 'bytes': archive.stat().st_size,
                    'dump_version': subprocess.check_output([binary, '--no-defaults', '--version'], text=True).strip(),
                    'includes': ['tables', 'data', 'views', 'routines', 'triggers', 'events'],
                    'encrypted': False}
        (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        (folder / 'manifest.json').chmod(0o600)
        return folder
    finally:
        sql.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-file', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    print('Backup created (not encrypted):', create_backup(args.client_file, args.database, args.output_dir))


if __name__ == '__main__':
    main()
