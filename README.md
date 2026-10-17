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

En **Sanidad → Retiro sanitario** se consultan los animales activos y las aplicaciones reales por tratamiento y producto. Se usa la última administración por instante UTC y los días de retiro guardados al registrar el tratamiento, aunque cambie el catálogo. La convención de la aplicación es mostrar el primer día calendario completo posterior al periodo: fecha local de la última dosis + días guardados + 1; también con cero días se muestra el día siguiente. La fecha local conserva el desplazamiento horario registrado. Esta convención de calendario es propia del sistema.

Sin aplicaciones, sin periodo histórico, con periodo inválido, variaciones de dosis o fechas fuera del calendario, el estado es **Por verificar**. La fecha calculada desde la pauta (`planned_release_date`) queda solo como referencia. Una pauta en curso mantiene el estado pendiente y no muestra fecha general; su estimación desde la última dosis es provisional. Las aplicaciones de pautas reemplazadas se conservan como exposición real y requieren revisión. Solo se descartan pautas reemplazadas sin aplicaciones.

El resumen toma la mayor fecha conocida entre productos y oculta la fecha general si existe algún dato por verificar o una pauta en curso. El detalle incluye `last_applied_at`, `application_count`, `estimated_release_date`, `planned_release_date`, `calculation_basis` y `review_reasons`. Las consultas a una fecha excluyen aplicaciones de días clínicos posteriores. Al guardar una salida, se recalcula bajo bloqueo para conservar el resultado actualizado en su auditoría. No cambia los permisos ni requiere una migración adicional a `0021_treatment_doses.sql`.

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

### Observaciones vinculadas a casos sanitarios

La migración nueva `0020_case_observations.sql` crea `health_case_observations` con observación, caso, usuario/rol que realiza el vínculo y fecha de creación. Se aplica al arrancar la API sin cambiar migraciones anteriores. Una observación de origen se vincula a un solo caso; un caso puede reunir varios hallazgos. El vínculo no modifica el texto, fecha, autor ni rol originales del evento de observación y no dispone de edición/eliminación desde la API.

En **Sanidad → Casos y observaciones → Observaciones → Atender hallazgo**, elegir **Abrir caso nuevo** o **Vincular a caso existente**. El animal queda determinado por la observación. Crear exige fecha y motivo del caso; la apertura y el vínculo se guardan en una sola transacción. Los casos elegibles pertenecen al mismo animal y comienzan el mismo día o después del hallazgo de origen. Se puede vincular un caso cerrado sin reabrirlo. La fila vinculada muestra **Ver caso** y el detalle incluye **Hallazgos de origen**, con texto, fecha y autor originales. Una observación reemplazada no admite vínculos nuevos, pero los casos ya vinculados conservan su evidencia original.

- `POST /api/v1/health/cases`: admite `observation_id` opcional, además de los campos existentes. Sin esa propiedad conserva el flujo independiente.
- `GET /api/v1/health/observations/{observation_id}/case-options?q=&limit=100`: casos del mismo animal elegibles por fecha, búsqueda por motivo y máximo 100 resultados; requiere `health:read`.
- `POST /api/v1/health/observations/{observation_id}/case-link`: `{"case_id":"UUID"}`; requiere `health:write`. Repetir el mismo vínculo es idempotente, sin duplicar auditoría; cambiarlo a otro caso devuelve 409.

Las observaciones del listado e historial incluyen `health_case` (`null` cuando no está vinculada). El detalle del caso añade `observations`. El historial integral identifica el caso vinculado en el hallazgo efectivo. Se validan animal, fecha y observación no reemplazada bajo bloqueo del animal; el identificador de observación es clave primaria del vínculo para impedir duplicados. Los vínculos generan auditoría en el módulo Sanidad. No se asocian retrospectivamente observaciones por coincidencias de texto o fecha.

### Bitácora de dosis realmente aplicadas

La migración `0021_treatment_doses.sql` crea registros independientes de la pauta de `event_treatments`, vinculados por su clave compuesta de evento y producto. No se generan dosis retrospectivas ni se interpreta una pauta como prueba de administraciones realizadas. La migración se aplica automáticamente al arrancar la API y no modifica archivos anteriores.

En **Sanidad → Ver caso → Tratamientos → Dosis aplicadas**, consultar la bitácora y usar **Registrar dosis aplicada**. Se captura fecha/hora local, persona que la aplicó, cantidad, unidad, vía y notas. El responsable es un nombre declarado para la aplicación; el usuario y rol que capturan el registro se obtienen de la sesión y se conservan por separado. La persona responsable se propone inicialmente con el nombre del usuario y puede cambiarse para registrar quién realmente aplicó la dosis. El historial sanitario permite consultar la bitácora sin editarla. También puede capturarse desde el historial de tratamientos de un programa sanitario. Los casos cerrados exigen reapertura antes de agregar aplicaciones, como los demás registros clínicos.

Endpoints de lectura/escritura: `GET/POST /api/v1/health/treatments/{event_id}/products/{product_id}/doses`, con `health:read` y `health:write`, respectivamente. GET tiene `offset`, `limit` (máximo 100) y total. POST recibe `applied_at` con zona horaria, `administered_by`, `dose_value`, `dose_unit_id`, `route_id` y `notes` opcionales. No admite identificadores de autor, rol ni animal proporcionados por el cliente. La pauta original no cambia. No hay PUT ni DELETE.

Se guardan el instante UTC, la fecha local y el desplazamiento horario declarado; la interfaz muestra el horario original de aplicación. No se permiten instantes futuros, cantidades no positivas o con más de tres decimales, aplicaciones anteriores al nacimiento/inicio del caso, posteriores a una salida o en tratamientos reemplazados. El mismo tratamiento/producto no admite dos registros para el mismo instante UTC, aunque se envíen zonas horarias diferentes. Las variaciones de fecha respecto al período indicado, cantidad, unidad o vía requieren explicación; se conservan como hechos observados y no alteran la indicación original ni constituyen autorización de una pauta nueva.

