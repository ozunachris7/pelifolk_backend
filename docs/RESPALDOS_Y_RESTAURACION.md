# Respaldos y restauración — punto 22

**Estado al 17/10/2026:** herramientas preparadas y simulacro local aprobado. Aiven es únicamente el entorno temporal de pruebas, según confirmó el dueño. El servidor definitivo aún no está definido: su política de respaldos se configurará y comprobará al elegirlo. No se ha leído la configuración privada de la API, exportado la base de pruebas ni restaurado encima del rancho.

## Lo que ya comprobamos

Se levantaron dos servidores MySQL 8.4.11 nuevos, solo con sockets locales y sin puertos de red: origen ficticio y destino de recuperación. Se aplicaron las 31 migraciones disponibles al realizar ese simulacro al origen y se registraron un dueño ficticio, madre/cría, pesaje, observación y caso sanitario mediante el mismo código de la API.

El simulacro exportó, comprimió y restauró el contenido. Después verificó:

- 54 tablas y sus 161 filas de muestra/catálogos/migraciones: mismos conteos y hashes del contenido de **cada tabla**, incluidos usuarios, permisos, auditoría y relaciones.
- Tres vistas presentes y consultables, una función y seis triggers presentes. Se exportaron también eventos programados; actualmente no hay ninguno.
- Reinicio del ejecutor de migraciones sin modificaciones ni diferencias de checksum.
- Login con el usuario restaurado y respuestas idénticas en animales, pesajes, observaciones, casos, historial de la cría y perfil del usuario.
- Apagado confirmado de ambos servidores temporales.

Restauración + comprobación local: 2.92 s; simulacro completo: 7.16 s. **Son mediciones de una muestra pequeña local; no constituyen tiempo de recuperación del rancho ni un compromiso de servicio.** No se probó cada módulo con datos en este simulacro; la comparación sí incluye todas las tablas, incluidas las vacías.

Evidencia de esta ejecución: `/tmp/pelifolk-recovery-mc4mtbmn/recovery-drill.json`. Los artefactos en `/tmp` son privados y temporales; este documento conserva el resumen, no una copia permanente de esa evidencia. Diez pruebas adicionales rechazaron archivos alterados, manifiestos inválidos, permisos inseguros y exportaciones incompletas.

## Repetir el simulacro sin tocar Aiven

Desde la raíz del backend y con la venv activa:

```sh
python -m scripts.validate_recovery
```

Requiere `mysqld`, `mysql` y `mysqldump` de MySQL disponibles en PATH, además de las dependencias Python. No requiere Docker, servidor externo ni credenciales del rancho. No utiliza `DATABASE_URL` ni carga `.env`. Crea sus propios datos ficticios y conserva logs, datos y reportes en carpetas privadas `/tmp/pelifolk-recovery-*`; detiene sus servidores al terminar. Los datos conservados pueden eliminarse manualmente después de revisar el reporte.

## Confirmar la protección del servidor definitivo

No es necesario cerrar un plan de producción en Aiven: se utiliza solo para pruebas. Cuando se asigne el servidor, registrar:

| Dato del entorno definitivo | Estado |
| --- | --- |
| Proveedor o equipo responsable / versión MySQL compatible | Sin definir |
| Responsable y procedimiento de respaldo | Pendiente de configurar |
| Frecuencia y retención disponibles | Pendiente de acordar |
| Último respaldo correcto y ubicación | Se comprobará en ese entorno |
| Copia independiente cifrada y custodia de clave | Pendiente de configurar |
| Restauración aislada y tiempo medido | Pendiente en ese entorno |

Si el servidor es propio, definir ejecución programada, almacenamiento, alertas y recuperación. Si es administrado, comprobar qué incluye el plan y qué debe hacer el equipo. No asumir que snapshots del equipo equivalen a una copia consistente de MySQL ni que un archivo en el mismo disco protege de perder el servidor.

