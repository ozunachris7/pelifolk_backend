# Revisión local de los seis perfiles

Fecha: 17/10/2026. Resultado: **215 pruebas del backend y 253 del frontend aprobadas**, compilación de producción correcta y navegación de los seis perfiles revisada en Chrome a 1440 y 390 px. No se encontraron regresiones en esta batería. La revisión usa cuentas y datos aislados; no modifica usuarios, permisos ni registros de Aiven.

## Matriz utilizada

La fuente de los permisos de prueba es `tests/fixtures/profile_matrix.json`. Las asignaciones se realizan con la API protegida de Roles dentro de una base SQLite temporal. Los nombres de rol no conceden acciones por sí solos. Esta matriz es una referencia reproducible para revisar el sistema, no una política aplicada al rancho ni una certificación de responsabilidades profesionales.

| Perfil de prueba | Alcance comprobado | Restricciones comprobadas |
| --- | --- | --- |
| Dueño | Todos los permisos del catálogo, incluida rectificación histórica | No puede quitarse su propio rol ni desactivarse; historial conserva originales |
| Administrador | Módulos operativos, usuarios, roles y auditoría | Sin rectificación especial; no puede otorgarla ni modificar al dueño con permisos superiores |
| Encargado | Lecturas operativas, animales, lotes, ubicaciones, pesajes, reproducción, salidas, alimentación y economía; observaciones, casos, evoluciones e incidentes | Sin administrar accesos/auditoría ni diagnosticar, indicar tratamientos o registrar dosis |
| Trabajador | Lecturas de animales/lotes/ubicaciones/pesajes/sanidad/alimentación; observaciones, dosis, incidentes, pesajes y alimentación | Sin economía, reproducción, administración de usuarios/roles, diagnósticos, indicaciones ni apertura de casos |
| Veterinario | Acciones sanitarias; lectura de animales, pesajes y alimentación | Sin economía, accesos, auditoría, reproducción ni rectificación especial |
| Técnico pecuario | Lecturas operativas seleccionadas; reproducción, pesajes, observaciones, dosis, evoluciones y pautas de programas | Sin economía, accesos, diagnósticos, indicaciones ni apertura de casos |

Los permisos no sanitarios conservan su alcance por módulo: por ejemplo, `feeding:write` incluye alimentos, precios y consumos, y `breeding:write` incluye montas, diagnósticos de gestación y partos. La matriz no afirma una separación de esas acciones que el producto todavía no tiene. La consulta de alimentación autoriza sus costos/precios; no autoriza Economía ni los precios de medicamentos.

## Verificación de API y colaboración

`tests/test_operational_profiles.py` añade nueve pruebas de integración:

- Una matriz por cada uno de los seis perfiles: 23 consultas, 12 rutas de escritura generales y 20 rutas sanitarias. Son **330 comprobaciones de autorización de rutas**. Las escrituras de la matriz usan cuerpos vacíos para comprobar autorización y validación sin crear registros; las altas completas se prueban en el flujo compartido y la batería de cada módulo.
- Inicio de sesión, identidad/permisos vigentes y cierre de sesión por perfil. Las lecturas deben devolver 200 o 403 según la asignación; el resumen omite los datos de módulos no autorizados. Las denegaciones y cuerpos inválidos no generan auditorías de cambios.
- Flujo coordinado: encargado registra hembra/macho; trabajador observa; veterinario abre caso desde ese hallazgo, diagnostica e indica una pauta; trabajador registra la dosis simulada; técnico registra peso, monta, gestación y parto/cría; encargado registra alimentación, gasto y asignación al caso; administrador vincula un ingreso. Resultado financiero comprobado: ingreso 100 menos gasto 50, sin volver a descontar alimentación. Dosis y pautas conservan autores/roles distintos.
- Trabajador, veterinario y técnico reciben 403 al consultar Economía o costos de aplicaciones sin los permisos correspondientes. Retirar un permiso al rol afecta al token ya emitido y conserva las lecturas que siguen autorizadas.
- Dos responsables intentan guardar el estado de un caso o el seguimiento de un incidente desde la misma versión: la segunda operación se rechaza con 409 y no sobrescribe a la primera. Esto verifica control de conflictos entre sesiones, no carga simultánea de MySQL.
- Administrador no puede otorgar rectificación ni cambiar la contraseña del dueño con permisos superiores. Sí puede crear una cuenta autorizada; cambio de rol y desactivación invalidan sus sesiones anteriores, y la cuenta desactivada no puede iniciar sesión.

La batería completa del backend también verifica genealogía, destinos históricos, ventas, reparto de costos, retiros, programas, evaluaciones, reportes y rectificaciones. Resultado: **215 aprobadas**, 16 pruebas MySQL excluidas expresamente y una advertencia de dependencia de Starlette/httpx, sin fallos.

## Verificación de frontend

El archivo `src/app/shared/ui/sidebar/profile-access.spec.ts` del frontend contiene 13 pruebas nuevas: navegación por perfil, acciones sanitarias visibles y controles de acceso en los métodos de apertura, más actualización del menú al cambiar de cuenta o cerrar sesión. La matriz de prueba refleja la del backend.

Batería completa: **59 archivos y 253 pruebas aprobadas**. Compilación de producción aprobada. Revisión en Chrome con API simulada: seis perfiles en escritorio y móvil, acciones de observación/apertura de caso según la matriz y bloqueo al acceder por URL directa a Economía con trabajador, veterinario o técnico. Sin errores de ejecución, solicitudes inesperadas ni desbordamiento horizontal en las vistas verificadas.

## Reproducción

Backend, desde su repositorio y con el entorno virtual activo:

```bash
python -m pytest tests/test_operational_profiles.py -q
python -m pytest tests -q -k 'not mysql'
```

El fixture de pruebas usa SQLite temporal, configura su aplicación sin migraciones de arranque y sustituye la dependencia de base de datos. Estas órdenes no deben ejecutar los flujos contra datos reales.

Frontend, desde su repositorio:

```bash
npm test -- --watch=false --include=src/app/shared/ui/sidebar/profile-access.spec.ts
npm test -- --watch=false
npm run build
```

## Límites y siguiente paso

La revisión cubre una matriz explícita y reproducible, no una lectura de la configuración real de tus seis roles en Aiven. Los permisos que hayas elegido allí siguen siendo la autoridad para cada cuenta. El funcionamiento de la rectificación y del perfil Trabajador también fue validado manualmente por el usuario durante la sesión.

La validación posterior del **punto 20** ya se ejecutó en MySQL local aislado, con volumen y concurrencia real; sus resultados están en `docs/VALIDACION_MYSQL.md`. Quedan tres puntos obligatorios: 21 (despliegue), 22 (respaldo/restauración) y 23 (guía de operación). La prueba manual con importes del reparto de lote (15) sigue aplazada; no se da por realizada mediante esta revisión. Las sustituciones históricas conservan los límites documentados del punto 18.