Los registros generan auditoría y aparecen como **Dosis aplicada** en el historial integral con su persona responsable y capturista. Se impide cambiar el nacimiento, fechar una salida o cerrar el caso de manera que contradiga aplicaciones existentes. El retiro utiliza estas aplicaciones reales y conserva las variaciones como **Por verificar**. Los tratamientos previos sin dosis muestran únicamente la pauta como referencia y no presentan una fecha de retiro confirmada. El punto 4 del inventario está terminado; ver Retiro sanitario para las reglas del cálculo.


### Alergias y reacciones adversas

**Sanidad → Alergias y reacciones → Registrar reporte** guarda la fecha observada, animal, tipo (`suspected_allergy` o `adverse_reaction`), descripción y agente sospechado opcional. Producto y dosis aplicada son vínculos opcionales: no se exige inventar una causa, un medicamento ni una aplicación. La relación no confirma causalidad. La búsqueda de dosis está paginada, se limita al animal/producto seleccionado y conserva aplicaciones de pautas reemplazadas; se permiten referencias históricas a productos inactivos.

`0022_animal_reactions.sql` se aplica al iniciar la API y crea `animal_reactions`, con autor, rol y fecha de captura. No cambia migraciones anteriores. Endpoints:

- `GET /api/v1/health/reactions`: búsqueda por nombre/SINIIGA (`q`), animal (`animal_id`), seguimiento (`status=open|closed`) y paginación (`offset`, `limit`, máximo 100). Requiere `health:read`.
- `GET /api/v1/health/reactions/dose-options?animal_id=...`: dosis reales del animal, con filtro opcional `product_id` y paginación. Requiere `health:read`.
- `POST /api/v1/health/reactions`: requiere `health:write`; campos `animal_id`, `date`, `kind`, `description`, `suspected_agent?`, `product_id?`, `dose_id?`. Una dosis determina el producto cuando este se omite; se rechazan animales/productos diferentes y fechas anteriores a la dosis.
- `POST /api/v1/health/reactions/{id}/closure`: `date` y `notes` obligatorios, con `health:write`. Cierra el seguimiento una sola vez, conservando el reporte original; un segundo cierre devuelve 409. Guarda autor/rol/fecha del cierre y auditoría. No permite editar ni borrar el reporte original.

El antecedente permanece visible, abierto o cerrado, en la ficha del animal, el detalle/historial sanitario y la captura de aplicaciones de programas. El panel muestra los cinco reportes más recientes y enlaza a la consulta paginada del animal. Solo consulta información con `health:read`. El historial integral incorpora reporte y cierre como hechos separados, sujetos a ese permiso; la auditoría los clasifica en Sanidad. Los nombres de personas/productos se resuelven con el catálogo actual; texto, fecha, vínculos y autores identificados se conservan en el reporte y su auditoría.

Se rechazan reportes futuros, anteriores al nacimiento o posteriores a una salida. Cambiar el nacimiento o fechar una salida no puede contradecir reportes existentes. El cierre administrativo sí puede ser posterior a la salida. Cerrar un seguimiento no confirma que una alergia haya desaparecido, y no tener reportes no confirma ausencia de alergias. Esta función registra antecedentes; no prescribe tratamientos ni modifica automáticamente las pautas o el retiro sanitario.


### Incidentes extraordinarios por animal

**Sanidad → Incidentes → Registrar incidente** captura un hecho por animal: accidente, aborto reportado, ataque, intoxicación reportada, desaparición u otro incidente. Requiere fecha y descripción; lugar reportado, acciones iniciales y caso sanitario son opcionales. Un vínculo a caso debe pertenecer al mismo animal. El registro no confirma diagnósticos, no modifica montas/gestaciones/partos y no crea una salida del hato. Un reporte de aborto requiere una hembra; impide cambiar posteriormente su sexo a macho mientras exista ese antecedente.

La migración automática `0023_animal_incidents.sql` crea `animal_incidents` e `incident_followups`, sin modificar migraciones anteriores. Endpoints:

- `GET /api/v1/health/incidents`: búsqueda por nombre/SINIIGA (`q`), animal (`animal_id`), tipo (`kind`), estado (`status=open|in_progress|closed`) y paginación (`offset`, `limit`, máximo 100).
- `GET /api/v1/health/incidents/case-options?animal_id=...`: casos del mismo animal, búsqueda por motivo (`q`) y límite máximo 100; permite referencias a casos abiertos o cerrados.
- `GET /api/v1/health/incidents/{id}`: reporte original, estado vigente, versión, fecha del último seguimiento y seguimientos paginados, del más reciente al más antiguo.
- `POST /api/v1/health/incidents`: `animal_id`, `date`, `kind`, `description`, `location?`, `initial_actions?`, `health_case_id?`. Tipos en inglés: `accident`, `abortion`, `attack`, `poisoning`, `disappearance`, `other`.
- `POST /api/v1/health/incidents/{id}/followups`: `date`, `notes`, `status`, `expected_version` y caso opcional `health_case_id`. Conserva cada nota, autor, rol y estado al registrar. Permite cerrar o reabrir con explicación; un seguimiento nuevo incrementa la versión. Una versión desactualizada devuelve 409 para evitar sobrescribir el trabajo de otra persona.

Las lecturas requieren `health:read`; las capturas, `health:write`. No existen endpoints para editar o eliminar el reporte original o sus notas. El estado vigente y la versión son metadatos actualizados bajo bloqueo del animal/incidente; cada cambio tiene su seguimiento y auditoría. La auditoría clasifica ambas tablas en Sanidad. Los nombres de autores/casos se resuelven con los catálogos actuales; los identificadores, fechas y textos originales se conservan.

Las fechas del reporte no pueden ser futuras, anteriores al nacimiento ni posteriores a una salida. Nacimiento y salida tampoco pueden modificarse de forma que contradigan un incidente existente. Los seguimientos no retroceden respecto del último registro y pueden continuar administrativamente después de la salida, sin crear actividad clínica. Un caso relacionado puede vincularse desde el reporte inicial o en una nota posterior, sin cambiar el estado del caso sanitario.

La ficha del animal y el detalle/historial sanitario muestran los cinco incidentes más recientes, incluidos los cerrados, con enlace a la lista filtrada. El historial integral muestra reporte y seguimientos como hechos separados sujetos al permiso de Sanidad. La tabla de incidentes permite buscar y filtrar, y Ver incidente permite añadir notas, cerrar y reabrir conservando la historia.


