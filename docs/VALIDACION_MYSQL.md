# Validación de MySQL, volumen y concurrencia

Fecha: 17/10/2026. Motor comprobado: MySQL Community Server 8.4.11, Linux. Se usa un servidor temporal con directorio propio y permisos privados en `/tmp`, socket Unix, red deshabilitada y MySQL X deshabilitado. No se usa `DATABASE_URL` para elegir el servidor de pruebas y no se conecta a Aiven.

## Resultado final

- **237 pruebas aprobadas en MySQL**, sin fallos, errores ni pruebas omitidas; incluye las 16 verificaciones MySQL que antes estaban pendientes y seis pruebas nuevas de concurrencia/volumen. Informe JUnit de esta ejecución: `/tmp/pelifolk-mysql-validation-9qxmqp_a/results.xml`.
- **215 pruebas aprobadas en SQLite**, 22 verificaciones específicas de MySQL excluidas expresamente. Informe JUnit: `/tmp/pelifolk-sqlite-validation.xml`.
- Las cinco pruebas simultáneas y la medición de volumen también se ejecutaron de forma focalizada después de sus ajustes. El listado final usa ocho consultas en la carga descrita abajo.
- El comando de reproducción con el cierre administrativo final fue verificado en su modalidad de concurrencia: cinco pruebas aprobadas, código de salida cero y `server_stopped: true` en `/tmp/pelifolk-mysql-validation-mlahtvjw/summary.json`. Las instancias temporales de las verificaciones anteriores también quedaron cerradas por su socket administrativo.
- Se conserva una advertencia de Starlette/httpx sobre una dependencia del cliente de pruebas. No produjo fallos de las verificaciones.

Esta etapa verifica una instancia MySQL local aislada y una carga definida. No certifica la configuración o rendimiento del servidor real de Aiven.

## Cómo repetirla

Desde el backend, con su entorno virtual activo y MySQL Server instalado localmente:

```bash
python -m scripts.validate_mysql --suite all
```

Para repetir solo una parte:

```bash
python -m scripts.validate_mysql --suite migrations
python -m scripts.validate_mysql --suite concurrency
python -m scripts.validate_mysql --suite volume
```

El comando crea su propio directorio temporal, inicializa un servidor nuevo y ejecuta pytest con una URL de pruebas explícita por socket. Cada fixture crea una base `pelifolk_test_<uuid>` distinta, aplica las migraciones reales y elimina exclusivamente esa base al terminar. El fixture de API controla sus catálogos y cuentas igual que la batería SQLite; las pruebas de migraciones comprueban por separado los datos iniciales auténticos. Nunca se reutiliza una base del rancho ni se desactivan sus restricciones para hacer pasar las pruebas.

El servidor temporal se detiene mediante `SHUTDOWN` por su socket administrativo. Se conservan `pytest.log`, `results.xml`, `summary.json`, logs del servidor y los archivos de datos en la carpeta temporal indicada por el comando. El usuario root sin contraseña existe solamente dentro de esa instancia privada sin puerto de red; no se modifica la instalación MySQL del sistema ni se lee la contraseña de la aplicación.

También se puede usar un servidor de pruebas administrado por separado, asignando expresamente `PELIFOLK_TEST_MYSQL_URL` y ejecutando:

```bash
python -m pytest tests --mysql-api -q
```

Esa modalidad requiere permiso para crear y eliminar bases de pruebas y no debe apuntar al servidor de producción. Sin `--mysql-api`, el fixture de API sigue utilizando SQLite. Las pruebas MySQL no usan una URL de la aplicación como alternativa automática.

## Migraciones y flujos

Se aplica el esquema desde SQL real, con claves foráneas, restricciones, funciones y triggers habilitados. Se verifican reinicios, continuidad tras fallos, datos existentes, checksum inmutable, conservación de datos y los flujos funcionales de la batería completa, incluidos los seis perfiles, sanidad, genealogía, reproducción, alimentación, finanzas, reportes y rectificaciones.

Las pruebas antiguas que esperaban exactamente 43 tablas o cuatro permisos sanitarios se actualizaron para comprobar todas las tablas mapeadas actuales y el conjunto exacto de permisos sanitarios por rol. Las consultas directas de auditoría de las pruebas ahora ordenan por fecha e ID; no se presupone un orden de lectura implícito de SQL. El caso de genealogía con datos legados usa un ciclo entre dos animales, sin intentar violar la restricción MySQL que prohíbe ser su propio padre/madre.

## Escrituras realmente simultáneas