Como referencia del entorno de pruebas, Aiven documenta respaldos automáticos cuya retención depende del plan; el plan Free incluye respaldos y no permite forking. Esto no determina la política del futuro servidor. Referencias: [respaldos MySQL de Aiven](https://aiven.io/docs/products/mysql/concepts/mysql-backups) y [plan Free](https://aiven.io/docs/products/mysql/concepts/mysql-free-tier).

## Crear una copia lógica independiente cuando se configure

La herramienta no toma credenciales de la API. Usa un archivo explícito del cliente MySQL con permisos privados. Exporta una base concreta, con datos, vistas, funciones, triggers y eventos; no exporta cuentas/grants administrativos del servidor MySQL. Las cuentas y permisos de **usuarios de Pelifolk** sí están en las tablas y se conservan.

Preparación manual para el entorno que se elija (no se ha ejecutado contra una base externa):

```sh
mkdir -m 700 ~/pelifolk-backups
cp deploy/backup-client.cnf.example ~/pelifolk-backups/client.cnf
chmod 600 ~/pelifolk-backups/client.cnf
```

Editar `client.cnf` con host/puerto/usuario/contraseña del servidor que se elija y ruta absoluta a su CA. La plantilla usa Aiven como ejemplo de conexión TLS; adaptar esos valores al destino definitivo. Usar `VERIFY_IDENTITY`; no desactivar TLS ni pasar contraseñas por parámetros. Escapar comillas y barras según el formato de archivos de opciones MySQL. La cuenta debe poder leer todas las tablas y los objetos programables necesarios; si falta un permiso, corregirlo sin omitir objetos para conseguir un “éxito” incompleto.

Comando de exportación (reemplazar `defaultdb` si la API usa otro nombre):

```sh
python -m scripts.backup \
  --client-file ~/pelifolk-backups/client.cnf \
  --database defaultdb \
  --output-dir ~/pelifolk-backups
```

El comando crea una carpeta nueva `pelifolk-backup-*` con:

- `database.sql.gz`: copia comprimida; **no está cifrada**.
- `manifest.json`: nombre de base, fecha UTC, versión del cliente, tamaño y SHA-256 del archivo.
- `dump.log`: diagnóstico privado de la exportación.

Una exportación con error no genera manifiesto de éxito. El SQL temporal sin comprimir se elimina al terminar. Los directorios son privados y el programa rechaza archivos de credenciales o carpetas de salida accesibles a otros usuarios. No sobrescribe respaldos anteriores ni elimina copias automáticamente.

La copia usa una transacción consistente para tablas InnoDB. No ejecutar migraciones, cambios de estructura o restauraciones simultáneamente; comprobar que las tablas de origen usan un motor transaccional. La compresión no cifra y SHA-256 detecta alteraciones accidentales, no autentica a quien produjo el archivo. La copia contiene información privada y hashes de contraseñas.

Referencia oficial: [exportación y restauración con mysqldump en Aiven](https://aiven.io/docs/products/mysql/howto/migrate-database-mysqldump).

## Verificar una copia real sin restaurarla sobre el rancho

Con una carpeta creada por la herramienta:

```sh
python -m scripts.verify_backup /RUTA/PRIVADA/pelifolk-backup-IDENTIFICADOR
```

Comprueba tamaño/SHA-256 antes de iniciar MySQL. Restaura exclusivamente en **un nuevo servidor local sin red**, con el mismo nombre de base en ese servidor separado: así las referencias de las vistas no se redirigen al origen. No acepta una URL de destino ni un host remoto y no carga la configuración de la API.

El reporte `restoration.json` incluye conteos/hashes y objetos encontrados. Un éxito significa que se importó y que sus vistas pudieron consultarse; no demuestra igualdad con la base real actual, corrección clínica de cada registro ni tiempo de recuperación en el servidor definitivo. Para una entrega real, validar además login, permisos e historiales conocidos y cotejar los registros esperados del instante del respaldo.

Usar solo copias SQL de origen conocido. Los dumps conservan los `DEFINER` de MySQL: una cuenta del proveedor ausente o permisos distintos pueden impedir funciones/vistas en la instancia nueva. El verificador debe fallar en ese caso; no elimina ni cambia definers silenciosamente. Resolver esa compatibilidad en un entorno separado con el responsable de la base, conservar la copia original y repetir la prueba antes de declararla recuperable. El simulacro local validó el definer local, no el de un proveedor externo.

Los datos restaurados y logs quedan en una carpeta privada, con el servidor detenido. El espacio requerido incluye archivo comprimido, SQL temporal y base restaurada. La verificación utiliza un MySQL de la misma rama o una versión compatible; no se ha validado una conversión a MariaDB ni una recuperación entre versiones mayores distintas.

## Conservar una copia fuera del equipo

Antes de transportarla o subirla a otro almacenamiento, cifrar el conjunto completo. Ejemplo con GPG disponible, desde la carpeta que contiene el respaldo seleccionado:

```sh
umask 077
tar -cf copia-pelifolk.tar pelifolk-backup-IDENTIFICADOR
gpg --symmetric --cipher-algo AES256 --output copia-pelifolk.tar.gpg copia-pelifolk.tar
```

GPG solicitará una frase de cifrado por su interfaz. Guardarla en un gestor de contraseñas con acceso de recuperación; no ponerla en el comando ni dentro del archivo. Conservar la copia cifrada en un segundo lugar autorizado y comprobar que se puede descargar y descifrar. La eliminación de copias locales sin cifrar queda a cargo del responsable, después de comprobar la copia externa. No se ha enviado ningún archivo a almacenamiento externo.

Para recuperar ese conjunto en una carpeta privada:

```sh
umask 077
gpg --output copia-recuperada.tar --decrypt copia-pelifolk.tar.gpg
tar -xf copia-recuperada.tar -C /CARPETA/PRIVADA/EXISTENTE
```

Después ejecutar `scripts.verify_backup` sobre la carpeta recuperada. La frase de cifrado y el archivo deben guardarse por separado.

## Rutina operativa propuesta

Cuando se configure una ubicación independiente y un equipo disponible: copia diaria y antes de migraciones, comprobar código de salida/manifiesto, verificar restauración periódica y después de cambios relevantes, conservar al menos una copia cifrada fuera del equipo. Definir retención, pérdida máxima aceptable de datos y tiempo de recuperación con el dueño; no hay un calendario o SLA activado por este cambio.

No agregar un cron todavía: faltan cuenta de backup, ruta de CA, ubicación cifrada, disponibilidad del equipo y responsable de alertas. Un portátil apagado no ejecuta respaldos y tener archivos en el mismo disco no protege de perder ese equipo.

## Para cerrar el punto 22

Cuando se conozca el servidor definitivo, completar su tabla de protección, generar una copia real autorizada, conservarla cifrada fuera del equipo y demostrar su recuperación aislada con verificaciones operativas. Por ahora queda **verificado el simulacro y preparada la herramienta; pendiente su configuración y comprobación en el destino definitivo**, no la contratación de Aiven.


## Archivos de fotos de perfil

Desde la migración 0032, `users.profile_photo_url` guarda la referencia a la foto; `upload/photos_profile` contiene los WebP. El respaldo lógico y su verificador recuperan **solo SQL**, no incluyen esos archivos. Añadir una copia cifrada del directorio/volumen `profile_photos` al procedimiento del servidor definitivo.

Para una copia conjunta, planificar un corte sin cargas/reemplazos de fotos, exportar SQL y copiar el almacenamiento de imágenes del mismo corte; conservar ambos con su fecha y verificar que las URLs restauradas tengan un archivo legible. No borrar ni vaciar el volumen para actualizar la API. La restauración aislada de SQL por sí sola no certifica recuperación de las fotos.