### Evaluaciones físicas descriptivas

**Animales → Evaluaciones físicas → Registrar evaluación** guarda animal, fecha, persona que evaluó y observaciones por apartado. El documento del proyecto menciona conformación/características físicas sin definir una escala: esta primera versión utiliza criterios descriptivos explícitos (`descriptive_v1`), sin calificación global, ranking, pureza racial ni valor genético inferidos.

Los apartados son estructura corporal (`body_structure`), patas y aplomos (`limbs_hooves`), desplazamiento (`movement`) y capa/pelaje (`coat_features`). Cada uno muestra su definición al capturar. Se exige al menos una observación; los apartados vacíos quedan como **Sin evaluar**, sin inventar valores cero. Son descripciones observadas, no un estándar racial ni una escala clínica. Una escala numérica futura requiere definir criterios, niveles y significado antes de implementarla.

La migración automática `0024_physical_evaluations.sql` crea `physical_evaluations`. Guarda una instantánea de código, etiqueta, definición y observación de los cuatro apartados, junto con su versión. También conserva evaluador declarado, capturista autenticado, rol y fecha de registro. La auditoría clasifica estos registros en Animales. Los nombres actuales del animal y capturista se resuelven con sus catálogos; el evaluador declarado, fecha, textos y definiciones se conservan.

Endpoints:

- `GET /api/v1/physical-evaluations/criteria`: versión, modalidad descriptiva y definiciones de los apartados.
- `GET /api/v1/physical-evaluations/animal-options`: animales activos, con búsqueda `q` y límite máximo 100.
- `GET /api/v1/physical-evaluations`: lista paginada por nombre/SINIIGA (`q`) o animal (`animal_id`), con `offset` y `limit` máximo 100. Incluye observaciones e instantáneas para consultar cada evaluación.
- `POST /api/v1/physical-evaluations`: `animal_id`, `date`, `evaluated_by`, `rubric_version`, `findings` (objeto con las cuatro claves anteriores y textos o null) y `notes?`. La versión debe coincidir con los criterios vigentes; una versión distinta devuelve 409.

Las lecturas requieren `animals:read`; la captura, `animals:write`. No se aceptan puntuaciones, identificadores de autor/rol enviados por el cliente, observaciones totalmente vacías, fechas futuras, anteriores al nacimiento o posteriores a una salida. Cambiar nacimiento o fecha de salida tampoco puede contradecir evaluaciones existentes. No hay edición ni eliminación: una revisión posterior es otro registro, sin borrar la anterior.

La ficha del animal permite desplegar las cinco evaluaciones más recientes y abrir la lista filtrada para consultar todas. El historial integral incorpora cada evaluación en Datos y decisiones, con evaluador y observaciones, y conserva los apartados sin evaluar explícitos. Las evaluaciones no modifican decisiones reproductivas, genealogía ni pesos.


### Habilidad materna y observaciones de las crías

**Reproducción → Evaluaciones maternas y de crías → Registrar evaluación** vincula la revisión a un parto registrado. Primero se busca el parto por madre/SINIIGA, se selecciona el tipo y, si corresponde, una cría de ese nacimiento. El parto determina la madre; el servidor valida la pertenencia de la cría. La búsqueda de partos está paginada e incluye partos históricos; excluye registros sustituidos para nuevas capturas.

La primera versión `breeding_descriptive_v1` es descriptiva, sin calificación global ni inferencia genética. Los criterios maternos son aceptación de las crías (`acceptance`), amamantamiento observado (`nursing`) y cuidado/atención (`care`). Para una cría son características físicas visibles (`body_features`), desplazamiento (`movement`) y desarrollo observado (`development`). El formulario explica cada criterio y exige describir al menos uno; los demás quedan **Sin evaluar**. Amamantamiento observado no determina cantidad/calidad de leche, y los rasgos visibles no confirman herencia ni pureza. Los pesos medidos y la evolución clínica siguen en sus módulos.

`0025_breeding_assessments.sql` crea `breeding_assessments` al iniciar la API. Guarda parto, animal evaluado, madre, padre conocido de la cría (cuando corresponda), tipo, fecha, evaluador declarado, capturista autenticado, rol, observaciones y versión. Cada registro conserva instantáneas de etiqueta, definición y observación de sus criterios. No permite edición ni borrado; una revisión posterior crea una evaluación nueva. Nombres actuales de animales/capturista se consultan de sus catálogos; texto y definiciones se conservan. Las observaciones maternas no se atribuyen al macho.

Endpoints con `breeding:read`:

- `GET /api/v1/breeding/assessments/criteria?kind=maternal|offspring`: criterios/versiones del tipo.
- `GET /api/v1/breeding/assessments/birth-options`: partos paginados por `q`, `offset`, `limit`; devuelve madre y crías registradas con indicador de vida al nacer.
- `GET /api/v1/breeding/assessments`: lista paginada con búsqueda por madre o animal evaluado (`q`), tipo (`kind`), parto (`birth_event_id`) y contexto de animal (`animal_id`). Este último incluye sus evaluaciones, observaciones de sus crías conocidas y, para la madre, sus evaluaciones maternas.

`POST /api/v1/breeding/assessments` requiere `breeding:write`: `birth_event_id`, `kind`, `offspring_id` solo para tipo offspring, `date`, `evaluated_by`, `rubric_version`, `findings` (claves del tipo y textos/null), `notes?`. Rechaza criterios desconocidos, puntuaciones, autor/rol enviados por el cliente, apartados completamente vacíos, versiones desactualizadas, partos sustituidos, crías ajenas, fechas futuras o anteriores al parto y evaluaciones posteriores a la salida del animal evaluado. Un padre que haya salido no impide evaluar posteriormente a su cría que permanece en el hato. Los controles de nacimiento y salida respetan el historial de evaluaciones del sujeto.

