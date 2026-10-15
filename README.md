# Pelifolk backend

> Estado actual y lista de pendientes: [docs/ESTADO_Y_PENDIENTES.md](docs/ESTADO_Y_PENDIENTES.md). Algunas notas de fases anteriores de este README describen limitaciones ya resueltas; consultar el inventario actualizado antes de planificar.


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

La API ejecuta las migraciones automáticamente al arrancar, antes de atender solicitudes. Crear una base vacía y configurar `DATABASE_URL` para apuntar a ella; puede ser `defaultdb` en Aiven. La base debe existir y el usuario necesita permisos para crear tablas, vistas, funciones, procedimientos y triggers, modificar tablas y eliminar los procedimientos auxiliares. No hace falta ejecutar SQL manualmente para una instalación nueva.

Las migraciones están en `database/migrations`, ordenadas por nombre. `0001_initial.sql` instala el esquema completo en inglés y los seis roles iniciales. No contiene `CREATE DATABASE`, `USE` ni una selección explícita del motor de almacenamiento. Se utiliza la base seleccionada por la conexión y el motor predeterminado del servidor, que debe soportar claves foráneas.

`schema_migrations` registra la versión, el checksum, el progreso y la fecha de aplicación. Los reinicios omiten versiones aplicadas. Un bloqueo de MySQL evita que varios workers migren a la vez. Si hay un error, el arranque falla y muestra la migración y sentencia afectadas. La migración inicial puede reanudarse tras corregir el problema; MySQL hace commits implícitos de DDL, por lo que no se promete rollback de toda la instalación.

No modificar una migración ya iniciada o aplicada: agregar un archivo nuevo, por ejemplo `0002_add_feature.sql`, con SQL que admita reintentos si el proceso se interrumpe después del DDL. El registro impide aplicar archivos modificados o arrancar con versiones registradas que ya no estén presentes en el proyecto.

Si la base contiene tablas o vistas y aún no tiene `schema_migrations`, el arranque se detiene sin modificar las tablas existentes. Una base anterior en español o una instalación manual requieren una migración explícita de estructura y datos; no se adoptan ni sobrescriben silenciosamente.

Los scripts siguientes se conservan como referencia y alternativa manual; no ejecutarlos antes del arranque automático:

- `database/auth_schema.sql`: únicamente auth, users, roles y auditoría.
- `database/schema.sql`: traducción completa del esquema demo a identificadores y valores de negocio en inglés, con las mismas tablas de autenticación.

No ejecutar ambos. Ninguno migra ni elimina la base `ganaderia` existente. Una migración de sus datos requiere respaldo y una estrategia explícita; los apellidos existentes no se pueden inventar. El esquema completo conserva el modelado del demo; los ajustes sanitarios, reproductivos y económicos de la revisión anterior siguen pendientes. Los catálogos de esos módulos todavía no tienen datos iniciales.

`users` incluye `name` (nombre), `middle_name` (segundo nombre opcional), `paternal_lastname`, `maternal_lastname`, `email`, `phone`, `role_id`, `password_hash`, `active`, `token_version` y `created_at`. El nombre y segundo nombre se guardan por separado. `0002_user_middle_name.sql` agrega el campo a instalaciones versionadas anteriores; no divide automáticamente los nombres existentes. El bootstrap admite `--middle-name`. Cada usuario tiene un rol, igual que en el demo. Los identificadores son UUID.

Roles iniciales: `owner` (dueño), `administrator` (administrador), `manager` (encargado), `worker` (trabajador), `veterinarian` y `livestock_technician`. Owner y administrator pueden gestionar usuarios y roles inicialmente. Los demás pueden iniciar sesión y consultar su propia identidad hasta que se les otorguen permisos. El rol owner está protegido para conservar una vía de administración. Los otros roles iniciales permiten editar sus permisos, pero conservan su nombre y no se eliminan. Ningún usuario puede modificar su propio rol asignado. Los roles personalizados pueden crearse, modificarse y eliminarse si no tienen usuarios asignados.

Los permisos disponibles inicialmente son `users:read`, `users:write`, `roles:read` y `roles:write`. Roles nuevos reciben únicamente los permisos elegidos, sin privilegios automáticos. Un gestor no puede otorgar permisos que no posee ni modificar cuentas o roles con permisos superiores a los suyos. Este backend opera para un solo rancho; la separación entre múltiples ranchos queda pendiente.

## Primer dueño y servidor

Después de configurar `.env`, arrancar primero la API para aplicar las migraciones. En otra terminal, crear el primer dueño:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
.\.venv\Scripts\python.exe -m scripts.bootstrap --email owner@example.com --name Christhoper --paternal-lastname Ozuna --maternal-lastname "APELLIDO_MATERNO"
```

En Linux:

```bash
source .venv/bin/activate
python -m uvicorn main:app --reload
```

El bootstrap solicita y confirma la contraseña, mínimo 8 caracteres. Solo funciona cuando no existen usuarios; no crea una contraseña fija. Documentación interactiva: http://localhost:8000/docs.

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
{"name": "Ana", "middle_name": "María", "paternal_lastname": "López", "maternal_lastname": "Pérez", "email": "ana@example.com", "password": "A-long-unique-password", "role_id": "00000000-0000-4000-8000-000000000005"}
```

Contraseñas con Argon2 y JWT HS256 con issuer/audience y vencimiento. Logout invalida **todas las sesiones del usuario**; cambios de contraseña, rol o actividad también invalidan sus tokens. Los permisos se leen de la base en cada solicitud. Tokens vencidos requieren nuevo login; refresh tokens y recuperación de contraseña quedan pendientes. Antes de publicar, incorporar HTTPS y límites de intentos de login en la infraestructura.

Creación, edición y desactivación de usuarios, y cambios de roles, generan auditoría en la misma transacción. No se auditan contraseñas ni hashes. No se permite cambiar el propio rol, desactivar la propia cuenta ni modificar el rol personalizado del propio actor.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan SQLite temporal en memoria para verificar HTTP, casos de uso y persistencia del módulo de seguridad. No ejecutan el SQL completo ni sustituyen una prueba de integración con MySQL, sus triggers y su collation. El frontend Angular conecta login, consulta de sesión, logout y administración de usuarios, roles y permisos a estos endpoints. Para desarrollo, iniciar ambos servidores y abrir `http://localhost:4200`; la API se usa en `http://localhost:8000/api/v1`.

Las pruebas de migraciones incluyen ejecución opcional contra MySQL: configurar `PELIFOLK_TEST_MYSQL_URL` con una conexión de pruebas cuyo usuario pueda crear y eliminar bases temporales y ejecutar `python -m pytest tests/test_migrations.py -q`. Cada prueba usa una base nueva con nombre aleatorio; no usar credenciales de producción. Las pruebas HTTP con SQLite desactivan explícitamente las migraciones de arranque.

