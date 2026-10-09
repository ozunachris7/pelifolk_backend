# Revisión del modelo de Pelifolk

Fuente revisada: `PROYECTO APP PELIFOLK ING NIVON.docx`, ubicado en el proyecto frontend `/home/ameth-toledo/Documentos/pelifolk`. El documento es un descubrimiento de necesidades, no una especificación cerrada.

## Base de datos en inglés

`schema.sql` es la versión completa en inglés para una instalación nueva en MySQL. Incluye nombres de tablas, columnas, valores de enumeraciones, vistas, funciones y triggers en inglés. Conserva `siniiga` como identificador del sistema de identificación animal. Incorpora el modelo de autenticación que utiliza la API: `password_hash`, `token_version`, apellidos y permisos por acción.

No es una migración de `ganaderia`: no copia sus datos ni transforma sus usuarios o contraseñas. No ejecutar `auth_schema.sql` y `schema.sql` sobre la misma instalación. El esquema completo ya incluye autenticación.

La instalación automática usa `migrations/0001_initial.sql` en la base seleccionada por `DATABASE_URL`, incluso si se llama `defaultdb`. El script manual `schema.sql` selecciona `pelifolk`; es una alternativa de referencia y no se debe ejecutar antes del arranque automático. Las migraciones rechazan una base previa sin registro de versiones para evitar mezclar estructuras. No se han ejecutado contra Aiven ni contra la base existente.

### Correspondencia principal

| Original | Inglés |
| --- | --- |
| unidades / razas | units / breeds |
| tipos_ubicacion / tipos_producto | location_types / product_types |
| vias_administracion / tipos_parto | administration_routes / birth_types |
| categorias_gasto / categorias_ingreso | expense_categories / income_categories |
| principios_activos / tipos_evento | active_ingredients / event_types |
| usuarios / roles / permisos_rol_evento | users / roles / role_event_permissions |
| ubicaciones / lotes / animales | locations / animal_groups / animals |
| animal_razas / lote_animales | animal_breeds / group_animals |
| productos / producto_principios / productos_precios | products / product_ingredients / product_prices |
| programas_sanitarios / casos_sanitarios | health_programs / health_cases |
| eventos / ev_observaciones / ev_diagnosticos | events / event_observations / event_diagnoses |
| ev_tratamientos / ev_pesajes / ev_montas | event_treatments / event_weights / event_matings |
| ev_diagnosticos_gestacion / ev_partos / ev_partos_crias | event_pregnancy_diagnoses / event_births / event_birth_offspring |
| salidas / proveedores / gastos | exits / suppliers / expenses |
| gasto_imputaciones / ingresos | expense_allocations / incomes |
| alimentos / alimentos_precios / alimentaciones | feeds / feed_prices / feedings |
| auditoria | audit_logs |

## Cobertura y pendientes frente al Word

| Necesidad | Cobertura actual | Trabajo pendiente |
| --- | --- | --- |
| Seis perfiles con responsabilidades distintas | Roles y permisos de administración; tabla de permisos por evento | Implementar autorización de cada módulo; los permisos por evento no tienen asignaciones iniciales |
| Identificación, padres, abuelos y descendientes | Animales y referencias a padres; composición racial | Consultas genealógicas, validar sexo de padres, fechas y ciclos de parentesco |
| Hallazgo → diagnóstico → tratamiento | Eventos, observaciones, diagnósticos, casos y tratamientos | Vincular el hallazgo al caso; seguimiento, resultado y próxima revisión como registros con autor |
| Saber quién aplicó cada dosis y cuándo | Autor del evento y pauta del tratamiento | Separar prescripción de aplicaciones reales; una pauta no demuestra que todas las dosis se aplicaron |
| Vacunas y desparasitación pendientes | Programas sanitarios y tratamientos | Reglas de vencimiento, pendientes y avisos; datos iniciales de catálogos |
| Tiempo de retiro | Valor actual en el producto | Guardar el retiro aplicable al tratamiento y calcularlo desde las aplicaciones reales; cambiar el producto no debe cambiar el historial |
| Reproducción, partos y desempeño | Montas, diagnósticos de gestación, partos y crías | Fecha prevista de parto según regla acordada; destete, evaluaciones reproductivas y características físicas |
| Alergias y reacciones conocidas | Se pueden narrar en observaciones | Registro consultable de alergias/reacciones y vínculo con el producto o aplicación |
| Incidentes y motivos de decisiones | Texto de motivo y observaciones | Eventos explícitos de incidentes, movimientos, selección/descarte reproductivo y decisiones, con autor y fecha |
| Gastos, ingresos y rentabilidad | Gastos, imputaciones, ingresos y precios históricos | Evitar sumar dos veces alimentación/tratamientos y gasto pagado; definir distribución de costos de lote y reportes |
| Historial que no se borra ni se sobrescribe | Eventos separados y auditoría | Implementar inmutabilidad de historia; hoy el SQL permite UPDATE/DELETE y algunas relaciones tienen borrado en cascada |
| Rancho y conectividad | Un único hato; registro con conexión | Confirmar si habrá varios ranchos; no existe separación por rancho. El Word permite registrar al volver a una zona con señal |
| Indicadores generales | Tablas que permiten calcular varios indicadores | Endpoints, filtros por periodo, consultas y pantallas; todavía no están implementados |