La ficha despliega las cinco evaluaciones más recientes del animal y sus descendientes, con enlace a la lista filtrada; requiere permiso reproductivo. Desempeño incluye Ver evaluaciones en cada reproductor, con filtro por ese animal. Cada registro identifica claramente cuál fue el animal evaluado. El historial integral las incluye en Reproducción para el sujeto y los progenitores conocidos; no las expone con solo permiso de Animales. La auditoría las clasifica en Reproducción. Una evaluación asociada a un parto sustituido permanece consultable como antecedente y lo señala; no se borra. No modifica montas, gestaciones, partos, pesos ni decisiones reproductivas automáticamente.


### Indicadores reproductivos con bases explícitas

**Reproducción → Indicadores** consulta hembras con reproducción/descendencia registrada o marcadas reproductoras. También se abre desde **Desempeño → Ver indicadores** por hembra. Es una consulta de solo lectura con `breeding:read`, sin migración nueva ni registros de auditoría por consultar.

`GET /api/v1/breeding/indicators` admite `q` (nombre/SINIIGA), `animal_id`, `date_from`, `date_to`, `as_of` (por defecto hoy), `age_days` (1–730, por defecto 60), `offset` y `limit` (máximo 100). `date_from ≤ date_to ≤ as_of ≤ hoy` cuando se proporcionan límites. El resumen comprende todas las hembras filtradas y todas las páginas; promedios y porcentajes se calculan con sumas de sus bases, nunca promediando porcentajes individuales. El indicador no reconstruye la composición histórica del hato: usa la genealogía actual y la historia efectiva actual, filtrada por fecha. Sustituciones posteriores conocidas pueden retirar evidencia anterior incluso si se consulta un corte pasado.

Reglas:

- **Entre partos registrados:** diferencia de días entre partos efectivos consecutivos de la hembra. Se incluye el par cuando el segundo parto está en el periodo; conserva el predecesor aunque quede antes del inicio. No hay intervalo sin dos registros. Expone cantidad, suma de días, promedio, mínimo y máximo. No presupone partos faltantes.
- **Montas con diagnóstico gestante:** selecciona montas del periodo; para cada una utiliza el último diagnóstico efectivo vinculado al mismo animal hasta `as_of`, incluso si fue posterior a `date_to`. La proporción es `gestantes / (gestantes + vacías) × 100`. Dudosos y montas sin diagnóstico se muestran aparte y se excluyen del denominador. Diagnósticos sin vínculo válido a una monta se cuentan por fecha del diagnóstico en el periodo, sin atribuirlos a una monta. Es una proporción de resultados registrados, no una tasa de fertilidad biológica, concepción o éxito por ciclo.
- **Monta a primer diagnóstico gestante vinculado:** días entre la monta seleccionada y su primer diagnóstico gestante efectivo hasta el corte, con número de observaciones. Puede existir un primer positivo histórico aunque el último diagnóstico sea diferente. No es duración de gestación ni fecha de concepción. Sin identificación fiable de ciclos, no se inventan intervalos entre gestaciones distintas a partir de diagnósticos repetidos.
- **Sin muerte registrada a una edad:** selecciona descendientes por nacimiento dentro del periodo; una condición al nacer conocida exige vínculo a un parto efectivo. Usa la fecha del parto cuando esa evidencia existe; para genealogía manual usa fecha de nacimiento actual, conservando la condición desconocida. Solo nacidos vivos conocidos que cumplen la edad al corte pueden entrar al denominador. Una muerte o sacrificio efectivo hasta el día objetivo inclusive es desenlace registrado; una venta u otra salida hasta ese día es seguimiento incompleto y se excluye. Sin salida hasta ese día, se clasifica Sin muerte registrada. Una muerte/salida posterior no reescribe el desenlace a una edad anterior. La proporción es `sin muerte registrada / (sin muerte registrada + muertes o sacrificios) × 100`, sin asumir seguimiento después de una salida. No confirma supervivencia real ni estima una curva estadística de supervivencia.

Sin denominador o sin pares, se devuelve null y se muestra **Sin base**, distinto de 0 %. Se detallan nacidos sin vida, condición al nacer desconocida, falta de fecha, crías aún sin edad y salidas tempranas. Sin límites de periodo se incluyen registros manuales sin fecha como categoría explícita; con límites quedan fuera de la cohorte porque no se pueden situar en el periodo.

`GET /api/v1/breeding/indicators/{animal_id}/details` requiere una hembra y los mismos filtros de periodo/corte/edad; `section=birth_intervals|matings|offspring` selecciona el detalle paginado. La interfaz conserva los filtros aplicados al abrir el cálculo, aunque se hayan editado campos sin pulsar Calcular. Las listas permiten verificar las fechas, el resultado vinculado y las exclusiones. No modifica el reporte anterior de Desempeño ni las capturas reproductivas.


### Salud registrada de las crías en Desempeño

**Reproducción → Desempeño** integra casos sanitarios de descendientes tanto para hembras como para machos. Con permisos `breeding:read` y `health:read` muestra crías con/sin casos registrados, total de casos y distribución entre abiertos, en tratamiento y cerrados. Una cría con varios casos cuenta una sola vez como descendiente con casos; cada caso conserva su propio conteo. El resumen usa todos los progenitores filtrados, no únicamente la página visible.

Desde **Ver crías → Ver casos sanitarios** se despliega el motivo, estado, fecha de inicio/cierre y enlace **Ver caso** al detalle sanitario existente. La consulta está paginada (10 por defecto, máximo 100) y se hace solo al desplegar; incluye casos de animales que ya salieron y los cerrados. No modifica casos ni genera auditoría por consultar.

El periodo de Desempeño selecciona descendientes por nacimiento, según la genealogía actual. Sus casos se consultan hasta hoy y sus estados son los actuales; no se filtran por la fecha de inicio del caso ni se reconstruye su estado anterior al periodo. Por eso un caso posterior al periodo de nacimientos puede aparecer como seguimiento de esa cohorte. Los descendientes sin nacimiento conocido se incluyen solo sin límites de periodo, como en el reporte existente. Cero casos significa **Sin casos registrados**, sin afirmar que la cría está sana. Los conteos no establecen herencia, causalidad ni valor genético.

Las respuestas de `/api/v1/breeding/performance` añaden `health_summary` y `items[].health` solo si el usuario tiene `health:read`. El detalle de descendientes añade `parent.health` e `items[].health` bajo la misma condición. Sin ese permiso, los campos se omiten por completo y no se ejecuta la consulta de conteos sanitarios; Reproducción sigue disponible con su permiso propio.