`tests/test_mysql_validation.py` lanza dos peticiones desde hilos distintos y sincroniza sus lecturas iniciales de autenticación antes de permitir las escrituras. Cada petición tiene su propia sesión/conexión de base de datos. Esto reproduce ventanas de lectura anteriores al bloqueo con el aislamiento normal de MySQL; no se sustituye por dos llamadas secuenciales ni se relaja el aislamiento global.

Se exige una escritura exitosa y un conflicto 409, conservando un único resultado, en estos casos:

1. Dos pesajes para el mismo animal y día.
2. Asignación del mismo animal a dos lotes en el mismo periodo.
3. Registro duplicado de la misma dosis real.
4. Dos rectificaciones de la misma versión del historial.
5. Dos seguimientos del mismo incidente desde la misma versión.

Se comprueba además el número de filas y, en rectificaciones, que exista una sola auditoría de la operación ganadora.

La prueba encontró que el control de pesos diarios podía leer la instantánea anterior a esperar el bloqueo del animal. Ahora la comprobación de duplicados usa una lectura de bloqueo actual. No se cambia el aislamiento del servidor ni se retiran validaciones de fechas, destetes o sustituciones.

## Volumen utilizado

La carga sintética contiene:

| Datos | Cantidad |
| --- | ---: |
| Animales | 1,000 |
| Pesajes | 5,000 |
| Lotes | 10 |
| Pertenencias históricas | 1,000 |
| Ingresos vinculados | 1,000 |
| Gastos | 1,010 |
| Asignaciones de gastos | 1,010 |
| Consumos de alimentación | 1,000 |

Se comprueba paginación sin repetir animales entre páginas, búsqueda exacta, totales de todas las páginas, historial individual, reparto histórico de lote y reporte de pesos. Los totales financieros deben ser exactamente 100,000.00 de ingresos, 40,500.00 de gastos atribuidos y 59,500.00 de resultado. La alimentación de referencia es 17.00 por animal y no se descuenta otra vez como gasto.

La medición cuenta consultas desde el inicio de cada petición, incluida autenticación. El listado tenía 81 consultas para 25 animales. Ahora precarga salidas, ubicaciones y padres por página y usa ocho consultas en la misma carga, manteniendo sus datos y permisos.

Medición local después de la optimización, con otros procesos de prueba también activos:

| Consulta | Tiempo observado | Consultas SQL |
| --- | ---: | ---: |
| Animales, página de 25 | 25.60 ms | 8 |
| Animales, página siguiente | 8.84 ms | 8 |
| Buscar un SINIIGA | 8.88 ms | 8 |
| Resultado por animal, totales de 1,000 | 133.96 ms | 18 |
| Reporte de 5,000 pesos, respuesta de 25 | 218.41 ms | 4 |
| Historial de un animal | 53.25 ms | 38 |
| Reparto del lote de 100 miembros, respuesta de 25 | 14.16 ms | 11 |

La prueba limita el listado a un máximo de 12 consultas por página para detectar regresiones de consultas por animal. Los demás endpoints tienen un presupuesto de 150 consultas y 10 segundos como control de regresión, no como compromiso de tiempo de respuesta en producción. Los tiempos de una instancia local no predicen la latencia de Aiven ni constituyen una prueba de carga sostenida o de múltiples dispositivos por internet. Algunos reportes calculan los totales sobre el conjunto filtrado antes de paginar su respuesta; los resultados anteriores no certifican memoria o latencia para historiales ilimitados.

## Precisión de fechas de captura

La comparación de respuestas y del orden de altas encontró columnas MySQL que descartaban los microsegundos enviados por la aplicación. La migración nueva `0031_capture_timestamp_precision.sql` conserva esa precisión en usuarios, animales, lotes, eventos, vínculos de observación, dosis, reacciones, incidentes/seguimientos y evaluaciones. Evita que altas consecutivas en el mismo segundo se ordenen por UUID y que la fecha retornada al crear un registro difiera de la consultada después.

No se modifica ninguna migración anterior. Las fechas existentes se conservan; las fracciones que ya se habían descartado no pueden reconstruirse. El ajuste se aplica con las migraciones de inicio de la API y no requiere borrar tablas ni alterar el control de checksum.

## Alcance pendiente

Esta validación comprueba MySQL local y una carga reproducible delimitada. La configuración real de Aiven, HTTPS, CORS de producción, disponibilidad, respaldo y restauración siguen perteneciendo a las etapas 21 y 22. El punto 15 conserva su prueba manual con importes aplazada por el usuario, aunque los repartos sí se verificaron automáticamente también con volumen. Las rectificaciones conservan el alcance delimitado del punto 18.
