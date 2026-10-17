"""Current user's profile photo. The database stores a URL, never image bytes."""
from datetime import datetime, timezone
from io import BytesIO
import logging
from pathlib import Path
import re
import unicodedata
import warnings
from fastapi import APIRouter, Depends, File, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.core.config import get_settings
from src.core.database import get_db
from src.core.errors import ApplicationError
from src.core.mapping import to_user
from src.core.models import AuditModel, UserModel
from src.features.auth.infrastructure.dependencies import current_user
from src.features.users.domain.dto.UserDTO import ProfileUpdate, UserResponse
from src.features.users.infrastructure.adapters.MySQL import snapshot

router = APIRouter(prefix='/profile', tags=['Profile'])
logger = logging.getLogger(__name__)
PHOTO_URL_PREFIX = '/upload/photos_profile/'
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 25_000_000


def converted_photo(data: bytes) -> bytes:
    if not data:
        raise ApplicationError('Selecciona una imagen JPEG, PNG o WebP', 422)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise ApplicationError('Solo se permiten imágenes JPEG, PNG o WebP', 422)
                if original.width * original.height > MAX_PIXELS:
                    raise ApplicationError('La imagen no debe superar 25 megapíxeles', 422)
                if getattr(original, 'n_frames', 1) != 1:
                    raise ApplicationError('Selecciona una imagen sin animación', 422)
                original.load()
                oriented = ImageOps.exif_transpose(original)
                # Explicit conversion and save options avoid preserving EXIF/GPS or original metadata.
                image = oriented.convert('RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB')
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format='WEBP', quality=85, method=6)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ApplicationError('La imagen no es válida o está dañada', 422) from exc


def safe_part(value: str, fallback: str) -> str:
    ascii_value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]', '', ascii_value) or fallback


def stored_path(directory: Path, url: str | None) -> Path | None:
    if not url or not url.startswith(PHOTO_URL_PREFIX):
        return None
    name = url.removeprefix(PHOTO_URL_PREFIX)
    if not re.fullmatch(r'[a-z0-9]+\.webp', name):
        return None
    return directory / name


@router.get('', response_model=UserResponse)
def profile(actor=Depends(current_user)):
    return UserResponse.from_user(actor)


@router.patch('', response_model=UserResponse)
def update_profile(request: ProfileUpdate, actor=Depends(current_user),
                   db: Session = Depends(get_db, scope='function')):
    row = db.scalar(select(UserModel).where(UserModel.id == actor.id).with_for_update()
                    .execution_options(populate_existing=True))
    if row is None or not row.active or row.token_version != actor.token_version:
        raise ApplicationError('Invalid or expired access token', 401)
    before = snapshot(row)
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.flush()
    after = snapshot(row)
    if after != before:
        db.add(AuditModel(user_id=actor.id, table='users', record_id=actor.id,
                          action='UPDATE', old_values=before, new_values=after))
        db.flush()
    return UserResponse.from_user(to_user(row))


@router.post('/photo', response_model=UserResponse)
def upload_photo(file: UploadFile = File(...), actor=Depends(current_user),
                 db: Session = Depends(get_db, scope='function')):
    try:
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        file.file.close()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApplicationError('La foto no debe superar 5 MB', 413)
    webp = converted_photo(data)
    # Lock and refresh after decoding: concurrent uploads replace the latest committed photo.
    row = db.scalar(select(UserModel).where(UserModel.id == actor.id).with_for_update()
                    .execution_options(populate_existing=True))
    if row is None or not row.active or row.token_version != actor.token_version:
        raise ApplicationError('Invalid or expired access token', 401)
    directory = get_settings().profile_photos_dir
    directory.mkdir(parents=True, exist_ok=True)
    previous_url = row.profile_photo_url
    path = None
    try:
        for _ in range(5):
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
            name = safe_part(row.role.name, 'rol')[:60] + safe_part(row.name, 'usuario')[:120] + stamp + '.webp'
            candidate = directory / name
            try:
                destination = candidate.open('xb')
            except FileExistsError:
                continue
            path = candidate
            with destination:
                destination.write(webp)
            break
        if path is None:
            raise ApplicationError('No se pudo guardar la foto. Intenta nuevamente', 503)
        row.profile_photo_url = PHOTO_URL_PREFIX + path.name
        db.add(AuditModel(user_id=actor.id, table='users', record_id=actor.id, action='UPDATE',
                          old_values={'profile_photo_url': previous_url},
                          new_values={'profile_photo_url': row.profile_photo_url}))
        db.flush()
        result = UserResponse.from_user(to_user(row))
        # Publish the new reference before removing the old file; rollback keeps the old photo usable.
        db.commit()
    except BaseException:
        db.rollback()
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    old_path = stored_path(directory, previous_url)
    if old_path is not None:
        try:
            old_path.unlink(missing_ok=True)
        except OSError:
            logger.warning('Profile photo saved but previous file could not be removed for user %s', actor.id)
    return result