`GET /api/v1/breeding/performance/{parent_id}/offspring/{child_id}/health-cases` exige ambos permisos. Valida la relación madre/padre actual, el periodo de nacimientos (`date_from`, `date_to`), la fecha no futura del descendiente y la paginación. Una cría ajena o fuera de cohorte devuelve 404, y falta de permisos devuelve 403. Solo entrega resúmenes de los casos de esa cría, con enlace para consultar su detalle en Sanidad. No requiere migración nueva.

### Decisiones vigentes de manejo

Animales → Decisiones vigentes consulta `GET /api/v1/management-decisions` con `animals:read`, búsqueda, tipo de decisión, sexo, estado y paginación. La última decisión de conservar para reproducción, descartar para reproducción, separar o prever venta reemplaza el plan anterior según fecha clínica, fecha de captura e ID descendentes. Las notas de compra y otras decisiones no lo reemplazan. El filtro por tipo se aplica después de seleccionar la vigente. Los totales corresponden a todos los animales filtrados.

La vista muestra contexto **actual**, no una fotografía al tomar la decisión: casos sanitarios/retiro con `health:read`, montas/partos/último diagnóstico posterior al parto con `breeding:read`. Sin esos permisos, los campos se omiten. El historial individual conserva todas las decisiones y permite registrar otro criterio desde la ficha; no se modifican automáticamente reproductores, lotes ni salidas. Los animales con salida aparecen sólo al ampliar el filtro, como antecedentes. No necesita migración nueva.

### Venta por kilogramo con pesaje vinculado

1. En Manejos → Pesajes registra el peso real del animal el día de la venta, antes de registrar la salida.
2. En Salidas registra la venta con esa misma fecha.
3. En Economía → Ingresos → Registrar ingreso selecciona Venta por kilogramo, la salida, el pesaje y el precio por kg en MXN. La fecha del ingreso puede ser posterior a la salida.

`GET /api/v1/finance/sales/{exit_id}/weights` muestra los pesajes efectivos del mismo animal y día de salida; requiere `finance:read`, como evidencia de la venta. Al guardar un ingreso con `pricing_mode=per_kg`, `exit_event_id`, `weight_event_id` y `price_per_kg`, el servidor calcula `peso × precio`, redondeado `ROUND_HALF_UP` a dos decimales. `amount` puede omitirse; si se envía, debe coincidir. No utiliza el último pesaje de otro día ni acepta uno reemplazado. El total conserva el límite decimal de ingresos.

La migración nueva `0026_sale_weight_pricing.sql` se aplica automáticamente al iniciar la API; no modifica migraciones anteriores ni ingresos por importe total. El ingreso guarda el ID de pesaje y una copia del peso/precio utilizados. El detalle y Excel de ingresos incluyen el desglose. Los totales existentes siguen sumando `incomes.amount` una sola vez. Ediciones financieras explícitas conservan antes/después en auditoría y vuelven a validar el pesaje; cambiar a importe total elimina el desglose actual, conservando el anterior en auditoría. No ejecuta una salida automáticamente.

Verificación local: pruebas SQLite de cálculo, vínculos, redondeo, duplicados, permisos, auditoría, reportes y compatibilidad; pruebas del formulario, compilación y revisión visual con API simulada en escritorio/móvil. La ejecución real de la migración en MySQL requiere el entorno de integración separado; no se verificó contra Aiven.

### Principios activos y composición de productos

Sanidad → Principios activos permite consultar, buscar, crear y corregir nombres y eliminar entradas sin productos vinculados. Cuenta productos activos e inactivos; los nombres son únicos sin distinguir mayúsculas y se recortan espacios exteriores. Usa `GET/POST /api/v1/health/ingredients` y `PUT/DELETE /api/v1/health/ingredients/{id}` con permisos `health:read`/`health:write`. Creación, corrección, eliminación y asignaciones generan auditoría.

En Productos, crear/editar permite seleccionar varios principios activos y agregar uno al catálogo desde el mismo formulario. Crear inline guarda inmediatamente la entrada del catálogo; su asignación se confirma con Guardar producto. El listado muestra nombres o Sin principios activos registrados. Se trata de composición **actual** del catálogo; no registra concentración ni infiere composición histórica, dosis, interacciones o causalidad de una reacción. Renombrar una entrada actualiza su nombre mostrado en todos los productos vinculados; el valor anterior queda en auditoría.

`ProductInput.ingredient_ids` admite hasta 100 identificadores positivos y únicos: omitirlo o enviar `null` preserva las asignaciones de un producto existente; `[]` las elimina explícitamente. La API valida existencia y bloquea entradas al asignar/eliminar. `ProductResponse.ingredients` entrega ID y nombre de la composición actual. Las tablas `active_ingredients` y `product_ingredients` ya existen en la migración inicial, por lo que no hay migración nueva.

### Precios históricos y costo calculado de aplicaciones

Productos muestra precio vigente para usuarios con `health:read` y `finance:read`. Al crear un producto, el precio inicial es opcional en el mismo formulario; requiere `finance:write` y se guarda en la misma transacción del producto. El botón Historial de precios permite consultar vigencias y agregar una fecha/costo por **1 unidad del producto**, en MXN con dos decimales. Por ejemplo, para unidad ml se captura costo por ml, no por frasco. Precios futuros quedan programados y no reemplazan el vigente antes de su fecha. Las vigencias no se sobrescriben ni eliminan; fechas duplicadas se rechazan con 409 y auditoría conserva cada alta. La unidad del producto no puede cambiar si existen precios. El formulario envía la unidad esperada para detectar cambios concurrentes anteriores al primer precio.

`GET/POST /api/v1/health/products/{id}/prices`: lectura con `health:read` + `finance:read`; alta con `health:read` + `finance:write`. `ProductInput.initial_price` admite `effective_from` y `cost` para altas de productos; actualizar un producto exige usar el historial para nuevas vigencias. El listado omite `current_price` sin permiso financiero. Reutiliza `product_prices`, existente en la migración inicial: no hay migración nueva.

