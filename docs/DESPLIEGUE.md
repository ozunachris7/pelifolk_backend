# Preparación de despliegue — punto 21

Estado al 17/10/2026: **preparado y validado localmente; publicación pendiente porque todavía no hay servidor ni dominio**. Aiven se usa solo para pruebas; no se requiere conservarlo en producción. No se ha consultado ni modificado ese servicio. No se ha solicitado un certificado público. No hay nuevas migraciones en este punto.

## Arquitectura preparada

Internet → Caddy (80/443 y HTTPS automático) → Nginx (frontend Angular y límite de login) → API FastAPI (8000 privado) → MySQL compatible en el servidor/proveedor que se asigne, con conexión protegida. Las plantillas actuales usan la conexión TLS de Aiven como ejemplo; deberán adaptarse al destino elegido.

Solo Caddy publica puertos. No abrir 8000 ni 8080 en el servidor. La API confía en el salto privado de Nginx, que reemplaza las cabeceras de IP y protocolo; así las redirecciones conservan HTTPS. No reutilizar el comando del contenedor exponiendo directamente la API. El frontend compilado para producción usa `/api/v1` del mismo dominio; `npm start` conserva `http://localhost:8000/api/v1`. `CORS_ORIGINS=[]` es correcto para esta instalación del mismo origen. Para separar dominios, adaptar frontend y registrar únicamente orígenes HTTPS exactos en CORS.

La API arranca con dos procesos, ejecuta las migraciones existentes bajo su bloqueo y rechaza checksums modificados. Usa un usuario de contenedor sin privilegios, sistema de archivos de solo lectura y dependencias fijadas. Se añadieron al archivo de versiones `openpyxl` y `et_xmlfile`, ya utilizados por los reportes. Swagger/OpenAPI se deshabilitan con `ENVIRONMENT=production`; en desarrollo permanecen disponibles.

## Archivos que se prepararán en el servidor

Desde la raíz del backend:

```sh
cp deploy/production.env.example deploy/production.env
cp deploy/stack.env.example deploy/stack.env
chmod 600 deploy/production.env deploy/stack.env
```

Editar las copias, nunca las plantillas:

- `deploy/stack.env`: dominio real sin protocolo ni ruta y correo para certificados.
- `deploy/production.env`: URL MySQL del destino y `JWT_SECRET` aleatorio. Conservar `ENVIRONMENT=production`, `CORS_ORIGINS=[]` y los parámetros TLS/timeouts de la plantilla. Codificar los caracteres especiales de usuario/contraseña en la URL. No reutilizar las credenciales de ejemplo.
- Obtener la CA del servidor MySQL elegido y guardarla en `deploy/aiven-ca.pem` (nombre de ejemplo usado por la plantilla), legible para el UID 10001. Es una CA pública, no una llave privada. No desactivar `ssl_check_hostname` ni sustituir la CA por un archivo vacío.

Generar un secreto nuevo:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

No enviar archivos de configuración reales, tokens o contraseñas a capturas, repositorios o registros públicos. Estas rutas y la carpeta de compilación se excluyen de Git. La imagen usa una lista explícita de archivos y no incorpora `.env`, Git ni documentos privados.

## Compilar el frontend y copiarlo

En el proyecto frontend:

```sh
npm ci
npm run build
```

Copiar **el contenido** de `dist/pelifolk/browser/` a `deploy/frontend/` del backend en el servidor. Debe existir `deploy/frontend/index.html`, no una carpeta `browser` anidada. Si se transporta entre equipos, usar un archivo de distribución o una copia por SSH.

## Publicación cuando exista servidor

Servidor con Docker Engine/Compose, DNS A/AAAA apuntando correctamente y puertos 80/443 accesibles. Si no existe conectividad IPv6, no publicar un AAAA incorrecto. El esquema preparado recibe tráfico directamente: no activar un CDN/proxy adicional sin revisar confianza de IP y certificados.

Desde el backend del servidor, después de preparar todos los archivos:

```sh
docker compose --env-file deploy/stack.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/stack.env -f deploy/compose.yaml build
docker compose --env-file deploy/stack.env -f deploy/compose.yaml up -d
docker compose --env-file deploy/stack.env -f deploy/compose.yaml ps
```

El proxy web espera que la API esté lista. Caddy obtiene y renueva HTTPS automáticamente para el dominio configurado si DNS y conectividad lo permiten. Sus certificados se conservan en volúmenes. No ejecutar `down -v` como procedimiento de actualización. Antes de una actualización con migraciones, completar el respaldo/restauración del punto 22. Una versión anterior del código no implica que sea seguro revertir una migración aplicada.

En una actualización, repetir compilación/copia del frontend y `up -d --build`. Nginx vuelve a resolver el servicio API mediante el DNS de Docker. Revisar disponibilidad y errores antes de dar la actualización por terminada.

Si faltan usuarios, el bootstrap protegido continúa disponible; si ya hay usuarios no crear otro dueño mediante el bootstrap. No se agregan cuentas, contraseñas o permisos de prueba al desplegar.

## Comprobaciones y supervisión

- `https://DOMINIO/health/live`: proceso HTTP responde, sin consultar la BD.
- `https://DOMINIO/health/ready`: consulta `SELECT 1`; responde 200 `{"status":"ready"}` o 503 genérico si falla la conexión. No certifica cada módulo ni la política de respaldos.
- Navegar a login y una ruta interna después de recargar. Iniciar sesión con una cuenta autorizada y comprobar sus permisos.
- Verificar que no hay solicitudes a `localhost:8000` desde el navegador publicado y que `/docs`, `/redoc` y `/openapi.json` no se exponen en la API de producción.