Referencias técnicas: [JWT en FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [SQLAlchemy engines](https://docs.sqlalchemy.org/en/20/core/engines.html), [arranque con lifespan](https://fastapi.tiangolo.com/advanced/events/) y [commits implícitos de DDL en MySQL](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html).

## Animales

La migración `0003_animal_permissions` agrega `animals:read` y `animals:write` al dueño y al administrador. Se aplica automáticamente al arrancar la API; los otros roles se habilitan desde Roles y permisos. Volver a iniciar sesión actualiza los permisos que muestra el frontend.

- `GET /api/v1/animals?q=Luna&sex=female&offset=0&limit=25`: búsqueda literal por nombre/SINIIGA y paginación con `{items,total,offset,limit}`. `sex` es opcional; `exclude_id` permite omitir el animal en los selectores de padres.
- `GET /api/v1/animals/{id}`: ficha con razas y datos de madre/padre.
- `POST /api/v1/animals`: registro.
- `PUT /api/v1/animals/{id}`: reemplaza los datos editables completos.
- `GET /api/v1/breeds`, `POST /api/v1/breeds` y `PUT /api/v1/breeds/{id}` y `DELETE /api/v1/breeds/{id}`: catálogo, alta, edición y eliminación de razas. Las razas asignadas a animales no se eliminan (409). Renombrar conserva el ID y las asignaciones a animales; requiere `animals:write` y genera auditoría.

```json
{"name":"Luna","siniiga":"MX123","sex":"female","birth_date":"2024-02-01","origin":"born_in_herd","mother_id":null,"father_id":null,"is_breeder":false,"breeds":[]}
```

Nombre o SINIIGA es obligatorio. Fechas, parentesco y razas pueden quedar pendientes; si se indican razas, deben ser únicas y sus porcentajes sumar exactamente 100, con hasta dos decimales. La API valida sexos, fechas y ciclos genealógicos, incluyendo cambios en padres con crías existentes. Altas y ediciones generan auditoría en la misma transacción. Este módulo aún no registra eventos sanitarios, salidas, lotes ni movimientos.

## Ubicaciones y lotes

La migración `0004_organization` concede `locations:read`, `locations:write`, `groups:read` y `groups:write` al dueño/administrador y agrega tipos iniciales (`corral`, `pasture`, `barn`, `other`). Se ejecuta al arrancar la API. Los permisos pueden delegarse desde Roles y permisos.

- `GET/POST /api/v1/location-types`: catálogo y alta de tipos.
- `GET/POST /api/v1/locations`, `PUT /api/v1/locations/{id}`: listar, crear y editar ubicaciones.
- `GET/POST /api/v1/groups`, `GET/PUT /api/v1/groups/{id}`: lotes con conteo de animales actuales.
- `GET /api/v1/groups/{id}/memberships?current=true&offset=0&limit=25`: animales actuales; `current=false` muestra todo el historial.
- `GET /api/v1/groups/animal-options?q=Luna&limit=50`: búsqueda de animales con su lote actual, para usuarios con `groups:write`.
- `POST /api/v1/groups/{id}/assignments`: `{ "animal_ids": ["uuid"], "effective_date": "2024-02-01", "move_existing": false }`. Hasta 100 animales únicos. `move_existing=true` traslada los que están en otros lotes.
- `POST /api/v1/groups/{id}/animals/{animal_id}/remove`: `{ "effective_date": "2024-03-01" }`. Cierra el periodo sin borrar historial.

Los intervalos incluyen ambos extremos: un cambio efectivo el 1 de febrero cierra el lote anterior el 31 de enero. La fecha debe ser posterior al ingreso actual, no futura y no anterior al nacimiento. Los periodos históricos no pueden solaparse. Cada operación valida el lote y bloquea los animales antes de escribir; los traslados masivos y su auditoría se confirman juntos. Un lote con animales asignados no se desactiva. Las ubicaciones son un catálogo: la ubicación actual del animal sigue derivándose de los eventos, que se implementarán en el módulo de manejo.

## Pesajes

La migración `0005_weights` agrega `weights:read` y `weights:write` al dueño y al administrador. Se aplica al reiniciar la API. Los permisos de los demás roles se asignan desde Roles y permisos.

- `GET /api/v1/weights?q=Luna&offset=0&limit=25`: pesajes del hato, más recientes primero.
- `GET /api/v1/weights/animal-options?q=Luna`: búsqueda de animales para registrar o consultar pesajes, independiente del permiso de animales.
- `POST /api/v1/weights`: `animal_id`, `date` (YYYY-MM-DD), `weight_kg` y `notes` opcional.
- `GET /api/v1/weights/animals/{id}/history`: mediciones en orden cronológico.

En Manejo, registrar un pesaje y usar Ver para consultar la gráfica y el historial. El peso debe ser positivo y tener hasta dos decimales. La fecha no puede ser futura ni anterior al nacimiento. Se permite una medición por animal y día; los registros conservan usuario, rol al registrar y auditoría en la misma transacción. La ganancia diaria divide el cambio de peso entre los días transcurridos; pérdidas se muestran con signo negativo. Editar el nacimiento tampoco puede dejar pesajes anteriores a esa fecha.

## Sanidad: observaciones y casos

La migración `0006_health` agrega `health:read` y `health:write` al dueño y al administrador. Los demás roles reciben acceso desde Roles y permisos. Se reutilizan `events`, `event_observations` y `health_cases`; la migración `0007_audit_precision` agrega microsegundos a la auditoría para ordenar cambios realizados dentro del mismo segundo.

- `GET /api/v1/health/animal-options?q=Luna`: búsqueda de animales sin depender del permiso de animales.
- `GET /api/v1/health/observations?q=Luna&offset=0&limit=25`: observaciones paginadas.
- `POST /api/v1/health/observations`: `animal_id`, `date` (YYYY-MM-DD), `observation`.
- `GET /api/v1/health/cases?q=Luna&status=open&offset=0&limit=25`: casos; `status` opcional admite `open`, `under_treatment`, `closed`.
- `POST /api/v1/health/cases`: `animal_id`, `start_date`, `reason` y `notes` opcional; se crea abierto.
- `GET /api/v1/health/cases/{id}`: detalle y actividad del caso.
- `PATCH /api/v1/health/cases/{id}/status`: `expected_status`, `status`, `closed_date` obligatoria al cerrar y nula en otros estados. Si otro usuario cambió el estado, devuelve 409 y requiere recargar el caso.
- `GET /api/v1/health/animals/{id}/history`: observaciones y casos del animal.

En Sanidad, usar Observación o Abrir caso. El icono de portapapeles abre el caso y permite cambiar su estado; el reloj abre el historial sanitario del animal. Cerrar exige una fecha entre el inicio y hoy. Reabrir elimina la fecha de cierre actual y conserva el cierre anterior en la actividad. No se aceptan registros futuros ni anteriores al nacimiento, y editar el nacimiento tampoco puede invalidar los registros existentes. Cada registro o cambio de estado se audita en la misma transacción. El flujo incluye diagnósticos y tratamientos dentro de cada caso.

### Diagnósticos

Desde el detalle de un caso abierto o en tratamiento, usar **Agregar diagnóstico**: fecha, descripción y gravedad (`mild`, `moderate`, `severe`, `critical`; etiquetas en español). `POST /api/v1/health/cases/{id}/diagnoses` requiere `health:write`; el animal se obtiene del caso, sin aceptar uno distinto en el formulario. Se guarda en `events` y `event_diagnoses`, con usuario, rol al registrar y auditoría en la misma transacción. No requiere nuevas migraciones ni permisos.

El detalle del caso y el historial sanitario del animal incluyen `diagnoses`, con fecha, gravedad, descripción y quién lo registró. No se aceptan fechas futuras o anteriores al inicio del caso. Un caso cerrado debe reabrirse antes de registrar diagnósticos. El cierre no puede ser anterior a un diagnóstico existente. Registrar un diagnóstico conserva el estado actual del caso; el cambio a En tratamiento se realiza desde Cambiar estado.


### Productos y tratamientos

La migración `0008_treatment_catalogs` agrega unidades, tipos de producto y vías de administración iniciales sin reemplazar los catálogos existentes. Reiniciar la API aplica esta migración. Se usan los permisos `health:read` y `health:write` existentes.

En **Sanidad → Productos**, crear y editar productos: nombre, tipo, unidad, retiro en días y actividad. Desactivar conserva el historial y bloquea nuevos tratamientos. En el detalle de un caso abierto o en tratamiento, usar **Agregar tratamiento**: producto activo, fecha de inicio, dosis positiva con hasta tres decimales, unidad de dosis, vía, frecuencia opcional en horas y duración entera de 1 a 3650 días. El primer tratamiento pasa el caso a En tratamiento y audita el cambio en la misma transacción. Un caso cerrado se reabre antes de registrar tratamientos.

- `GET /api/v1/health/catalogs`: tipos, unidades y vías.
- `GET /api/v1/health/products?q=&active=true&offset=0&limit=25`: catálogo paginado; omitir `active` incluye todos.
- `POST /api/v1/health/products` y `PUT /api/v1/health/products/{id}`: registrar o editar productos.
- `POST /api/v1/health/cases/{id}/treatments`: `product_id`, `start_date`, `dose_value`, `dose_unit_id`, `route_id`, `frequency_hours` opcional y `duration_days`.

El animal se obtiene del caso. Los tratamientos quedan en `events` y `event_treatments`, con usuario, rol al registrar y auditoría. El detalle del caso y el historial por animal incluyen `treatments`. La columna generada existente `end_date` es el límite exclusivo (inicio + duración); `last_day` representa el último día incluido y se muestra en la interfaz. Un tratamiento de un día tiene el mismo día de inicio y último día. No se acepta un inicio futuro o anterior al caso, ni un cierre anterior al último día del tratamiento. Los datos del producto en consultas provienen del catálogo actual; la auditoría conserva sus cambios.

### Programas sanitarios y avisos

En **Sanidad → Programas y avisos**, crear o editar programas con producto, intervalo, edad mínima, sexo, anticipación del aviso y actividad. Se reutilizan `health_programs` y `event_treatments.program_id`; no requiere nuevas migraciones ni permisos. Un programa con aplicaciones conserva su producto; desactivar mantiene el historial y bloquea aplicaciones nuevas.

- `GET /api/v1/health/programs?q=&active=true&offset=0&limit=25`: programas paginados.
- `POST /api/v1/health/programs` y `PUT /api/v1/health/programs/{id}`: nombre, `product_id`, `interval_days`, `minimum_age_days`, `sex` (`male`, `female` o null), `notice_days` y `active`.
- `GET /api/v1/health/programs/{id}/schedule?q=&state=attention&offset=0&limit=25`: avisos por animal; `state` admite `attention`, `all`, `overdue`, `due`, `upcoming`, `scheduled`, `missing_birth_date`.
- `POST /api/v1/health/programs/{id}/applications`: `animal_id`, `start_date`, dosis, unidad, vía, frecuencia opcional y duración. El producto se obtiene del programa.

La primera fecha es nacimiento + edad mínima. Las siguientes son la última aplicación de ese programa + intervalo, respetando la edad mínima configurada. No se descuentan aplicaciones realizadas fuera del programa. Vencidas, para hoy, próximas dentro del aviso y nacimiento faltante aparecen en Avisos pendientes; elegir Todos muestra las programadas más adelante. Se excluyen animales con salida efectiva registrada y se aplica el filtro de sexo. Sin nacimiento y sin aplicaciones previas no se inventa una fecha. Si la edad mínima es cero, se permite registrar una primera aplicación sin nacimiento; cuando es mayor que cero, debe conocerse y cumplirse la edad en la fecha registrada.

Las aplicaciones quedan como tratamientos con `program_id`, sin exigir abrir un caso sanitario, y aparecen en el historial del animal y en el reloj del aviso. Se conserva usuario, rol y auditoría en la misma transacción. Se valida producto/programa activos, sexo, edad, fecha y permanencia en el hato. La fecha debe ser posterior a la última aplicación del mismo programa; una aplicación temprana válida reinicia el intervalo desde su inicio. Los avisos se calculan al consultar la pantalla, dentro del sistema. Editar intervalo, edad o sexo recalcula los avisos usando la configuración actual, sin cambiar los registros históricos.

## Reproducción

La migración `0009_breeding` agrega `breeding:read` y `breeding:write` al dueño y al administrador, además de los tipos de parto. Se aplica al reiniciar la API. Volver a iniciar sesión actualiza los permisos del menú; los demás roles se configuran desde Roles y permisos.

En **Reproducción**, las pestañas Montas, Gestación y Partos y crías permiten registrar y consultar eventos. El reloj abre el historial reproductivo de la hembra. Una monta requiere hembra, macho y fecha. Un diagnóstico admite `pregnant`, `not_pregnant` o `uncertain`, y puede vincularse a una monta de esa misma hembra.

- `GET /api/v1/breeding/events?kind=mating&q=&offset=0&limit=25`: registros paginados; `kind` también admite `pregnancy` y `birth`, y `animal_id` filtra por hembra.
- `GET /api/v1/breeding/animal-options?q=&sex=female`: hasta 100 animales activos por sexo.
- `GET /api/v1/breeding/birth-types`: natural, asistido, cesárea y otro.
- `POST /api/v1/breeding/matings`: `animal_id`, `male_id`, `date` y `notes` opcional.
- `POST /api/v1/breeding/pregnancy-diagnoses`: `animal_id`, `date`, `result`, `mating_event_id` y `notes` opcionales.
- `POST /api/v1/breeding/births`: `animal_id` de la madre, `date`, `birth_type_id`, `father_id` y `notes` opcionales, y `offspring` con 1 a 20 crías.
- `GET /api/v1/breeding/animals/{id}/history`: eventos de la hembra, montas del macho o nacimiento de la cría.

Cada cría requiere nombre o SINIIGA y sexo; admite peso al nacer y `alive` (por defecto verdadero). El parto crea los animales con nacimiento, origen y padres; el padre se elige explícitamente o queda desconocido. Una cría sin vida conserva su registro y una salida por muerte. Los pesos de nacimiento se guardan en el detalle del parto. Las razas y los lotes se asignan después desde sus módulos.

Se rechazan fechas futuras, anteriores o iguales al nacimiento de los padres, animales con salida efectiva, montas de otra hembra, diagnósticos anteriores a la monta y partos duplicados para la misma madre y día. El parto, todas sus crías, las salidas y la auditoría se confirman juntos. Editar animales no permite invalidar su historial reproductivo ni cambiar nacimiento o parentesco vinculados a un parto.

## Salidas del hato

La migración `0010_exits` agrega `exits:read` y `exits:write` al dueño y al administrador sin modificar tablas ni migraciones anteriores. Se aplica al iniciar la API. Volver a iniciar sesión actualiza el menú; los demás roles reciben acceso desde Roles y permisos.

En **Salidas → Registrar salida**, elegir animal, tipo (venta, muerte, sacrificio, traspaso, robo u otro), fecha y motivo/destino. Se conserva el animal y su historial. **Animales** muestra activos por defecto; elegir Bajas o Todos y pulsar Buscar permite consultar los animales que salieron, con tipo y fecha en su ficha. Las crías sin vida registradas desde un parto también aparecen entre las salidas.

- `GET /api/v1/exits?q=&exit_type=sale&offset=0&limit=25`: salidas paginadas, con tipo opcional (`sale`, `death`, `slaughter`, `transfer`, `theft`, `other`).
- `GET /api/v1/exits/animal-options?q=`: hasta 100 animales sin salida registrada.
- `POST /api/v1/exits`: `animal_id`, `exit_type`, `date` (YYYY-MM-DD) y `reason` obligatorio.
- `GET /api/v1/exits/animals/{id}/history`: historial de salidas del animal, con usuario y motivo.
- `GET /api/v1/animals?active=true`: activos; `active=false` devuelve bajas y omitir el filtro incluye todos. Las respuestas incluyen `status` y `exit_date`, derivados de eventos efectivos.

No se permiten salidas duplicadas, futuras, anteriores al nacimiento o que contradigan registros posteriores: eventos, montas del macho, casos sanitarios, tratamientos y pertenencia a lotes. La pertenencia abierta al lote se cierra incluyendo la fecha de salida, pero el animal deja de contar entre los miembros actuales. El evento, cierre y auditoría se confirman en una sola transacción. Se conserva el rol al registrar.

Las nuevas asignaciones a lotes requieren animales sin salida. Pesajes y registros sanitarios no pueden quedar después de la salida; se permiten registros históricos compatibles. Los tratamientos deben terminar dentro de la permanencia en el hato. Los programas sanitarios y reproducción también validan las salidas. Los casos sanitarios existentes conservan su estado e historial. Los padres históricos siguen disponibles al editar genealogía. Registrar una venta no crea todavía un ingreso económico.

## Economía

La migración `0011_finance` agrega `finance:read` y `finance:write` al dueño y al administrador y categorías iniciales de gastos e ingresos. Usa las tablas `expenses`, `incomes`, `suppliers`, `expense_categories` e `income_categories` existentes; no modifica migraciones aplicadas. Reiniciar la API aplica la migración y volver a iniciar sesión actualiza el menú. Los demás roles se configuran desde Roles y permisos.

En **Economía**, las pestañas Gastos e Ingresos permiten registrar, consultar y editar movimientos. Cada registro tiene categoría, importe en MXN, fecha y descripción opcional. Un gasto puede incluir proveedor; un ingreso puede vincularse a una salida por venta de animal. El balance muestra ingresos menos gastos de todo el rango de fechas aplicado, sin limitarlo a la página, búsqueda o categoría de la lista. Los filtros Desde y Hasta incluyen ambos extremos; omitirlos consulta todo el historial.

En **Proveedores**, crear o editar nombre y contacto y activar o desactivar. Desactivar conserva el historial y bloquea nuevas asignaciones; editar un gasto existente puede conservar su proveedor inactivo. En **Categorías**, administrar categorías de gastos e ingresos por separado, con eliminación solo si no hay movimientos asociados. Las categorías iniciales se guardan en inglés y se muestran traducidas; las categorías creadas por el usuario conservan su nombre.

- `GET /api/v1/finance/summary?date_from=&date_to=`: ingresos, gastos, balance y número de movimientos. Omitir parámetros de fecha vacíos.
- `GET /api/v1/finance/expenses` y `GET /api/v1/finance/incomes`: filtros opcionales `q`, `category_id`, `date_from`, `date_to`, paginación `offset=0&limit=25` (máximo 100).
- `POST /api/v1/finance/expenses` y `PUT /api/v1/finance/expenses/{id}`: `category_id`, `amount`, `date`, `description` y `supplier_id` opcionales.
- `POST /api/v1/finance/incomes` y `PUT /api/v1/finance/incomes/{id}`: `category_id`, `amount`, `date`, `description` y `exit_event_id` opcionales.
- `GET /api/v1/finance/sale-options?q=&income_id=`: hasta 100 ventas sin ingreso; al editar, `income_id` permite conservar su venta actual.
- `GET /api/v1/finance/suppliers?q=&active=true&offset=0&limit=25`, `POST /api/v1/finance/suppliers` y `PUT /api/v1/finance/suppliers/{id}`: proveedores con nombre, teléfono, correo, dirección y actividad.
- `GET /api/v1/finance/categories/{kind}`, `POST`, `PUT /{id}` y `DELETE /{id}`: `kind` admite `expense` o `income`; el cuerpo de creación/edición incluye `name`.

Los importes usan `Decimal` y `DECIMAL(12,2)`: se rechazan más de dos decimales, valores no finitos y fechas futuras. Los gastos deben ser positivos; los ingresos admiten cero según el esquema existente. Una venta solo puede tener un ingreso y este no puede ser anterior a su salida; muertes y otras salidas no se aceptan como ventas. Registrar una salida por venta conserva la separación entre el movimiento del hato y el cobro: el ingreso se registra después, con su importe y fecha. Los cambios económicos y de catálogos se auditan en la misma transacción. La consulta de Economía no requiere permisos de animales ni de salidas. El balance corresponde a movimientos registrados; aún no distribuye costos por animal o lote.

## Alimentación

La migración `0012_feeding` agrega los permisos `feeding:read` y `feeding:write` al dueño y administrador y unidades kg, lb, paca y saco. Se aplica al iniciar la API; volver a iniciar sesión actualiza el menú. Reutiliza `feeds`, `feed_prices` y `feedings` sin modificar migraciones anteriores.

En **Alimentación → Alimentos y precios**, agregar un alimento con su unidad, precio inicial en MXN y fecha de vigencia en la misma ventana. El alimento y su precio se guardan juntos; los cambios posteriores se agregan desde Precios. Se admiten precios futuros; cada fecha tiene un único precio. La unidad no puede cambiar después de registrar precios o consumos. Los precios se agregan al historial, sin editar ni borrar los anteriores.

En **Consumos → Registrar consumo**, elegir alimento, animal o lote, fecha y cantidad. El costo usa el último precio vigente en esa fecha, con redondeo a centavos. El lote debe tener miembros en esa fecha; la cantidad corresponde al lote completo. No se admiten fechas futuras, consumos individuales anteriores al nacimiento ni posteriores a la salida. Un precio retroactivo recalcula los costos derivados del período correspondiente. No se crea automáticamente un gasto en Economía.

El historial permite buscar, filtrar fechas y consultar un animal o lote desde cada fila. El costo total incluye todos los registros filtrados, no solo la página visible. Los registros antiguos sin precio muestran costo desconocido y no se incluyen como cero en el total.

- `GET /api/v1/feeding/units`: unidades disponibles.
- `GET/POST /api/v1/feeding/feeds` y `PUT /api/v1/feeding/feeds/{id}`: catálogo, con `name` y `unit_id`.
- `GET/POST /api/v1/feeding/feeds/{id}/prices`: precios; creación con `effective_from` y `unit_cost` (hasta cuatro decimales).
- `GET /api/v1/feeding/target-options?kind=animal&q=`: destinos; también admite `kind=group`.
- `GET /api/v1/feeding/consumptions`: filtros `q`, `animal_id`, `group_id`, `date_from`, `date_to`, `offset` y `limit`.
- `POST /api/v1/feeding/consumptions`: `feed_id`, `date`, `quantity` (hasta dos decimales) y exactamente uno de `animal_id` o `group_id`.

## Resumen del rancho

`GET /api/v1/dashboard/summary` requiere iniciar sesión y devuelve únicamente las áreas autorizadas por los permisos de lectura existentes; las demás son `null`. No requiere una migración nueva. **Resumen** permite actualizar las cifras y abrir los módulos correspondientes.

El hato muestra animales activos, hembras, machos y bajas. Sanidad conserva los casos abiertos o en tratamiento y muestra hasta cinco avisos prioritarios de programas activos con productos activos; el total cuenta combinaciones de animal y programa, incluyendo fechas pendientes y falta de fecha de nacimiento. Reproducción cuenta hembras activas cuyo último diagnóstico o parto efectivo corresponde a un diagnóstico gestante; un parto posterior o un nuevo diagnóstico vacío deja de contarlas. No se estiman fechas de parto.

Economía y alimentación usan desde el primer día del mes actual hasta hoy. El balance usa movimientos económicos registrados; el costo alimenticio se muestra por separado y no se vuelve a restar del balance. Los consumos sin precio se señalan y se excluyen del costo conocido. La actividad lista los últimos ocho eventos efectivos por fecha, solo de los módulos autorizados, con enlaces a esos módulos. Las cifras sanitarias y del hato no se restringen al mes. Las fechas siguen el criterio de fecha actual de la API, usado por los demás módulos.

## Reporte de animales

**Reportes** requiere `animals:read`, igual que el catálogo de animales. Incluye búsqueda por nombre/SINIIGA, estado (activos por defecto, bajas o todos), sexo, raza y lote actual. Una cruza aparece al filtrar cualquiera de sus razas. El filtro por lote considera la pertenencia vigente hoy y excluye animales con salida; no consulta pertenencias históricas. La tabla muestra identificación, nacimiento, edad en meses completos (presentada como años y meses), razas con porcentajes, lote y tipo/fecha de salida. Los totales por sexo corresponden a todos los resultados filtrados, no solo a la página.

- `GET /api/v1/reports/animals/options`: razas y lotes para los filtros.
- `GET /api/v1/reports/animals?q=&status=active&sex=&breed_id=&group_id=&offset=0&limit=25`: reporte paginado (máximo 100); omitir filtros vacíos.
- `GET /api/v1/reports/animals/export`: mismos filtros, devuelve `.xlsx` con todos los resultados, fecha de consulta, filtros y total; no recibe paginación.

**Aplicar filtros** actualiza la consulta y **Descargar Excel** usa esos filtros aplicados, aunque haya cambios pendientes en el formulario. El archivo contiene fechas y edades como valores nativos de Excel, encabezados y autofiltro; los nombres e identificadores se guardan como texto. Las edades sin nacimiento quedan desconocidas. No requiere migración. Instalar las dependencias con `python -m pip install -r requirements.txt` incluye `openpyxl`, usado para generar el archivo.

## Reporte de sanidad

En **Reportes → Sanidad**, consultar **Casos** o **Programas** y descargar cada vista en Excel. El menú Reportes aparece con `animals:read` o `health:read`; cada pestaña y sus endpoints exigen el permiso de su módulo. Los usuarios con solo `health:read` abren Sanidad directamente. No requiere migración ni permisos nuevos.

- `GET /api/v1/reports/health/options?animal_q=`: hasta 100 animales por búsqueda (incluye bajas para consultar sus casos históricos) y programas activos con productos activos.
- `GET /api/v1/reports/health?kind=cases&status=all&q=&animal_id=&date_from=&date_to=&offset=0&limit=25`: casos con estado `open`, `under_treatment`, `closed` o `all`. Las fechas filtran **inicio del caso**, con extremos inclusivos; búsqueda por animal, SINIIGA o motivo.
- `GET /api/v1/reports/health?kind=schedule&status=attention&program_id=`: avisos derivados de los programas activos para animales que permanecen en el hato. Estados `overdue`, `due`, `upcoming`, `scheduled`, `missing_birth_date`, `attention` o `all`; búsqueda por animal/SINIIGA, filtro por animal, programa y fechas de **próxima aplicación**. Un rango de fechas excluye avisos sin fecha. `attention` incluye todos salvo `scheduled`; los avisos son combinaciones de animal y programa, no tratamientos clínicos pendientes.
- `GET /api/v1/reports/health/export`: los mismos filtros, sin paginación; devuelve `.xlsx` con fecha, filtros, total, encabezados y autofiltro. Casos incluye motivo, estado, inicio, cierre y observaciones. Programas incluye producto, última/próxima aplicación y días restantes.

Los totales por estado corresponden a todos los resultados filtrados. Cambiar entre Casos y Programas limpia los filtros incompatibles. **Aplicar filtros** confirma la consulta y el Excel usa los filtros aplicados. La búsqueda de opciones conserva el animal seleccionado aunque no coincida con la nueva búsqueda. Los textos se guardan como celdas de texto, sin interpretar fórmulas. La fecha actual sigue el criterio de los demás módulos de la API.

## Reporte de reproducción

En **Reportes → Reproducción**, consultar **Montas**, **Diagnósticos de gestación** y **Partos y crías**. Requiere `breeding:read`; los usuarios con solo ese permiso pueden abrir Reportes y ven únicamente Reproducción. Se reutilizan tablas y permisos existentes, sin migraciones nuevas.

- `GET /api/v1/reports/breeding/options?animal_q=`: hasta 100 animales por búsqueda, incluidos animales con salida para consultar registros históricos.
- `GET /api/v1/reports/breeding?kind=mating&q=&animal_id=&date_from=&date_to=&offset=0&limit=25`: `kind` admite `mating`, `pregnancy` y `birth`; fechas inclusivas por fecha del evento, paginación máxima 100. La búsqueda y el animal seleccionado incluyen la hembra, el macho de una monta o una cría vinculada al parto. Solo se muestran eventos efectivos, excluyendo los reemplazados.
- En `kind=pregnancy`, `result` opcional admite `pregnant`, `not_pregnant`, `uncertain`; los totales cuentan diagnósticos del período, no hembras gestantes actuales.
- En `kind=birth`, los totales de crías nacidas vivas/sin vida corresponden a todos los partos filtrados. **Ver crías** muestra identificación, sexo, condición al nacer y peso. Filtrar por una cría conserva el parto completo y todas sus crías. La condición al nacer no representa su estado actual.
- `GET /api/v1/reports/breeding/export`: mismos filtros, todos los resultados sin paginación. Exporta `.xlsx` con fecha, filtros, totales y datos propios de cada tipo de evento. El Excel de partos incluye una segunda hoja **Crías** con el ID del parto para relacionar ambas hojas y pesos numéricos.

**Aplicar filtros** confirma la consulta; la descarga usa los filtros aplicados. Cambiar de tipo de evento limpia los filtros incompatibles. Las fechas y pesos se guardan como valores nativos y los nombres, notas e identificadores como texto. El reporte conserva registros históricos después de una salida y no calcula fechas estimadas de parto.

## Reporte de economía

En **Reportes → Economía**, consultar **Gastos** e **Ingresos**, con permiso `finance:read`. Usuarios con solo ese permiso pueden abrir el reporte económico sin acceso a animales, sanidad o reproducción. No requiere migraciones nuevas.

La vista abre con el mes actual. Filtrar por fechas inclusivas, categoría, búsqueda y proveedor (solo gastos); los proveedores inactivos siguen disponibles para consultar movimientos históricos. Vaciar ambas fechas consulta todo el historial. Cambiar entre ingresos y gastos conserva fechas y búsqueda y limpia categoría y proveedor. **Aplicar filtros** confirma la consulta y la descarga usa esos filtros aplicados.

El **balance del período** usa todos los movimientos del rango de fechas, sin limitarlo a búsqueda, categoría, proveedor o página. El **importe filtrado** suma todos los resultados de la lista, no solo los visibles en la página. Alimentación no se resta automáticamente; el balance considera gastos registrados en Economía. El Excel distingue estos dos ámbitos.

- `GET /api/v1/reports/finance/options?supplier_q=`: categorías de ambos tipos y hasta 100 proveedores por búsqueda, activos o inactivos.
- `GET /api/v1/reports/finance?kind=expense&q=&category_id=&supplier_id=&date_from=&date_to=&offset=0&limit=25`: `kind` admite `expense` o `income`; omitir filtros vacíos. Devuelve lista, importe filtrado, conteo y balance del período. Máximo 100 por página.
- `GET /api/v1/reports/finance/export`: mismos filtros, todos los movimientos sin paginación; Excel con hoja **Resumen** (fechas, filtros, ingresos/gastos/balance e importe filtrado) y hoja **Gastos** o **Ingresos**. Incluye proveedor o identificación del animal de la venta vinculada, descripción y total.

Los importes de la API se serializan como decimales en cadenas y el Excel guarda importes y fechas como valores numéricos/nativos. Nombres, identificadores y descripciones se guardan como texto, sin interpretar fórmulas. Las categorías iniciales se traducen igual que en Economía; los nombres personalizados se conservan.

## Reporte de alimentación

En **Reportes → Alimentación**, consultar consumos por alimento, animal o lote con `feeding:read`. Abre con el mes actual; vaciar ambas fechas consulta todo el historial. Las fechas son inclusivas. Las opciones incluyen animales con salida y lotes inactivos para consultar consumos históricos. Cambiar de tipo de destino limpia la selección anterior. No requiere migración.

- `GET /api/v1/reports/feeding/options?feed_q=&target_q=&target_kind=animal`: hasta 100 alimentos y destinos por búsqueda. `target_kind` admite `animal` o `group`.
- `GET /api/v1/reports/feeding?q=&feed_id=&target_kind=all&target_id=&date_from=&date_to=&offset=0&limit=25`: búsqueda por alimento, animal/SINIIGA o lote; destino `all`, `animal` o `group`. Un `target_id` requiere tipo específico. Máximo 100 por página; omitir filtros vacíos.
- `GET /api/v1/reports/feeding/export`: mismos filtros sin paginación; Excel con hojas **Resumen** y **Consumos**, fechas nativas, cantidades/precios/costos numéricos y textos sin interpretar fórmulas.

El costo usa el precio vigente en la fecha de cada consumo y se redondea a centavos por registro. Los consumos sin precio se señalan y quedan fuera del **costo conocido**, aunque su cantidad sí se incluye. Las cantidades se suman por unidad, sin convertir kg, lb, sacos o pacas. Un consumo de lote pertenece al lote completo y no se distribuye por animal. Los totales corresponden a todos los resultados filtrados, no solo a la página. Agregar un precio retroactivo puede actualizar estos costos calculados; el reporte no registra gastos automáticamente en Economía.

**Aplicar filtros** confirma la consulta y **Descargar Excel** usa los filtros aplicados, aunque haya cambios pendientes en el formulario.

## Reporte de pesajes y crecimiento

En **Reportes → Pesajes y crecimiento**, consultar mediciones por animal, nombre/SINIIGA y fechas inclusivas. Requiere `weights:read`; usuarios con solo ese permiso también acceden a Reportes. Abre con todo el historial e incluye animales con salida. No requiere migración.

- `GET /api/v1/reports/weights/options?animal_q=`: hasta 100 animales por búsqueda, incluidos animales con salida.
- `GET /api/v1/reports/weights?q=&animal_id=&date_from=&date_to=&offset=0&limit=25`: reporte paginado (máximo 100), con peso, fecha/peso anterior, días, cambio de peso y ganancia diaria. Omitir filtros vacíos.
- `GET /api/v1/reports/weights/export`: mismos filtros, sin paginación; Excel con hojas **Resumen** y **Pesajes**. Guarda fechas nativas, pesos/cambios numéricos y nombres/notas como texto sin interpretar fórmulas.

Solo se consideran eventos efectivos, excluyendo reemplazados. El pesaje anterior se calcula por animal **antes** de filtrar fechas: puede quedar fuera del período consultado. Cambio = peso actual − anterior; ganancia diaria = cambio / días, redondeada a tres decimales en kg/día. El primer pesaje queda sin comparación y no representa ganancia cero. Si dos registros históricos son del mismo día, no se calcula ganancia diaria entre ellos. Los valores negativos representan pérdidas.

Los totales cuentan pesajes, animales distintos, intervalos comparables y pesajes con pérdida en todos los resultados filtrados, no solo en la página. No se suman cambios de peso entre animales. **Aplicar filtros** confirma la consulta y **Descargar Excel** usa los filtros aplicados.

## Genealogía visual

La vista **Genealogía** requiere `animals:read` y se abre desde el menú o desde **Animales → Genealogía**, en la fila o ficha de cada animal. Permite buscar por nombre/SINIIGA y elegir el animal. Las rutas del frontend son `/dashboard/genealogy` y `/dashboard/genealogy/:id`; compartir la segunda conserva el animal consultado.

- `GET /api/v1/animals/{animal_id}/genealogy?offset=0&limit=12`: árbol con el animal consultado, sus padres y abuelos (dos generaciones de antepasados), más hijos directos paginados. Máximo 100 hijos por página. Los totales de hijos, hembras y machos corresponden a todos los hijos registrados, no solo a la página.

Los vínculos se obtienen de `mother_id` y `father_id`, incluidos animales con salida. Los parentescos desconocidos quedan como **No registrado**; no se infieren desde montas. Un antepasado compartido permanece en ambas ramas, conservando su relación materna/paterna. La consulta tiene profundidad acotada y no modifica datos ni necesita migración. Las fechas y estados mostrados corresponden a la consulta actual.

**Ficha** abre los datos del familiar (identificación, sexo, nacimiento, estado, origen, reproducción, padres y razas) en la modal con el scroll existente. **Explorar familia** centra el árbol en ese familiar y permite avanzar hacia otras generaciones o recorrer descendientes. La lista inferior muestra hijos directos; no es un conteo de todos los descendientes ni un indicador de fertilidad o supervivencia. Esta vista no calcula consanguinidad ni evalúa el valor genético de los reproductores.

## Partos próximos

En **Reproducción → Partos próximos**, consultar hembras activas cuyo último evento efectivo entre diagnóstico de gestación y parto sea un diagnóstico `pregnant`. Requiere `breeding:read`; no necesita permiso de animales, migración ni registros nuevos. La vista conserva acceso al historial reproductivo. **Ir a registrar parto**, visible con `breeding:write`, abre la pestaña Partos y crías; allí se selecciona la hembra y se registra el parto real.

- `GET /api/v1/breeding/upcoming-births?q=&status=all&notice_days=14&offset=0&limit=25`: búsqueda por nombre/SINIIGA, aviso de 1 a 60 días, paginación máxima 100. Estados `all`, `past_estimate`, `due`, `upcoming`, `scheduled` y `missing_mating`. Totales y conteos corresponden a todos los resultados filtrados.

La fecha estimada usa **monta vinculada al diagnóstico + 147 días**, una referencia promedio para ovinos ([Merck Veterinary Manual](https://www.merckvetmanual.com/management-and-nutrition/preventative-health-care-and-husbandry-of-sheep/breeding-parturition-and-common-lamb-diseases-of-sheep)). No confirma la fecha real ni diagnostica un retraso. Fecha estimada pasada significa que la referencia quedó atrás y no hay un parto posterior registrado. Hoy se muestra por separado; próximas incluye los siguientes `notice_days`, y las demás quedan Más adelante.

No se estima desde la fecha de diagnóstico ni desde una monta sin vínculo explícito. Un diagnóstico sin monta vinculada, con monta reemplazada/inválida o anterior al último parto queda **Sin fecha estimada**, con el motivo visible. Se excluyen animales con salida y eventos reemplazados; un parto posterior o diagnóstico posterior de vacía/dudosa retira la hembra del listado. La misma ordenación que el resumen resuelve eventos del mismo día por fecha, creación e ID. Actualizar listado vuelve a calcular con los filtros aplicados y la fecha actual de la API; no envía notificaciones externas ni registra partos automáticamente.

## Desempeño de reproductores

En **Reproducción → Desempeño**, comparar hembras o machos con `breeding:read`, sin exigir permiso de animales. Incluye animales marcados como reproductores, con eventos efectivos de reproducción o con hijos directos registrados, aun si tienen cero resultados en el período. La vista abre con todo el historial, permite buscar por nombre/SINIIGA y filtrar estado actual y fechas. No requiere migración ni registros nuevos.

- `GET /api/v1/breeding/performance?sex=female&q=&status=all&date_from=&date_to=&offset=0&limit=25`: sexo `female` o `male`; estado `all`, `active` o `exited`; fechas inclusivas. Máximo 100 por página. Devuelve métricas por animal y totales sobre todos los resultados filtrados.
- `GET /api/v1/breeding/performance/{animal_id}/offspring?date_from=&date_to=&offset=0&limit=25`: hijos directos del período, condición/peso al nacer, estado actual y fecha de salida. Usa las fechas aplicadas a la comparación, no cambios pendientes. **Ver genealogía** aparece solo con `animals:read`.

Montas y partos se filtran por fecha del evento; descendientes por nacimiento. Sin rango se incluyen descendientes sin fecha, pero un rango los excluye. Los padres se obtienen de las fichas; las crías creadas manualmente también cuentan como descendientes. La condición y peso al nacer solo se obtienen de un parto efectivo vinculado; los datos desconocidos quedan explícitos y no se convierten en cero.

En hembras, **partos registrados** cuenta eventos efectivos y **crías por parto registrado** divide las crías de esos partos entre su número. No usa las crías capturadas fuera de partos en esa razón. En machos, **partos con descendencia** cuenta partos efectivos con crías que tienen ese padre; no demuestra fecundidad ni atribuye un padre a partir de una monta. Montas son registros de monta, no concepciones confirmadas.

El peso promedio al nacimiento considera únicamente las crías con peso registrado (incluye nacidas sin vida) y muestra cuántas contribuyen al promedio. **Nacidos vivos**, **nacidos sin vida** y **condición desconocida** son resultados al nacimiento. **Muertes posteriores registradas** cuenta muerte/sacrificio actual de crías que nacieron vivas; el estado de las crías se consulta a la fecha actual, incluso si la salida ocurrió fuera del rango de nacimientos. Ventas, traspasos y otras salidas quedan separados: no prueban supervivencia. No se calcula una tasa de supervivencia/fertilidad ni una puntuación genética. Los descendientes son hijos directos, no todas las generaciones.

## Asignación de gastos y costos por animal o lote

En **Economía → Gastos**, usar **Asignar** o **Asignado** para consultar o repartir un gasto existente entre animales, lotes o casos sanitarios. Consultar requiere `finance:read`; guardar requiere `finance:write`. Un reparto no vacío debe sumar exactamente 100 %, sin repetir destinos; cada porcentaje admite hasta dos decimales. Quitar todos los destinos y guardar deja el gasto como general del rancho. La operación se confirma de forma atómica y conserva la asignación anterior si falla. Genera auditoría con el usuario y los valores anteriores/nuevos. Se reutiliza `expense_allocations` de la migración inicial, sin modificar migraciones aplicadas ni crear otra.

- `GET /api/v1/finance/allocation-options?kind=animal&q=`: hasta 100 destinos por búsqueda. `kind` admite `animal`, `group`, `health_case`; incluye animales con salida, lotes inactivos y casos cerrados para asignaciones históricas. Casos se identifican por fecha y animal, sin exponer el detalle clínico.
- `GET /api/v1/finance/expenses/{expense_id}/allocations`: gasto, destinos, porcentajes, importes asignados y saldo sin asignar.
- `PUT /api/v1/finance/expenses/{expense_id}/allocations`: `{"allocations":[{"kind":"animal","target_id":"UUID","percentage":"100.00"}]}`. Reemplaza el reparto; `{"allocations":[]}` lo limpia. Máximo 100 destinos.
- `GET /api/v1/finance/costs?kind=animal&target_id=UUID&date_from=&date_to=&offset=0&limit=25`: `kind` admite `animal` o `group`. Fechas inclusivas; omitir fechas vacías. Lista asignaciones paginadas (máximo 100), total asignado a ese destino y alimentación separada. El costo de alimentación solo se devuelve si el usuario también tiene `feeding:read`.

El reparto distribuye centavos por mayores residuos, con desempate estable por destino, para que los importes asignados sumen exactamente el gasto cuando los porcentajes suman 100 %. Se calcula desde el monto actual del gasto: editar su importe actualiza automáticamente los importes derivados, conservando porcentajes. La asignación no crea ni duplica movimientos ni cambia el balance de Economía. La lista de gastos incluye `allocation_count` para distinguir Asignar/Asignado.

En **Economía → Costos por animal o lote**, seleccionar un destino y consultar su período. Para un animal se suman asignaciones directas y las de sus casos sanitarios. Para un lote se suman solo sus propias asignaciones; no se distribuyen automáticamente a los miembros ni se suman las asignaciones individuales. Los gastos generales no atribuidos quedan fuera. Cada fila es una asignación: un mismo gasto puede aportar varias al animal, sin contar nuevamente su importe completo.

Los consumos de alimentación se valoran con el precio vigente en su fecha y se presentan aparte de los gastos asignados. No se suman ambos importes: una compra de alimento registrada en Economía puede corresponder a esos mismos consumos. Los consumos sin precio conservan costo desconocido; se informa su conteo y se excluyen del costo conocido. El consumo del lote completo no se reparte entre animales. La vista muestra costos registrados/atribuidos; no calcula rentabilidad ni un costo total que incluya gastos generales no repartidos. **Ver asignación** permite inspeccionar o editar el reparto con los permisos correspondientes.

## Ubicación actual e historial de traslados

En **Ubicaciones → Animales y traslados**, consultar animales en el hato, con salida o todos, por nombre/SINIIGA y ubicación. Requiere `locations:read`, sin exigir permiso de animales. **Asignar ubicación** o **Trasladar** requiere `locations:write`; permite elegir un destino activo, fecha y motivo obligatorio. Conserva usuario, rol al registrar y auditoría. La ficha de Animales también muestra `current_location`.

- `GET /api/v1/locations/animal-positions?q=&status=active&location_id=&offset=0&limit=25`: estado `active`, `exited` o `all`, paginación máxima 100. Para bajas devuelve ubicación actual nula y última ubicación conocida.
- `GET /api/v1/locations/animals/{animal_id}/history?offset=0&limit=25`: registros vigentes con origen/destino derivados cronológicamente, fecha, motivo y responsable. La referencia anterior se conserva incluso al paginar.
- `POST /api/v1/locations/movements`: `animal_id`, `location_id`, `date` (YYYY-MM-DD), `reason` (1–2000 caracteres). Fecha no futura ni anterior al nacimiento, posterior al último registro de ubicación. Se admite un registro por animal/día; no inserta traslados retroactivos entre registros existentes, no repite el destino actual y no traslada animales con salida.

Se reutiliza `events.location_id`; la migración nueva **0013_location_movements** registra el tipo de evento 9 (`location_movement`). Se aplica al reiniciar la API con las migraciones de inicio activas. No modifica migraciones anteriores ni crea tablas nuevas. La ubicación se deriva del último evento efectivo con ubicación, incluidos registros previos de otros tipos; se ignoran reemplazados. Los registros de otros tipos se distinguen en el historial. La actividad del resumen incluye traslados solo con `locations:read`.

La ubicación física y el lote son independientes. Un traslado no cambia la pertenencia al lote. Una ubicación con animales actualmente asignados no se desactiva hasta trasladarlos o registrar sus salidas. Los animales con salida conservan el historial; su última ubicación no significa que permanezcan allí. Cambiar el nacimiento no puede invalidar registros anteriores de ubicación, y una salida no puede quedar antes de un traslado ya registrado.

### Retiro sanitario

`0014_treatment_withdrawal.sql` agrega un periodo histórico nullable a los tratamientos; se aplica automáticamente al arrancar la API. No modifica migraciones anteriores ni rellena el historial con el catálogo actual. Cada tratamiento nuevo, de caso o programa, guarda los días de retiro del producto bajo bloqueo del producto.

En **Sanidad → Retiro sanitario** se consultan los animales activos y sus tratamientos efectivos. Los días de retiro positivos se cuentan como días calendario completos posteriores al último día del tratamiento (`end_date` es exclusivo); la fecha estimada es `end_date + withdrawal_days`. Se toma la mayor fecha entre productos y se descartan eventos reemplazados. Un tratamiento en curso muestra una estimación basada en su duración registrada, no una confirmación de última dosis administrada. Cero días mantiene la fecha de fin del tratamiento; no significa autorización inmediata para consumo. Los registros antiguos sin periodo histórico y las fechas que exceden el calendario aparecen **por verificar**, aunque otro tratamiento tenga una fecha conocida.

`GET /api/v1/health/withdrawals` admite búsqueda y paginación (permiso `health:read`); `GET /api/v1/health/animals/{id}/withdrawal` incluye el detalle. `GET /api/v1/exits/animals/{id}/withdrawal?date=YYYY-MM-DD` requiere `exits:read` y entrega solamente el resumen a la fecha de salida. El formulario de venta/sacrificio consulta ese resumen antes de guardar y avisa sobre retiros pendientes o datos por verificar. El backend calcula nuevamente el estado y lo conserva en la auditoría de la salida; el aviso no prohíbe registrar una venta. Permanecen las validaciones de fechas contra el historial.

La estimación no certifica aptitud para consumo. El retiro depende de la etiqueta y del tratamiento indicado por el veterinario; su referencia es la última administración, que debe mantenerse actualizada en los registros. Referencia sobre registro de tratamientos y retiro: [FDA, Adequate Records Help Prevent Illegal Drug Residues](https://www.fda.gov/animal-veterinary/animal-health-literacy/adequate-records-help-prevent-illegal-drug-residues-and-ensure-food-safety).

### Consulta de auditoría

**Auditoría** en el menú muestra los cambios ya guardados por la aplicación, con paginación de 25 registros, búsqueda y filtros por módulo, acción, usuario y fechas. El detalle compara los campos modificados en columnas **Antes / Después**, distingue valores nulos de campos que no existían y permite consultar el historial del registro sin mezclar identificadores iguales de tablas distintas. Los nombres de usuarios y referencias vinculadas se resuelven con el catálogo actual; los valores guardados en las instantáneas conservan su contenido histórico. También se incluyen acciones propias, usuarios inactivos y registros sin usuario (sistema).

La migración automática `0015_audit_permission.sql` concede `audit:read` al dueño y al administrador del sistema. Es un permiso global de lectura: permite consultar cambios de todos los módulos, incluidos usuarios y economía. Puede asignarse explícitamente a otros roles desde **Roles y permisos**, sujeto a las reglas existentes para conceder permisos. No existe permiso de escritura ni endpoints para modificar o borrar la auditoría. Después de aplicar la migración, iniciar sesión nuevamente actualiza los accesos del menú.

Endpoints: `GET /api/v1/audit`, `GET /api/v1/audit/users` (busca hasta 50 usuarios con registros, configurable hasta 100) y `GET /api/v1/audit/{id}`. Todos requieren `audit:read`; consultar usuarios del historial no requiere `users:read`. El listado admite `q`, `module`, `action`, `user_id` (UUID o `system`), `record_id`, `table`, `offset`, `limit`, `date_from` y `date_before`. Los filtros de fecha deben incluir zona horaria: el primero es inclusivo y el segundo exclusivo. El frontend convierte las fechas locales elegidas a límites UTC y muestra las horas en el horario local.

La API elimina claves de credenciales de los valores anteriores/nuevos, incluso dentro de objetos y listas de registros históricos; conserva solamente la marca `password_changed`, nunca contraseñas ni hashes. La lista no devuelve instantáneas completas. La pantalla refleja la auditoría existente, no añade captura de cambios hechos directamente por SQL ni convierte registros anteriores en un historial que no se guardó.

### Seguimiento sanitario y revisiones clínicas

La migración automática `0016_health_followups.sql` crea `health_case_followups` con autor, rol al registrar, fecha clínica, evolución, evaluación de los tratamientos del caso, notas y próxima revisión opcional. Los seguimientos se agregan al historial y no tienen endpoints de edición ni eliminación. Registrar recuperación no cierra automáticamente el caso: el cierre sigue siendo una decisión explícita y no puede quedar antes de un seguimiento existente.

En **Sanidad → Casos y observaciones → Ver caso → Registrar evolución** se registra cómo está el animal y qué se acordó. Los seguimientos también aparecen en el historial sanitario del animal y generan auditoría en la misma transacción. La evaluación del resultado requiere un tratamiento efectivo registrado en ese caso cuya fecha de inicio no sea posterior a la evaluación; no se deduce automáticamente eficacia ni se sugieren dosis.

**Sanidad → Revisiones clínicas** muestra casos sin cerrar de animales activos, con filtros por animal y revisiones vencidas/para hoy, próximas o todas las programadas. **Abrir caso** lleva directamente al caso para registrar la siguiente evaluación. La próxima revisión corresponde al seguimiento más reciente por fecha clínica y, en empates, fecha de creación e identificador. Agregar una nota atrasada conserva el historial sin reemplazar un plan clínico posterior. Dejar vacía la próxima revisión en el seguimiento más reciente retira el pendiente; cerrar el caso o registrar una salida lo excluye de la agenda, conservando los registros.

`POST /api/v1/health/cases/{id}/followups` requiere `health:write`; `GET /api/v1/health/reviews?q=&state=attention|upcoming|all&offset=&limit=` requiere `health:read`. Los detalles del caso y del animal incluyen `followups`. No se admiten seguimientos futuros, anteriores al inicio del caso, posteriores a una salida ni en casos cerrados. La próxima revisión no puede quedar antes del seguimiento, pero se permite registrar una revisión histórica ya vencida. Una salida no puede quedar antes de un seguimiento registrado. No cambian los permisos existentes ni se modifican migraciones anteriores.

### Decisiones por animal

La migración automática `0017_animal_decisions.sql` crea `animal_decisions`. En **Animales → Ficha → Decisiones e historial → Registrar decisión** se conserva la fecha de la decisión, tipo, motivo, usuario que la registra y rol al registrar. Tipos: conservar para reproducción, descartar para reproducción, separar del resto del hato, venta prevista, motivo de compra y otra decisión. El historial se consulta por tipo y páginas de 25 registros, ordenado por fecha clínica, creación e identificador. Para aclaraciones o cambios de criterio se añade una nueva decisión; no existen endpoints de edición o eliminación.

Las decisiones documentan el motivo y no ejecutan por sí mismas un cambio operativo: el estado de reproductor se actualiza en **Editar animal**, los traslados y pertenencias en **Ubicaciones / Lotes**, y las ventas o bajas en **Salidas**. La captura lo explica al usuario para distinguir el criterio registrado de la acción realizada. El historial también permanece accesible desde la ficha de un animal dado de baja; permite agregar motivos históricos con fecha no posterior a su salida.

`GET /api/v1/animals/{id}/decisions?kind=&offset=&limit=` requiere `animals:read`; `POST /api/v1/animals/{id}/decisions` requiere `animals:write`, con `date`, `kind` y `reason`. La API obtiene el autor y el rol de la sesión, registra auditoría en la misma transacción y valida que la fecha no sea futura, anterior al nacimiento ni posterior a una salida. Modificar el nacimiento o registrar una salida tampoco puede invalidar decisiones existentes. No se necesitan permisos nuevos ni se modifican migraciones anteriores.

### Aviso de parentesco en montas

La migración automática `0018_mating_kinship.sql` agrega `kinship_snapshot` nullable a `event_matings`. En **Reproducción → Montas → Registrar**, al seleccionar hembra y macho se compara la genealogía registrada hasta padres y abuelos. Se muestran relaciones directas con progenitores/abuelos, progenitores compartidos, abuelos compartidos y antepasados que son progenitores de uno y abuelos del otro. Un antepasado presente en distintas ramas conserva todos sus caminos; compartir un único progenitor conocido no se presenta automáticamente como hermanos de un solo progenitor cuando falta el otro.

El aviso distingue **parentesco registrado**, **sin parentesco encontrado hasta abuelos** y **datos genealógicos incompletos**. Los datos faltantes y las inconsistencias (ciclos o sexos incompatibles en las ramas) aparecen explícitamente; no se inventa una genealogía ni un coeficiente genético y no se descartan parentescos más lejanos. La consulta no requiere `animals:read`: usa `breeding:read`, como el resto de la captura reproductiva.

`GET /api/v1/breeding/kinship?animal_id=UUID&male_id=UUID` devuelve el aviso y sus antepasados/caminos. El frontend consulta al cambiar la pareja y espera una respuesta correcta antes de permitir guardar; muestra errores sin presentarlos como ausencia de parentesco. El parentesco encontrado es un aviso y no impide registrar una monta que efectivamente ocurrió. El backend calcula nuevamente la comprobación al guardar, bajo bloqueo de los animales consultados, y la conserva en la monta y en su auditoría. El cliente no puede enviar una comprobación inventada.

El detalle y el historial de la monta muestran la comprobación guardada, aunque luego cambien los padres o nombres de los antepasados. Las montas anteriores sin comprobación conservada muestran esa ausencia; no se reconstruye retrospectivamente un resultado. Se mantienen todas las validaciones existentes de sexos, nacimiento y permanencia en el hato, y no cambian los permisos ni migraciones anteriores.

### Opciones válidas al seleccionar padres

La edición de animales consulta `GET /api/v1/animals?parent_of=UUID&sex=female|male&q=&limit=100`. La API excluye al animal y a todos sus descendientes por cualquiera de las dos líneas parentales, incluso crías/nietos fuera de la primera página o con fechas de nacimiento desconocidas. Filtra antes de contar y paginar; un descendiente sigue disponible para animales que no sean sus ascendientes. El parámetro genérico `exclude_id` conserva su comportamiento anterior.

La respuesta incluye `excluded_parent_ids` para impedir que el selector vuelva a introducir una selección anterior que ya sea descendiente. Si la genealogía cambia mientras se edita, se limpia esa selección y se avisa. La validación existente al guardar sigue comprobando ciclos, sexos y fechas bajo bloqueo. Este ajuste no necesita migración ni modifica parentescos guardados.

El filtro de `parent_of` también excluye parejas reproductivas conocidas mediante montas efectivas (sin eventos reemplazados) o crías con ambos progenitores registrados. Se aplica en ambas direcciones: la hembra no se propone como madre del macho con el que se reprodujo, ni el macho como padre de esa hembra. La pareja sigue disponible para otros animales. Se conservan los padres que ya están guardados cuando existe una monta histórica entre familiares; este filtro ajusta opciones para asignaciones nuevas y no borra ni reescribe la genealogía. Las validaciones de ciclos, sexos y fechas al guardar permanecen vigentes.

### Registro de destete

La migración automática `0019_weanings.sql` crea `event_weanings`, vinculado al pesaje del destete y con un único registro por animal. En **Manejo → Destetes** se registra fecha, peso en kg y observaciones. Se conservan la madre y la fecha de nacimiento registradas al capturar el destete, además del autor y su rol. La edad se calcula solo con ese nacimiento guardado; si falta, aparece desconocida. Corregir después la madre o el nacimiento del animal no reescribe estos datos históricos.

El peso se integra en **Manejo → Pesajes**, en la curva de crecimiento y en los reportes de pesos existentes. Se marca como **Destete** en la lista y el historial de pesajes. Si existe un pesaje efectivo ese día con el mismo valor, se reutiliza sin modificar su autor ni sus notas; las notas y el autor del destete se guardan separadamente. Si el peso difiere, se pide consultar el historial y usar el valor registrado. **Consultar pesajes** en la captura conserva los campos al volver al formulario.

`GET /api/v1/weanings`, `GET /api/v1/weanings/animal-options` y `GET /api/v1/weanings/animals/{id}` requieren `weights:read`. El listado tiene búsqueda y paginación; las opciones muestran animales activos sin destete registrado. `POST /api/v1/weanings` requiere `weights:write` y recibe `animal_id`, `date`, `weight_kg` y `notes` opcionales. Se rechazan fechas futuras, fechas no posteriores al nacimiento conocido, registros posteriores a una salida y destetes duplicados. No se prescribe una edad de destete ni se inventan fechas o madres. La captura genera auditoría en la misma transacción. El destete es inmutable en esta versión; no tiene endpoints de edición o eliminación.

### Reporte de destetes

En **Reportes → Destetes** se consulta y exporta a Excel la fecha, animal/SINIIGA, madre al registrar, peso, edad al destete, autor y observaciones. Los filtros por nombre/SINIIGA, animal y fechas se aplican tanto al listado paginado como al Excel completo. Las fechas Desde/Hasta son inclusivas; sin fechas se consulta todo el historial, incluidos animales que posteriormente salieron del hato.

Endpoints `GET /api/v1/reports/weanings`, `/reports/weanings/options` y `/reports/weanings/export`, con permiso `weights:read`. Las opciones incluyen animales con destete registrado, aunque estén dados de baja. La edad utiliza el nacimiento guardado al registrar el destete; si falta, aparece desconocida y su celda en Excel permanece vacía. La madre corresponde al vínculo guardado en ese momento, con su identificación actual. Las notas y el autor corresponden al destete incluso cuando se reutilizó un pesaje previo. El Excel conserva fechas y números como tales y nombres/observaciones como texto, sin ejecutar fórmulas. No requiere migración ni permisos nuevos.

### Destetes en desempeño de reproductores

**Reproducción → Desempeño** incluye `weaned_offspring` (crías con destete efectivo registrado) y `average_weaning_weight_kg` (promedio observado, redondeado a dos decimales). **Ver crías** muestra `weaning`: fecha, peso y edad histórica al registrar; es `null` cuando no existe destete efectivo. No se utilizan pesajes ordinarios o posteriores para inferir el destete, ni se convierten edades desconocidas en cero. Los pesajes reemplazados quedan fuera del cálculo.

Se mantienen el permiso `breeding:read` y los filtros existentes: las fechas seleccionan descendientes por su nacimiento, y se consideran sus destetes efectivos hasta la consulta, aunque ocurran fuera del período o la cría haya salido del hato. Sin fechas también se incluyen descendientes sin nacimiento conocido. La agrupación usa la madre o el padre de la genealogía actual; los datos históricos del registro de destete no se reescriben. El promedio muestra su número de observaciones y no ajusta los pesos a una edad común. No requiere migración ni permisos nuevos.

### Historial integral del animal

En **Animales → Ver ficha → Historial completo → Ver historial**, consultar los registros ordenados del más reciente al más antiguo, con filtros por área y fechas y páginas de 25 registros. `GET /api/v1/animals/{id}/timeline` requiere `animals:read`; cada fuente se consulta y cuenta solo si el usuario tiene el permiso de lectura de su módulo. Filtrar expresamente un área no autorizada devuelve 403. Admite `module`, `date_from`, `date_to`, `offset` y `limit` (máximo 100), con fechas inclusivas. La consulta es de solo lectura y no requiere migración ni permisos nuevos.

Incluye fecha de nacimiento guardada actualmente, alta en el sistema, decisiones, observaciones, casos/cambios de estado, diagnósticos, tratamientos, seguimientos, pesajes/destete, montas (también para el macho), gestación, partos/descendencia paterna, traslados, inicio/fin de pertenencia a lotes, alimentación individual y del lote durante esa pertenencia, gastos atribuidos directamente o mediante casos e ingresos vinculados a ventas. La consulta permanece disponible después de la salida. No incluye gastos generales o del lote como si fueran atribuciones individuales.

La alimentación del lote indica su cantidad completa y no la atribuye al animal. Un gasto con varias atribuciones al mismo animal/casos se muestra una sola vez, indicando el porcentaje atribuible y el importe total del gasto; no se presenta ese importe completo como costo individual. Los eventos reemplazados se excluyen. El destete sustituye la etiqueta del pesaje asociado, usando las notas y autor del destete y su edad histórica, sin duplicar el evento. Una pauta de tratamiento se identifica como dosis indicada, sin afirmar aplicaciones de cada dosis.

Las fechas clínicas se conservan como fechas del evento. El alta y los cambios de estado usan la fecha del registro UTC de sus fuentes y se identifican explícitamente; no se inventa una fecha clínica para reabrir/cambiar un caso. Cuando la fuente no conserva autor y no existe auditoría inicial, no se inventa un responsable. Los nombres y relaciones de catálogos son los actuales; esta vista reúne evidencia disponible, no reconstruye instantáneas históricas ausentes.
