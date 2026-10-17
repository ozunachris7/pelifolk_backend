import gzip
import json
from pathlib import Path
import pytest
from scripts.backup import checksum, create_backup, private_client_file
from scripts.verify_backup import read_manifest, verify_backup


def backup_fixture(tmp_path):
    archive = tmp_path / 'database.sql.gz'
    with gzip.open(archive, 'wb') as file:
        file.write(b'SELECT 1;\n')
    manifest = {'format': 1, 'database': 'example', 'file': archive.name,
                'bytes': archive.stat().st_size, 'sha256': checksum(archive)}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    return manifest, archive


def test_modified_backup_is_rejected_before_starting_mysql(tmp_path, monkeypatch):
    import scripts.verify_backup as verifier
    _, archive = backup_fixture(tmp_path)
    archive.write_bytes(archive.read_bytes() + b'corrupted')
    def forbidden():
        pytest.fail('Do not start a restore after integrity failure')
    monkeypatch.setattr(verifier, 'temporary_mysql', forbidden)
    with pytest.raises(ValueError, match='integrity'):
        verify_backup(tmp_path)


def test_same_length_corruption_is_detected(tmp_path):
    _, archive = backup_fixture(tmp_path)
    content = bytearray(archive.read_bytes())
    content[-1] ^= 1
    archive.write_bytes(content)
    with pytest.raises(ValueError, match='integrity'):
        read_manifest(tmp_path)


@pytest.mark.parametrize('changes', [
    {'database': 'example;DROP DATABASE other'}, {'database': '../other'},
    {'file': '../other.sql.gz'}, {'format': 2}, {'sha256': 'bad'},
])
def test_invalid_manifest_cannot_choose_another_path_or_sql(tmp_path, changes):
    manifest, _ = backup_fixture(tmp_path)
    (tmp_path / 'manifest.json').write_text(json.dumps({**manifest, **changes}))
    with pytest.raises(ValueError, match='manifest'):
        read_manifest(tmp_path)


def test_client_credentials_require_private_permissions(tmp_path):
    config = tmp_path / 'client.cnf'
    config.write_text('[client]\npassword=fictional\n')
    config.chmod(0o644)
    with pytest.raises(ValueError, match='600'):
        private_client_file(config)
    config.chmod(0o600)
    assert private_client_file(config) == config


def test_backup_refuses_public_output_folder(tmp_path):
    config = tmp_path / 'client.cnf'
    config.write_text('[client]\nuser=fictional\n')
    config.chmod(0o600)
    folder = tmp_path / 'public'
    folder.mkdir(mode=0o755)
    with pytest.raises(ValueError, match='700'):
        create_backup(config, 'example', folder)


def test_failed_dump_never_becomes_a_successful_backup(tmp_path, monkeypatch):
    import scripts.backup as backup
    config = tmp_path / 'client.cnf'
    config.write_text('[client]\npassword=fictional\n')
    config.chmod(0o600)
    binary = tmp_path / 'failed-dump'
    binary.write_text('#!/bin/sh\necho "private diagnostic" >&2\nprintf "partial SQL"\nexit 1\n')
    binary.chmod(0o700)
    monkeypatch.setattr(backup.shutil, 'which', lambda name: str(binary))
    output = tmp_path / 'backups'
    with pytest.raises(RuntimeError, match='Backup failed'):
        create_backup(config, 'example', output)
    folder = next(output.iterdir())
    assert not (folder / 'database.sql').exists()
    assert not (folder / 'manifest.json').exists()
    assert (folder / 'dump.log').stat().st_mode & 0o077 == 0
    assert folder.stat().st_mode & 0o077 == 0
