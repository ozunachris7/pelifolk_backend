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
