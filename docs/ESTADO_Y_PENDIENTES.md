# Estado y pendientes de Pelifolk

Revisión del código local y del documento `PROYECTO APP PELIFOLK ING NIVON.docx`, realizada el 14/10/2026. Este inventario sustituye, para planificación, las listas antiguas de pendientes en README y `database/REVIEW.md`. No certifica configuración externa de Aiven ni despliegue: esos puntos requieren verificación específica.

El Word describe necesidades y ejemplos; no es una especificación cerrada. Se separan faltantes funcionales, verificaciones para operación y ampliaciones que necesitan acuerdo. Los números identifican trabajo pendiente, no estimaciones de tamaño ni módulos completamente ausentes.

## Implementado

- Login, consulta de sesión, cierre de sesión, usuarios, roles y permisos por módulo.
- Animales, razas/composición racial, genealogía de padres/abuelos, descendientes y filtros para evitar padres descendientes o parejas conocidas.
- Lotes, pertenencias históricas, ubicaciones y traslados.
- Pesajes, crecimiento, destetes, ficha de destete, reporte Excel y promedio de destete en desempeño de reproductores.
- Observaciones, casos sanitarios, diagnósticos, tratamientos, evolución, resultado del tratamiento y revisiones clínicas.
- Productos, programas sanitarios, aplicaciones de programa y avisos internos; retiro histórico estimado a partir de la pauta registrada.
- Montas, comprobación de parentesco hasta abuelos, diagnósticos de gestación, partos/crías, partos próximos y desempeño registrado de hembras/machos.
- Salidas, ingresos vinculados a ventas, gastos, proveedores/categorías y asignación de gastos a animales/lotes/casos.
- Alimentos, precios históricos, consumos individuales/por lote y costos conocidos de alimentación.
- Resumen del rancho y reportes Excel de animales, sanidad, reproducción, economía, alimentación, pesajes y destetes.
- Decisiones por animal, auditoría de cambios, validaciones transaccionales y migraciones automáticas versionadas.

## Faltantes funcionales y funciones parciales

| ID | Pendiente | Estado actual y alcance restante |
| --- | --- | --- |
| 1 | Historial integral por animal — TERMINADO | Disponible en Animales → Ver ficha → Historial completo. Reúne registros con fechas, filtros por área, paginación y permisos por módulo; incluye contexto de lote y atribuciones económicas sin inventar consumos individuales. Ver README para límites de las fuentes históricas. |
| 2 | Observación vinculada al caso sanitario | Se conserva la observación, pero no existe vínculo explícito con el caso que origina. Conservar la secuencia hallazgo → caso → diagnóstico → tratamiento. |
| 3 | Aplicaciones reales de cada dosis | El tratamiento guarda pauta, fecha inicial y autor. Registrar cada administración con fecha/hora, dosis y responsable, diferenciándola de la indicación. Las aplicaciones de programa existentes son registros de tratamiento, no una bitácora de todas las dosis de una pauta. |
| 4 | Retiro basado en la última aplicación real | Ya existe retiro histórico estimado desde la duración registrada. Integrarlo con la última administración real del punto 3 y conservar datos desconocidos explícitamente. |
| 5 | Alergias y reacciones adversas | Hoy pueden narrarse en observaciones. Crear registros consultables y visibles, vinculados al producto o aplicación cuando se conozca. |
| 6 | Incidentes extraordinarios estructurados | Observaciones, tipos de parto y salidas cubren parte de los hechos. Falta clasificación/seguimiento específico de accidentes, abortos, ataques, intoxicaciones, desapariciones y otros incidentes, sin perder autor ni fecha. |
| 7 | Conformación y características físicas | Existen pesos y composición racial; faltan evaluaciones físicas con criterios, fecha, observaciones y evaluador. Definir los criterios antes de puntuarlos. |
| 8 | Habilidad materna y calidad de descendientes | Existen partos, cantidades y pesos. Faltan evaluaciones explícitas de habilidad materna, calidad y características observadas/heredadas, con criterios acordados. |
| 9 | Indicadores reproductivos complementarios | El desempeño muestra hechos registrados; faltan intervalos entre partos/gestaciones y tasas de fertilidad/supervivencia con períodos, denominadores y reglas definidos. No inferir genética o concepción a partir de una monta. |
| 10 | Salud de las crías en desempeño | Los casos sanitarios existen por animal. Integrar problemas sanitarios de descendientes en la evaluación de sus progenitores, controlando permisos y evitando interpretar el simple conteo como causa hereditaria. |
| 11 | Consulta global de candidatos a venta o conservación | Existen decisiones individuales y estado del animal. Falta una vista de decisiones vigentes/candidatos, con contexto de salud, reproducción y retiro; definir cómo se sustituye una decisión anterior. |
| 12 | Venta por peso y peso de salida vinculado | La venta y su ingreso existen; los pesajes son independientes. Registrar la medición asociada a la salida y, cuando la venta sea por kg, peso, precio unitario y cálculo del importe. |
| 13 | Principios activos de productos | Las tablas de ingredientes están en el SQL original/inglés, pero no están expuestas como catálogo y composición de productos en el flujo actual. |
| 14 | Precios históricos de productos y costo sanitario | Alimentación ya tiene precios. Falta exponer precios de medicamentos/productos y valorar consumos/aplicaciones sanitarias, diferenciando costo estimado de gasto pagado. |
| 15 | Distribución de costos de lote entre animales | Se asignan gastos a lotes y se captura alimentación del lote completo. Falta un criterio de reparto por miembros/permanencia u otra regla acordada; hoy no se atribuyen automáticamente esos importes a cada animal. |
| 16 | Rentabilidad individual y costo integral de producción | Ya hay balance financiero y gastos atribuidos. Completar vinculación de ingresos/costos por animal, gastos generales y compras/consumos para obtener resultados integrales sin duplicar alimentación o medicamentos. Definir las reglas contables de la valoración. |
| 17 | Permisos por acción dentro de los módulos | Los roles y permisos por módulo funcionan. `health:write` permite observaciones, diagnósticos y tratamientos; falta distinguir esas acciones para reflejar las responsabilidades del trabajador, técnico y veterinario. |
| 18 | Rectificación histórica sin sobrescribir hechos | Muchos registros son inmutables desde la API y existe auditoría. Falta un flujo de aclaración/sustitución para errores históricos, con vínculo, motivo y permisos. Resolver la contradicción del Word entre historia que no se modifica y dueño que puede modificar todo. No implica habilitar borrado de historia. |