## Problemas concretos del esquema original

1. `v_animal_actual` puede devolver varias filas por animal si hay varias salidas. La versión inglesa ahora elige la salida más reciente y desempata la ubicación más reciente.
2. El JOIN de costos de alimentación ocultaba alimentaciones sin precio vigente. La versión inglesa usa LEFT JOIN: conserva el registro y devuelve costo NULL. NULL significa costo desconocido, no cero.
3. La suma de porcentajes raciales y de imputaciones debe validarse dentro de una transacción. Los CHECK de cada fila no garantizan una suma de 100.
4. Los triggers de solapamiento de lotes no bastan ante inserciones concurrentes: el caso de uso debe bloquear el animal antes de comprobar e insertar la pertenencia. Los intervalos actuales incluyen ambos extremos; un traslado el mismo día requiere definir otra convención.
5. El documento dice tanto que la historia no se corrige como que el dueño puede modificar todo. Antes de habilitar cambios históricos, resolver esa política. `replaced_event_id` no impide modificaciones ni obliga a conservar el mismo animal o tipo de evento.
6. `end_date = start_date + duration_days` representa el límite posterior al periodo, no necesariamente la fecha de la última dosis. Definir la convención antes de usarla para avisos o retiro; no se cambió la fórmula sin esa regla.
7. Faltan validaciones cruzadas: monta de una hembra con macho distinto, gestación vinculada a la misma hembra y crías consistentes con madre y fecha del parto.
8. `alive` en una cría describe si nació viva; su estado actual debe derivarse del historial posterior, no de ese valor.
9. Los abuelos pueden obtenerse siguiendo las referencias de padres: no hace falta duplicarlos como columnas. La genealogía externa puede requerir animales de referencia no presentes en el hato.
10. No hay catálogos de negocio iniciales ni permisos iniciales para registrar eventos; tener las tablas no hace que los módulos estén listos.

## Estado del programa revisado

El backend implementa autenticación, usuarios y roles. El frontend Angular conecta login, validación de sesión al recargar, logout y las pantallas de administración de usuarios, roles y permisos con esta API. Guarda el token y su vencimiento en sessionStorage, sin guardar contraseñas. Los módulos ganaderos siguen con pantallas temporales; crear la base no implementa esas pantallas pendientes.

Login y administración de usuarios y roles están conectados. Orden recomendado para lo restante: animales e historial; sanidad y aplicaciones; reproducción y manejo; economía y reportes. Conservar nombres técnicos en inglés y textos de interfaz en español.

## Validación y límites

Esta revisión compara el Word, el SQL proporcionado, el esquema inglés y el código local. La migración inicial completa, incluyendo creación de vistas, función y triggers, se verificó en MySQL 8.4 temporal. Se probaron reinicios, conservación de datos, rechazo de una base previa sin versionado, recuperación de una migración fallida y detección de archivos modificados. No se ha aplicado a Aiven. Las pruebas HTTP del backend usan SQLite; la ejecución del SQL en MySQL no sustituye pruebas de todas las reglas de negocio de sanidad, reproducción y economía.