Chequeo de disponibilidad para un programador externo al servidor (salida JSON, código 0 disponible / 1 no disponible; HTTPS y certificados verificados):

```sh
python -m scripts.check_availability https://DOMINIO
```

Programarlo cada minuto desde otro equipo o servicio de supervisión. Una ejecución manual no constituye supervisión continua: todavía falta elegir el servicio y destinatario de alertas cuando exista infraestructura. El healthcheck de Docker marca la API `unhealthy`; `restart: unless-stopped` reinicia procesos que terminan, **no** contenedores que solo cambian a `unhealthy`.

Consultar registros locales:

```sh
docker compose --env-file deploy/stack.env -f deploy/compose.yaml logs --tail=100 api web https
```

Nginx registra fecha, identificador de solicitud, estado, duración y estado del servicio API; no guarda cuerpos, query strings, correos, contraseñas ni tokens. Devuelve `X-Request-ID` para correlación. Los logs Docker rotan a 10 MB × 3 archivos por servicio. Los errores inesperados de API quedan en los logs del servidor; revisar su contenido antes de compartirlo. No se ha conectado un servicio externo de errores ni un canal de alertas.

## Límite de login

Nginx limita por IP del cliente: 5 solicitudes por minuto con ráfaga de 5 adicionales. Devuelve 429 JSON, `Retry-After: 12` y `Cache-Control: no-store` al excederlo. Cuenta tanto intentos válidos como inválidos y se comparte entre procesos de Nginx/API en este único despliegue. No bloquea una cuenta por su correo. Personas detrás de una misma IP comparten el límite.

Caddy sobrescribe la cabecera interna de IP, por lo que el navegador no puede evadir el límite falsificándola. Este control depende de mantener privados Nginx y la API; una ejecución directa con `uvicorn --reload` no incorpora el límite. Varias réplicas independientes de Nginx necesitarían un control compartido adicional. Las API protegidas siguen comprobando JWT, estado, versión de sesión y permisos en cada solicitud.

## Validación local realizada

- Imagen Docker construida desde cero con dependencias instaladas; importación real como UID 10001, sin red y con filesystem de solo lectura. No se probó un arranque de producción contra Aiven.
- Compose validado con plantillas, sin secretos reales.
- 22 pruebas backend aprobadas: configuración, docs deshabilitadas, disponibilidad/BD fallida, login y monitor con respuestas/red simuladas.
- 253 pruebas frontend aprobadas; después se amplió el flujo de login para comprobar el aviso de límite 429 y sus 5 pruebas volvieron a pasar. Compilación de producción y Chrome con login simulado al mismo origen aprobados.
- Caddy + Nginx + API ficticia en red Docker temporal: 6 respuestas 401 seguidas de 6 respuestas 429 en una ráfaga; cabeceras falsas no evaden el control; JSON/Retry-After/no-store comprobados; disponibilidad y rutas SPA correctas. Configuración HTTPS adaptada/validada sin solicitar certificados.

Repetir la prueba aislada de proxies:

```sh
python -m scripts.validate_deployment
```

Requiere Docker; puede descargar imágenes oficiales. Crea exclusivamente sus contenedores/red temporales y los elimina al terminar. Usa una API y un HTML ficticios: no arranca el programa real ni usa Aiven. Para validar Compose sin archivos privados:

```sh
PELIFOLK_API_ENV=production.env.example docker compose --env-file deploy/stack.env.example -f deploy/compose.yaml config --quiet
```

Las imágenes base tienen etiquetas versionadas por rama (`python:3.14-slim`, `nginx:alpine`, `caddy:2-alpine`). Al preparar una publicación definitiva, registrar/preservar los digests de las imágenes validadas. Reconstrucciones futuras pueden incorporar actualizaciones de esas ramas.

Referencias de configuración: [proxy de Caddy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy), [HTTPS de Caddy](https://caddyserver.com/docs/quick-starts/reverse-proxy), [límites de Nginx](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html).

## Para cerrar el punto 21

Cuando exista servidor: registrar dominio/destino, publicar, comprobar TLS público y redirección HTTP, confirmar la conexión protegida al MySQL definitivo y los datos migrados, probar login/permisos desde fuera del servidor y activar un monitor externo con alertas comprobadas. Hasta entonces el punto queda **preparado, no publicado ni verificado externamente**.


## Fotos de perfil persistentes

La API guarda fotos en `upload/photos_profile`; Compose monta el volumen `profile_photos` sobre `/app/upload/photos_profile`, escribible por el UID 10001 de la imagen. Conservarlo entre actualizaciones y no ejecutar `down -v` sobre una instalación con datos. Nginx enruta `/upload/photos_profile/` a la API; las URLs son públicas.

Al mover la instalación, respaldar/restaurar también este directorio o volumen junto con el dump MySQL. Planificar un corte sin cambios de foto para que las referencias SQL y archivos correspondan al mismo instante. Restaurar solo la BD deja URLs sin archivo; conservar solo las fotos no recupera usuarios ni otros registros. En un servidor sin Docker, dar al proceso API permisos de escritura sobre el directorio elegido mediante `PROFILE_PHOTOS_DIR`.