En tratamientos de casos, historial y programas, Dosis aplicadas → Costo de aplicaciones consulta `GET /api/v1/health/treatments/{event_id}/products/{product_id}/cost`, con lectura sanitaria y financiera. Valora cada aplicación real usando su **fecha clínica local guardada**, cantidad aplicada y último precio vigente anterior o igual a esa fecha. Sólo calcula si el ID de unidad de dosis coincide con el del producto; no convierte unidades ni estima cantidades desde frecuencia/duración de la pauta. Mantiene cero conocido distinto de precio faltante. Redondea cada aplicación a centavos (`ROUND_HALF_UP`) y suma esos costos. El resumen incluye todas las aplicaciones del tratamiento/producto aunque el detalle esté paginado.

Sin aplicaciones no hay costo total determinado; con faltantes se muestra subtotal conocido y cantidad sin determinar. Es valoración de material según precios registrados, no factura, gasto pagado ni costo integral (no incluye mano de obra u otros conceptos). Agregar una vigencia pasada puede cambiar cálculos al consultarlos nuevamente; no se afirma un precio histórico que no se haya registrado. No genera gastos ni modifica las dosis.

### Reparto calculado de costos de lote entre animales

Economía → Costos por animal o lote → Consultar costos → Reparto calculado de lotes. Se consulta para un lote o para un animal y el mismo rango de fechas aplicado. Por animal muestra las partes que le corresponden por sus pertenencias históricas; por lote muestra todos sus destinatarios. Origen del reparto permite abrir el detalle paginado de cada gasto/consumo y verificar miembros e importes.

Criterio fijo y explícito: reparto igual entre miembros del lote **en la fecha de cada registro**, con entrada y salida de pertenencia inclusivas. Una baja permite actividad el mismo día, pero excluye días posteriores; se excluyen fechas anteriores a un nacimiento conocido. Identificadores duplicados de un mismo animal se cuentan una vez por fuente. Los cambios de lote posteriores no eliminan pertenencias anteriores. No reparte por peso, horas, días de un periodo de cobertura, ni presume consumo individual: los gastos no tienen un periodo de cobertura definido.

Para un gasto, primero se calcula sólo la porción realmente asignada al lote con la política de centavos existente sobre todas las asignaciones del gasto. Después reparte esa porción entre los miembros elegibles, dividiendo centavos enteros y asignando sobrantes por ID de animal ascendente. Nunca vuelve a repartir el gasto completo si sólo parte corresponde al lote. Para alimentación usa el costo conocido del consumo del lote con su precio histórico vigente y redondeo por consumo, y reparte ese costo; no registra cantidades individuales.

Gastos y alimentación permanecen separados: pueden representar la misma compra y no se suman como si fueran costos diferentes. Sin miembros, el importe queda sin repartir y se muestra explícito; sin precio, no se inventa un valor ni se presenta como costo completo. El resumen corresponde a todos los resultados, no sólo a la página. En modo animal, `attributed_expenses` y `attributed_feeding` corresponden sólo al animal consultado; los campos `source_*` describen los importes completos de sus fuentes de lote relacionadas. Sin `feeding:read` se omiten fuentes/importes de alimentación.

`GET /api/v1/finance/group-costs` requiere `finance:read`; parámetros `kind=animal|group`, `target_id`, `date_from`, `date_to`, `view=animals|sources`, `offset`, `limit`. `GET /api/v1/finance/group-costs/sources/{expense|feeding}/{source_id}` pagina los miembros del registro; para gasto usa el ID de su asignación, no el ID del gasto. Alimentación requiere además `feeding:read`. Sólo se consideran fuentes hasta la fecha actual.

El cálculo es de consulta y usa los datos históricos disponibles actualmente: cambiar asignaciones, pertenencias o precios puede cambiarlo. No crea gastos, no altera porcentajes ni saldos, y no guarda una distribución irreversible. Reutiliza tablas existentes sin migración nueva. No se mezcla con los totales directos de la vista anterior.

### Resultado individual y costo integral registrado

Economía → Resultado por animal reúne ingresos y gastos registrados atribuibles. Base financiera: `ingresos vinculados − gastos registrados atribuidos`, incluidos costo directo del animal, partes asignadas a sus casos sanitarios y partes calculadas de gastos del lote según pertenencias históricas. La suma conserva centavos. Compras de alimento y medicamentos son gastos cuando se registran como tales; alimentación y aplicaciones reales valoradas son **referencias separadas** y no se deducen otra vez. Se comparte la valoración de dosis con el historial sanitario.

El periodo corresponde a la fecha elegida del ingreso/gasto; referencias usan fecha de consumo/aplicación. Sin fechas se consulta hasta hoy; el corte de estado usa Hasta o la fecha actual. Nacimiento conocido posterior al corte se identifica, sin clasificarlo como activo o salido en esos filtros. Conserva animales con salida para sus ingresos posteriores. Ventas se atribuyen por el evento original vinculado, incluso si se sustituye su historial operativo: no se borra un ingreso financiero por reemplazar un evento.

Cobertura muestra gastos generales sin asignación, residuos y partes de lote sin miembros como pendientes. No los distribuye arbitrariamente. Desde Gastos pendientes de atribuir se abre el editor existente y al guardar se recalcula. Ingresos sin animal abre el ingreso exacto en Economía para vincularlo a una venta o directamente a un animal. Cobertura abarca todo el rancho para el periodo; búsqueda/estado afectan filas y resumen de animales. Totales abarcan todas las páginas.

La migración nueva `0027_income_animal.sql` agrega `incomes.animal_id` opcional con FK y restricción que impide usarlo simultáneamente con una salida. `IncomeInput.animal_id` atribuye el importe completo de un ingreso sin venta a un animal existente; rechaza fechas anteriores a su nacimiento conocido. La fecha financiera puede ser posterior a su salida. Listado, detalle, Excel e historial integral muestran el vínculo y auditoría conserva las ediciones. Los registros anteriores permanecen sin cambios. La migración se aplica al iniciar la API y no modifica migraciones aplicadas.

