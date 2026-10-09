# Pelifolk backend

API en Python y FastAPI. Conserva la estructura por features: domain, application e infrastructure; auth también utiliza controllers. `core` contiene configuración, conexión, seguridad y modelos compartidos. La implementación inicial cubre auth, users y roles.

## Instalación en PowerShell

Ejecutar desde la carpeta pelifolk-back:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Editar `.env`: configurar DATABASE_URL y usar el secreto generado como JWT_SECRET. La API exige configuración explícita; no contiene credenciales de demostración. No compartir ni versionar `.env`.

## Base de datos MySQL

Elegir **uno** de estos scripts para una instalación nueva en MySQL Workbench:

- `database/auth_schema.sql`: únicamente auth, users, roles y auditoría.
- `database/schema.sql`: traducción completa del esquema demo a identificadores y valores de negocio en inglés, con las mismas tablas de autenticación.

No ejecutar ambos. Ninguno migra ni elimina la base `ganaderia` existente. Una migración de sus datos requiere respaldo y una estrategia explícita; los apellidos existentes no se pueden inventar. El esquema completo conserva el modelado del demo; los ajustes sanitarios, reproductivos y económicos de la revisión anterior siguen pendientes. Los catálogos de esos módulos todavía no tienen datos iniciales.

`users` incluye `name`, `paternal_lastname`, `maternal_lastname`, `email`, `phone`, `role_id`, `password_hash`, `active`, `token_version` y `created_at`. Cada usuario tiene un rol, igual que en el demo. Los identificadores son UUID.

Roles iniciales: `owner` (dueño), `administrator` (administrador), `manager` (encargado), `worker` (trabajador), `veterinarian` y `livestock_technician`. Owner y administrator pueden gestionar usuarios y roles. Los demás pueden iniciar sesión y consultar su propia identidad; sus permisos de negocio se incorporarán con cada módulo. Los seis roles iniciales están protegidos contra edición/borrado para conservar una vía de administración. Los roles personalizados pueden crearse, modificarse y eliminarse si no tienen usuarios asignados.

Los permisos disponibles inicialmente son `users:read`, `users:write`, `roles:read` y `roles:write`. Roles nuevos reciben únicamente los permisos elegidos, sin privilegios automáticos. Un gestor no puede otorgar permisos que no posee ni modificar cuentas o roles con permisos superiores a los suyos. Este backend opera para un solo rancho; la separación entre múltiples ranchos queda pendiente.

## Primer dueño y servidor

Después de aplicar el SQL y configurar `.env`:

```powershell
.\.venv\Scripts\python.exe -m scripts.bootstrap --email owner@example.com --name Christhoper --paternal-lastname Ozuna --maternal-lastname "APELLIDO_MATERNO"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

El bootstrap solicita y confirma la contraseña, mínimo 12 caracteres. Solo funciona cuando no existen usuarios; no crea una contraseña fija. Documentación interactiva: http://localhost:8000/docs.

## Endpoints

| Método | Ruta | Acceso |
| --- | --- | --- |
| POST | /api/v1/auth/login | Público; JSON email y password |
| GET | /api/v1/auth/me | Sesión activa |
| POST | /api/v1/auth/logout | Sesión activa |
| GET | /api/v1/users | users:read; offset y limit |
| GET | /api/v1/users/{id} | users:read |
| POST | /api/v1/users | users:write |
| PATCH | /api/v1/users/{id} | users:write |
| DELETE | /api/v1/users/{id} | users:write; desactivación, no borrado |
| GET | /api/v1/roles/permissions | roles:read |
| GET | /api/v1/roles | roles:read |
| POST | /api/v1/roles | roles:write |
| PUT | /api/v1/roles/{id} | roles:write; reemplazo de nombre/permisos |
| DELETE | /api/v1/roles/{id} | roles:write |

Después del login, enviar `Authorization: Bearer <access_token>`. La respuesta incluye usuario, apellido, rol y permisos. No devuelve hashes. No hay registro público: un administrador crea las cuentas.

Ejemplo de rol nuevo:

```json
{"name": "health_supervisor", "permissions": ["users:read", "roles:read"]}
```

Ejemplo de usuario:

```json
{"name": "Ana", "paternal_lastname": "López", "maternal_lastname": "Pérez", "email": "ana@example.com", "password": "A-long-unique-password", "role_id": "00000000-0000-4000-8000-000000000005"}
```

Contraseñas con Argon2 y JWT HS256 con issuer/audience y vencimiento. Logout invalida **todas las sesiones del usuario**; cambios de contraseña, rol o actividad también invalidan sus tokens. Los permisos se leen de la base en cada solicitud. Tokens vencidos requieren nuevo login; refresh tokens y recuperación de contraseña quedan pendientes. Antes de publicar, incorporar HTTPS y límites de intentos de login en la infraestructura.

Creación, edición y desactivación de usuarios, y cambios de roles, generan auditoría en la misma transacción. No se auditan contraseñas ni hashes. No se permite cambiar el propio rol, desactivar la propia cuenta ni modificar el rol personalizado del propio actor.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan SQLite temporal en memoria para verificar HTTP, casos de uso y persistencia del módulo de seguridad. No ejecutan el SQL completo ni sustituyen una prueba de integración con MySQL, sus triggers y su collation. El frontend actual todavía usa su login demo y requiere conexión a estos endpoints.

Referencias técnicas: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ y https://docs.sqlalchemy.org/en/20/core/engines.html.