## Verificaciones y preparación antes de operación diaria

Estos puntos no significan que no existan pruebas o medidas parciales. El sistema ya cuenta con pruebas automatizadas y verificaciones de varios flujos.

| ID | Pendiente | Alcance |
| --- | --- | --- |
| 19 | Revisión integral con los seis perfiles | Comprobar navegación, lecturas/escrituras permitidas y denegadas, concurrencia y flujos completos con varios usuarios. Repetir después del cambio de permisos por acción. |
| 20 | Validación integral en MySQL y con volumen representativo | Hay pruebas SQLite y pruebas MySQL de partes del sistema. Verificar todos los flujos, triggers, migraciones, concurrencia, consultas/paginación y rendimiento con datos de un hato grande. Utilizar una base de pruebas, no datos reales para pruebas destructivas. |
| 21 | Preparación/verificación de despliegue | Dominio, HTTPS, configuración de producción, restricciones de CORS, límites de intentos de login y supervisión de errores/disponibilidad. La configuración externa no se auditó en esta revisión. |
| 22 | Respaldo y restauración verificados | Comprobar la política real de Aiven, retención y restauración; no suponer que no hay respaldos. Probar recuperación en un entorno separado. |
| 23 | Guía de operación y cambio de responsables | Documentar capturas, roles, cierre de casos, rectificaciones y entrega del historial a otro encargado/veterinario. La documentación técnica existente no sustituye una guía de uso integral. |

## Ampliaciones por acordar y menciones del Word por concretar

No se incluyen como requisitos cerrados ya autorizados para implementación.

| ID | Ampliación | Distinción de alcance |
| --- | --- | --- |
| 24 | Captura masiva de pesajes y tratamientos | Mejora para reducir carga administrativa. Lotes ya admite operaciones de pertenencia de varios animales; no falta todo el manejo por lote. |
| 25 | Captura sin internet y sincronización | No existe modo offline. El Word admite esperar a recuperar señal; sincronizar capturas offline es una ampliación que requiere reglas de conflictos/duplicados. |
| 26 | Notificaciones fuera de la aplicación | Ya existen avisos sanitarios, revisiones y partos próximos dentro del sistema. Push/correo/WhatsApp requieren definir canal, destinatarios y servicio. |
| 27 | Recuperación de contraseña y perfil propio | Un administrador puede cambiar contraseñas de otros usuarios. Falta autoservicio para recuperar la cuenta y editar el propio perfil/contraseña. |
| 28 | Renovación de sesión | Actualmente un token vencido exige iniciar sesión nuevamente. Refresh tokens y gestión de sesiones son una mejora por acordar. |
| 29 | Indicadores ambientales | El Word menciona agua, residuos y uso del suelo; faltan criterios, unidades, captura y reportes. No hay una especificación operativa de este módulo. |
| 30 | Organización social/laboral | El Word menciona condiciones y organización del trabajo; definir tareas/responsables y datos concretos antes de construir pantallas. Roles de acceso ya existen. |
| 31 | Varios ranchos | El sistema actual opera para un solo rancho. La separación por rancho requeriría ampliar el alcance; el documento no exige operar múltiples ranchos. |

## Orden recomendado

1. Historial integral (1): terminado. El siguiente desarrollo es el vínculo entre observación y caso sanitario (2).
2. Cadena sanitaria, aplicaciones reales, retiro y reacciones (2–5).
3. Incidentes y evaluaciones productivas/reproductivas (6–10).
4. Consulta de decisiones, venta y costo integral (11–16).
5. Permisos por acción y rectificaciones, coordinados con las capturas anteriores (17–18).
6. Verificación operativa y preparación de producción (19–23).
7. Elegir cuáles ampliaciones de 24–31 entran en una versión posterior.

Actualizar esta lista cuando se termine un punto o cambie el alcance. No presentar tareas ya implementadas como pendientes a partir de documentos antiguos.