APIs con `finance:read`: `GET /api/v1/finance/profitability` (q, status, date_from/to, offset/limit), `/profitability/pending?kind=expenses|incomes`, `/profitability/{animal_id}/entries?section=incomes|expenses|feeding|medicines` y `/incomes/{id}`. Secciones de referencia requieren `feeding:read` o `health:read`; se omiten sin esos permisos. Escribir vínculos/porcentajes requiere `finance:write`. Consultar no crea movimientos ni auditoría.

Integra registros financieros atribuidos, incluidos generales una vez asignados. No presume inventarios, depreciación, trabajo, compra del animal ni costos ausentes; no certifica utilidad final ni costo devengado. Cambios de asignación, pertenencia, importes o precios pueden cambiar consultas posteriores. La prueba manual del reparto con importes fue aplazada por el usuario y queda como revisión operativa pendiente.


### Permisos sanitarios por acción

La migración `0028_health_action_permissions.sql` reemplaza `health:write` por acciones explícitas, conservando los accesos completos que ya tenía cada rol (incluidos los personalizados). No modifica migraciones previas ni concede Sanidad a roles que no la tenían. Se aplica automáticamente al iniciar la API. Recarga el frontend o vuelve a iniciar sesión para obtener los permisos nuevos.

Cada acción requiere `health:read`; la API rechaza un rol con acciones sin consulta. Roles activa la consulta al marcar una acción y retira sus acciones al desmarcar la consulta. El permiso general anterior deja de aceptarse al crear/editar roles. Los permisos se consultan desde la base en cada petición, por lo que retirarlos afecta también a tokens ya emitidos.

| Permiso | Acciones |
| --- | --- |
| `health:observations:create` | Registrar observaciones |
| `health:cases:write` | Abrir casos, vincular hallazgos y cambiar estado |
| `health:diagnoses:create` | Registrar diagnósticos |
| `health:treatments:create` | Indicar pautas de tratamiento |
| `health:doses:create` | Registrar dosis realmente aplicadas |
| `health:followups:create` | Registrar evolución y revisiones |
| `health:products:write` | Administrar productos y principios activos |
| `health:programs:write` | Crear/editar programas sanitarios |
| `health:program_applications:create` | Registrar pautas de programas; no crea dosis reales |
| `health:reactions:write` | Registrar/cerrar antecedentes de reacciones y alergias |
| `health:incidents:write` | Registrar incidentes y seguimientos |

Los precios conservan sus permisos financieros adicionales. No se presupone autorización profesional por el nombre del rol: el dueño selecciona las responsabilidades. Indicar un tratamiento no concede permiso para registrar dosis y registrar dosis no permite indicar tratamientos. Los permisos restantes por módulo conservan su alcance.

Prueba manual sugerida: en Roles edita Trabajador, conserva sus permisos ajenos a Sanidad, habilita solo consultar Sanidad y registrar observaciones, guarda y entra con una cuenta de ese rol. Debe aparecer Observación y no Abrir caso ni las acciones de diagnóstico/tratamiento/dosis. Después prueba esos permisos individualmente según las responsabilidades reales de cada cuenta.


### Rectificación del historial sin borrar el original

Animales → Ver ficha → Historial completo → Rectificar registro. La migración nueva `0029_history_rectifications.sql` crea un historial inmutable de rectificaciones: motivo obligatorio (10–2000 caracteres), autor y rol conservados, fecha UTC, versión, instantánea del origen y datos corregidos cuando hay sustitución. El permiso independiente `history:rectify` se concede inicialmente solo al dueño del sistema; los demás roles necesitan asignación explícita. También se exigen lectura de Animales, lectura del módulo y su autorización de captura específica (incluidas las acciones sanitarias separadas).

Hay dos modos deliberadamente distintos:

- **Agregar aclaración:** disponible para todas las fuentes visibles del historial de ese animal. Conserva una explicación (10–5000 caracteres) junto al origen. No modifica importes, fechas, cantidades, estados ni cálculos. Para registros de lote compartidos, la nota pertenece al historial del animal seleccionado, no a todos sus miembros.
- **Sustituir con datos corregidos:** pesajes ordinarios sin vínculo a venta/destete, observaciones sin vínculo a caso y diagnósticos de casos abiertos. Usa los validadores/repositorios de captura existentes y crea otro evento con `replaced_event_id`; nunca cambia el original. Mantiene el mismo animal y, para diagnósticos, el mismo caso. Lecturas sanitarias, crecimiento, reportes de pesajes y opciones de venta usan los eventos efectivos. Los pesos que respaldan ventas o destetes solo admiten aclaración. No se corrigen automáticamente dosis reales, retiros, finanzas, partos, salidas u otros hechos mediante una nota.

Cada alta requiere la versión y hash de la fuente consultada. Se serializa con escrituras del animal, se detectan ventanas desactualizadas y la clave única impide duplicar la misma versión. Al sustituir se conservan todos los antecedentes de la cadena, con el texto/peso anterior, datos nuevos, motivo y responsable. La UI permite consultarlos sin el permiso especial siempre que la cuenta conserve las lecturas del área; no expone fuentes sanitarias con solo permiso de Animales. La auditoría clasifica la rectificación según el módulo de origen. No hay endpoints de edición ni borrado de rectificaciones.

API: `GET /api/v1/animals/{animal_id}/rectifications?entry_id=...` obtiene contexto, instantánea, permisos y versiones; `POST` crea una aclaración o sustitución. `entry_id` procede del historial, no de texto libre; el servidor valida que la fuente siga perteneciendo a ese historial y a un módulo consultable. Si ya fue sustituida, se recarga el historial para operar sobre su registro vigente. Los comprobantes previos no se reescriben y una aclaración no debe interpretarse como una modificación operativa de ellos.


La precisión de microsegundos de las fechas de rectificación se aplica en `0030_rectification_timestamp_precision.sql`. La migración 0029 conserva su contenido original para que los servidores que ya la iniciaron o aplicaron puedan reiniciar con la comprobación de checksum intacta. No se requiere borrar tablas ni modificar `schema_migrations`.


### Revisión de perfiles operativos

El informe [Revisión local de los seis perfiles](docs/REVISION_SEIS_PERFILES.md) documenta la matriz de referencia, las comprobaciones permitidas/denegadas y el flujo compartido entre responsables. `tests/test_operational_profiles.py` configura los roles mediante la API en una base temporal; `tests/fixtures/profile_matrix.json` contiene la asignación explícita de prueba, sin cambiar roles reales. La revisión completa aprobó 215 pruebas backend y 253 frontend, además de compilación y navegación simulada en Chrome. La validación posterior de MySQL con carga y concurrencia real está documentada por separado en `docs/VALIDACION_MYSQL.md`.


### Validación integral en MySQL y pruebas simultáneas

El informe [Validación de MySQL, volumen y concurrencia](docs/VALIDACION_MYSQL.md) documenta 237 pruebas MySQL y 215 SQLite aprobadas. Incluye cinco escenarios de escrituras realmente simultáneas y una carga de 1,000 animales, 5,000 pesajes, 10 lotes y movimientos económicos/alimentarios. Se usan instancias y bases temporales, no datos del rancho.

Con MySQL Server instalado localmente, ejecutar desde el backend:

```bash
python -m scripts.validate_mysql --suite all
```

Las modalidades `--suite migrations`, `--suite concurrency` y `--suite volume` repiten cada parte. El comando inicializa su propio MySQL sin puerto de red, pasa una URL de pruebas por socket a pytest, conserva los informes/logs y detiene el servidor por su interfaz administrativa. La opción de pytest `--mysql-api` permite ejecutar la batería de API sobre esquemas creados y migrados de forma independiente, sin cambiar el fixture SQLite predeterminado.

El control de pesos diarios usa ahora una lectura de bloqueo actual después de esperar por el animal, para impedir dobles capturas bajo MySQL REPEATABLE READ. El listado de animales precarga padres, salidas y ubicaciones por página; en la carga medida pasó de 81 a 8 consultas por 25 animales conservando su respuesta. La migración nueva `0031_capture_timestamp_precision.sql` preserva los microsegundos de captura para mantener el orden y la misma fecha entre alta/consulta. No modifica migraciones anteriores ni reconstruye fracciones de tiempo ya descartadas.


## Despliegue preparado

La instalación de producción con Docker, HTTPS, límite de login, frontend del mismo origen y comprobaciones de disponibilidad está documentada en [docs/DESPLIEGUE.md](docs/DESPLIEGUE.md). Está validada localmente; aún no se ha publicado porque no hay servidor. El desarrollo local conserva sus comandos actuales.


## Respaldos y recuperación

[Guía de respaldos y restauración](docs/RESPALDOS_Y_RESTAURACION.md): simulacro local sin Aiven (`python -m scripts.validate_recovery`), exportación mediante archivo privado del cliente MySQL y verificador que restaura exclusivamente en un servidor local nuevo sin red. Aiven se usa solo para pruebas. La política del servidor definitivo y una copia real independiente se configurarán/comprobarán cuando se asigne el destino.


## Guía para los usuarios del rancho

La [Guía de operación](docs/GUIA_DE_OPERACION.md) explica los pasos por pantalla, las correcciones históricas, la interpretación de costos y los problemas frecuentes. El [formato de entrega de responsabilidades](docs/ENTREGA_DE_RESPONSABILIDADES.md) permite registrar pendientes y comprobar accesos al cambiar de encargado o veterinario.

Aiven es el entorno temporal de pruebas. Quedan dos puntos para el servidor definitivo: publicar/migrar/verificar el sistema y configurar/probar sus respaldos. No se requiere contratar ni mantener Aiven para dar esos pasos.


## Perfil y foto del usuario

En el menú del usuario → **Mi perfil** se consultan nombre, segundo nombre, apellidos, correo, teléfono y rol; **Editar datos** permite modificar los datos personales y se puede agregar o reemplazar la foto propia. No requiere permisos de administración de usuarios.

- `GET /api/v1/profile`: perfil de la sesión.
- `PATCH /api/v1/profile`: modificación parcial de nombre, segundo nombre, apellidos, correo y teléfono del usuario autenticado; valida correo único, conserva foto y sesión, audita cambios y rechaza rol, permisos, estado, contraseña, IDs o URLs de foto. Segundo nombre/teléfono vacíos se guardan como nulos. No requiere otra migración.
- `POST /api/v1/profile/photo`: multipart con campo `file`, autenticado, sin ID de otro usuario. JPEG/PNG/WebP estáticos hasta 5 MB y 25 megapíxeles; validación del contenido real, orientación EXIF aplicada, reducción máxima a 1024 × 1024 sin deformar, WebP sin metadatos originales.
- Guarda el archivo en `upload/photos_profile` y solo la URL relativa en `users.profile_photo_url`. Se devuelve en login, `/auth/me`, perfil y respuestas de usuario; el frontend resuelve la URL contra el origen de la API y refresca el avatar.
- Nombre: rol y primer nombre normalizados sin espacios/acentos/caracteres especiales, seguidos de fecha UTC `YYYYMMDDHHMMSSffffff`, extensión `.webp`. La precisión y creación exclusiva evitan sobrescribir archivos homónimos. No utiliza el nombre enviado por el navegador.
- El cambio bloquea la fila del usuario; un fallo de guardado/commit retira el archivo nuevo y conserva el anterior. Después de guardar la referencia se elimina la foto previa; si el sistema de archivos impide retirarla se deja diagnóstico en el log. Se auditan las URLs anterior y nueva.
- Migración nueva e inmutable `0032_profile_photo.sql`; se aplica al iniciar. `PROFILE_PHOTOS_DIR` permite configurar otro directorio físico sin cambiar la URL pública `/upload/photos_profile/`. Las fotos se sirven como archivos públicos por esa URL, no como rutas autenticadas.
- Compose conserva las fotos en un volumen `profile_photos`; Nginx enruta sus URLs a la API y admite el multipart de la foto. El directorio no se incluye en Git ni en la imagen. Para migración o recuperación hay que copiar/resguardar también los archivos: un dump SQL conserva las URLs, no las imágenes.

Verificación: conversión/rotación/metadatos, límite y rechazo de archivos inválidos, reemplazo y rollback, permisos propios, migración de usuarios existentes y reemplazos simultáneos reales en MySQL aislado; pruebas frontend y Chrome de escritorio/móvil con API simulada.
