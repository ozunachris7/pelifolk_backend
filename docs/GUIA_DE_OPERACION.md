# Guía de operación de Pelifolk

Versión del 17/10/2026. Dirigida al dueño, encargado, capturistas y responsables sanitarios del rancho. Los nombres corresponden a las pantallas actuales. Cada persona verá únicamente las secciones y acciones autorizadas para su cuenta.

Pelifolk administra **un rancho**. Aiven se utiliza temporalmente para pruebas: el servidor, dominio y respaldos definitivos se configurarán cuando se conozca la infraestructura de entrega.

## Índice

- [Inicio de sesión y accesos](#inicio-de-sesión-y-accesos)
- [Menú lateral con submenús](#menú-lateral-con-submenús)
- [Gráfica económica del Resumen](#gráfica-económica-del-resumen)
- [Distribución del hato](#distribución-del-hato)
- [Gráfica de casos sanitarios](#gráfica-de-casos-sanitarios)
- [Evolución sanitaria por mes](#evolución-sanitaria-por-mes)
- [Montas y partos por mes](#montas-y-partos-por-mes)
- [Alimentación por mes](#alimentación-por-mes)
- [Rutina de trabajo](#rutina-de-trabajo)
- [Usuarios y permisos](#usuarios-y-permisos)
- [Animales, razas y genealogía](#animales-razas-y-genealogía)
- [Lotes y ubicaciones](#lotes-y-ubicaciones)
- [Pesajes y destetes](#pesajes-y-destetes)
- [Sanidad](#sanidad)
- [Reproducción](#reproducción)
- [Alimentación](#alimentación)
- [Salidas y economía](#salidas-y-economía)
- [Historial, correcciones y auditoría](#historial-correcciones-y-auditoría)
- [Reportes y cierre de jornada](#reportes-y-cierre-de-jornada)
- [Problemas frecuentes](#problemas-frecuentes)
- [Cambio de responsable](#cambio-de-responsable)
- [Entrega al servidor definitivo](#entrega-al-servidor-definitivo)

## Inicio de sesión y accesos

1. Abrir la dirección de Pelifolk proporcionada por el responsable técnico.
2. Escribir el correo y la contraseña de la cuenta personal y pulsar **Iniciar sesión**.
3. Revisar que el menú contiene las áreas necesarias para el trabajo asignado.
4. Al terminar, utilizar **Cerrar sesión**. Cerrar únicamente una pestaña no sustituye esta acción.

Si la sesión vence, iniciar sesión nuevamente. Si aparece “Demasiados intentos”, esperar unos segundos antes de reintentar. Si el problema es de conexión, verificar con el responsable técnico que la API y la base están disponibles.

No compartir una cuenta entre trabajadores: el sistema conserva quién capturó cada registro. Para consultar tus datos y cambiar tu foto, abrir el menú de usuario de la esquina superior derecha y elegir **Mi perfil**. En **Mi perfil → Editar datos** puedes cambiar tu información personal. No existe actualmente recuperación de contraseña por correo ni cambio de contraseña propio; una persona autorizada administra las contraseñas de los demás usuarios.

### Editar tu información

1. Abrir **menú de usuario → Mi perfil → Editar datos**.
2. Corregir nombre, segundo nombre, apellido paterno, apellido materno, correo o teléfono.
3. Dejar vacíos segundo nombre o teléfono si se desea retirarlos. Nombre, apellidos y correo son obligatorios.
4. Pulsar **Guardar cambios**. **Cancelar** descarta el formulario sin guardar.
5. Comprobar los datos actualizados. Si se cambió el correo, utilizar el nuevo en el próximo inicio de sesión.

No se puede utilizar un correo que ya pertenezca a otro usuario. La foto se conserva al editar los datos. El rol y los permisos continúan administrándose desde Usuarios y Roles y permisos.

### Foto de perfil

1. Abrir **menú de usuario → Mi perfil**.
2. Pulsar **Agregar foto** o **Cambiar foto** y elegir una imagen JPEG, PNG o WebP de hasta 5 MB y 25 megapíxeles.
3. Revisar la vista previa y pulsar **Guardar foto**. **Cancelar** descarta la selección sin cambiar la foto guardada.
4. Comprobar que aparece la nueva imagen en el perfil y en el encabezado. Al reemplazarla, la anterior se elimina del almacenamiento activo.

Cada persona cambia únicamente su propia foto; no necesita administrar usuarios. Los datos personales se muestran y editan separados: nombre, segundo nombre, apellidos, correo y teléfono.

## Menú lateral con submenús

Pulsar el nombre de un grupo para desplegar sus opciones. Se mantiene un grupo abierto a la vez y se abre automáticamente el correspondiente a la pantalla actual. Solo se muestran grupos y opciones permitidos para la cuenta.

| Grupo | Opciones |
| --- | --- |
| Hato | Animales, Genealogía, Razas, Lotes, Ubicaciones |
| Operación | Pesajes (área de Manejo y destetes), Sanidad, Reproducción, Alimentación |
| Economía | Movimientos (ingresos, gastos y catálogos), Salidas |
| Administración | Usuarios, Roles y permisos, Auditoría |

Resumen y Reportes permanecen como accesos directos. En móvil, abrir **Menú**, desplegar el grupo y seleccionar el destino; desplegar un grupo no cierra el menú. Para los pasos de esta guía que mencionan Manejo, entrar por **Operación → Pesajes**; para los movimientos económicos, usar **Economía → Movimientos**.

## Gráfica económica del Resumen

En **Resumen**, debajo de las cifras económicas, se comparan los ingresos y gastos registrados por mes. Solo aparece con permiso para consultar Economía. La gráfica inicia con el mes actual y los cinco anteriores; las cifras de las tarjetas superiores siguen correspondiendo al mes actual.

Usar **3 meses**, **6 meses** o **12 meses**, o elegir **Desde** y **Hasta** y pulsar **Ver gráfica**. El rango admite hasta 24 meses y no supera hoy. Si el rango comienza o termina a mitad de mes, solo se incluyen los movimientos entre esas fechas. Los meses sin movimientos permanecen en la consulta.

Las gráficas usan Chart.js, con animación de entrada y tooltips al pasar el cursor o tocar las barras. Pulsar una pareja de barras para ver ingresos, gastos y balance de ese mes. Con Tab, enfocar la gráfica y usar las flechas izquierda/derecha para seleccionar el mes; Inicio y Fin llevan a los extremos. **Ver importes por mes** abre la tabla con los valores exactos en MXN. La gráfica se adapta al ancho de la pantalla y al modo claro u oscuro; respeta la preferencia del dispositivo de reducir movimiento. **Actualizar** del Resumen también actualiza la gráfica con sus fechas seleccionadas.

Se utiliza la fecha guardada en cada ingreso y gasto, sin limitarse a una página de resultados. No se suman los consumos calculados de alimentación o tratamientos. El balance representa los registros disponibles y no certifica utilidad final. Si no hay movimientos, se muestra un mensaje para cambiar el periodo o capturarlos en Economía.

## Distribución del hato

En **Resumen → Distribución del hato** se muestran dos comparaciones con Chart.js, disponibles para quienes pueden consultar animales:

- **Sexo de los animales activos:** hembras y machos que continúan en el hato. Los porcentajes se calculan sobre los activos; se excluyen las bajas.
- **Activos y bajas:** estado de todos los animales registrados al corte. Los porcentajes se calculan sobre el total registrado y las bajas agrupan las salidas.

Las cifras proceden del resumen completo del rancho, independientemente de la paginación del listado. **Actualizar** del Resumen actualiza ambos gráficos. El corte se indica en el encabezado; las fechas de la gráfica económica son independientes.

Pasar el cursor o tocar las barras para ver cantidades y porcentajes. Con Tab se enfoca cada gráfica y con las flechas izquierda/derecha se selecciona una categoría. **Ver cantidades por sexo** y **Ver cantidades por estado** despliegan las tablas. En móvil se muestran una debajo de otra. Si no hay animales, o no quedan activos, se informa sin inventar barras ni porcentajes.

## Gráfica de casos sanitarios

En **Resumen → Casos sanitarios por estado**, las cuentas con permiso para consultar Sanidad pueden comparar casos **abiertos** (ámbar), **en tratamiento** (azul) y **cerrados** (turquesa). Incluye todos los casos registrados, independientemente de su fecha de inicio, y usa su estado actual al corte indicado. Las fechas de la gráfica económica no filtran esta distribución.

Se cuentan casos, no animales únicos: un animal puede tener varios. Los porcentajes de la gráfica y la tabla se calculan sobre el total de casos. La tarjeta superior de casos sin cerrar sigue mostrando únicamente abiertos y en tratamiento.

Pasar el cursor o tocar las barras para ver cantidades y porcentajes; pulsarlas cambia el detalle seleccionado. También se puede enfocar la gráfica con Tab y usar las flechas izquierda/derecha. La tabla muestra los tres estados y el total. Si todavía no hay casos, se informa sin inventar barras. **Ver Sanidad** abre el módulo y **Actualizar** del Resumen vuelve a consultar los estados, incluidos los casos que se hayan cerrado o reabierto.

## Evolución sanitaria por mes

En **Resumen → Evolución sanitaria por mes**, debajo de la distribución de casos por estado, se comparan **Casos iniciados** (azul) y **Cierres vigentes** (violeta). Requiere permiso para consultar Sanidad. Cada caso se cuenta una vez por su fecha de inicio y, si actualmente está cerrado, una vez por la fecha de cierre guardada. El cierre puede corresponder a un caso iniciado antes del periodo elegido. Reabrir un caso retira su cierre de esta gráfica, aunque el historial de cambios se conserva en Sanidad. Si vuelve a cerrarse, cuenta en su nueva fecha de cierre. No representa todos los episodios históricos de cierre, una tasa de recuperación ni el saldo de casos pendientes.

Se muestran seis meses inicialmente. Usar **3 meses**, **6 meses**, **12 meses** o indicar fechas y pulsar **Ver gráfica**; se admiten hasta 24 meses, sin superar hoy. Los extremos parciales respetan las fechas exactas y los meses sin actividad siguen visibles. Estos filtros son independientes de Economía, Reproducción y Alimentación. **Actualizar** del Resumen conserva el periodo elegido y vuelve a consultar el estado de los casos.

Pasar el cursor o tocar las barras muestra un tooltip oscuro; pulsarlas o enfocarlas con Tab y usar las flechas selecciona el detalle mensual. **Ver registros por mes** muestra las cantidades exactas en tabla. Si no hay inicios ni cierres en el periodo, aparece un mensaje sin barras ficticias.

Para cargar datos de prueba directamente en la base configurada, ejecutar `python -m scripts.seed_health_trend_demo` con el entorno virtual del backend activo. Agrega 12 casos ficticios repartidos en seis meses, siete de ellos cerrados, al animal **DEMO-PESO-001**. Los motivos y notas indican **SIMULACIÓN**. No modifica casos existentes ni duplica los ejemplos al repetirlo en el mismo mes. Son datos para probar la interfaz; también aparecen en Sanidad y en los totales del Resumen.

## Montas y partos por mes

En **Resumen → Montas y partos por mes**, las cuentas con permiso para consultar Reproducción pueden comparar montas (violeta) y partos (turquesa). Inicialmente se muestran el mes actual y los cinco anteriores. Cada parto cuenta una vez, aunque tenga varias crías; se incluyen solo eventos vigentes, excluyendo registros reemplazados por rectificaciones. Una fecha rectificada mueve el registro al mes correspondiente.

Elegir **3 meses**, **6 meses** o **12 meses**, o indicar **Desde** y **Hasta** y pulsar **Ver gráfica**. Se admiten hasta 24 meses, sin fechas futuras; los extremos parciales incluyen únicamente las fechas elegidas y los meses sin actividad permanecen visibles. Este filtro es independiente del de Economía.

Pasar el cursor, tocar las barras o enfocarlas con Tab y usar las flechas permite consultar el mes seleccionado. La tabla mensual conserva los valores exactos. **Actualizar** del Resumen vuelve a consultar la gráfica conservando sus fechas. Estas cantidades representan eventos registrados; no son tasas de fertilidad ni pronósticos de partos.

## Alimentación por mes

En **Resumen → Alimentación por mes**, las cuentas con permiso para consultar Alimentación pueden ver el costo conocido (ámbar) y la cantidad consumida (azul). Se muestran seis meses inicialmente, con opciones de 3, 6 o 12 meses y fechas personalizadas de hasta 24 meses sin superar hoy. Los filtros son independientes de las otras gráficas; los meses sin registros se conservan y los extremos parciales incluyen solo las fechas elegidas.

El selector **Unidad** cambia la gráfica de cantidades entre kg, sacos, pacas u otras unidades registradas en el periodo. No se suman unidades distintas ni se convierten automáticamente. Los consumos individuales y de lotes se incluyen; un consumo de lote se cuenta una sola vez, por su cantidad completa.

Cada consumo se valora con el precio vigente en su fecha y se redondea a centavos antes de sumar, igual que en los reportes. Las cantidades sin precio sí se incluyen y se indica cuántos consumos no pudieron valorarse. Si ninguno tiene precio, se muestra la gráfica de cantidades y un mensaje en lugar de dibujar un costo conocido. Un precio de cero sí se considera conocido. Este costo no equivale a un gasto pagado y no se suma a los gastos de Economía.

Pasar el cursor o tocar una barra muestra su tooltip oscuro. Pulsarla, o enfocar la gráfica con Tab y usar las flechas, selecciona el mismo mes en ambas gráficas y muestra cantidades, costo y registros sin precio. **Ver consumos por mes** presenta todas las unidades y valores exactos en una tabla. **Actualizar** del Resumen conserva los filtros de fecha y la unidad cuando sigue disponible.

Para preparar datos ficticios en la base configurada, ejecutar `python -m scripts.seed_feeding_demo` desde el backend con su entorno virtual activo. Agrega 12 consumos en seis meses, dos alimentos identificados como **SIMULACIÓN · Gráfica alimentación** y precios ficticios, usando el animal **DEMO-PESO-001**. No altera registros existentes y no duplica los consumos al repetirlo durante el mismo mes. Estos datos son solo para visualizar y probar el sistema, no representan raciones ni precios reales. Volver a Resumen y pulsar **Actualizar** para verlos.

## Consultas extensas y formularios

Las fichas de animales, los casos y el historial sanitario, los incidentes, el historial reproductivo, los descendientes, los detalles de indicadores, los resultados económicos y los avisos y aplicaciones de programas se consultan en páginas dentro del panel. Usar **Volver al listado** para regresar conservando los filtros y la paginación. En las aplicaciones de programas, **Volver a los avisos** regresa al programa seleccionado.

Los formularios breves de alta y edición conservan su ventana modal. Desde un historial reproductivo, consultar un evento abre su detalle breve sobre el historial.

## Rutina de trabajo

| Momento | Acción | Dónde |
| --- | --- | --- |
| Inicio de jornada | Consultar resumen, revisiones clínicas, avisos sanitarios y partos próximos. | Resumen, Sanidad, Reproducción |
| Después de una actividad | Capturar el animal/destino correcto, fecha del hecho y datos comprobados. | Módulo correspondiente |
| Al aplicar una dosis | Registrar la aplicación real, aunque ya exista una pauta. | Tratamiento → Registrar dosis aplicada |
| Al mover animales | Registrar pertenencia a lote y/o traslado físico, según lo que ocurrió. | Lotes; Ubicaciones → traslados |
| Al recibir o pagar dinero | Capturar el movimiento y asignar/vincular su destino. | Economía |
| Fin de jornada | Comprobar capturas, pendientes, gastos sin atribuir y reportes necesarios. | Historial, Sanidad, Economía, Reportes |

Antes de guardar, comprobar la identidad mediante nombre y SINIIGA cuando exista. En los selectores con búsqueda, escribir parte del nombre o identificador y **seleccionar una opción**; escribir el texto sin elegir un resultado no selecciona al animal.

La fecha del hecho puede ser distinta a la fecha en que se captura. Para dosis se conserva también la hora/zona indicada. No cambiar fechas solo para conseguir que el formulario acepte un registro: revisar primero la secuencia histórica.

## Usuarios y permisos

### Crear o revisar un rol

1. Entrar en **Roles y permisos** con una cuenta autorizada.
2. Crear un rol o editar uno administrable.
3. Seleccionar las lecturas y acciones necesarias para la función de esa persona.
4. En Sanidad, seleccionar por separado las acciones de observaciones, casos, diagnósticos, tratamientos, dosis, evoluciones, productos, programas, aplicaciones de programa, reacciones e incidentes. Una acción sanitaria necesita también lectura de Sanidad.
5. Guardar y comprobar el resultado iniciando sesión con una cuenta que use ese rol.

El nombre del rol no garantiza sus permisos. Los seis perfiles de referencia están documentados en [la revisión de perfiles](REVISION_SEIS_PERFILES.md); no se aplican automáticamente a todos los roles existentes. No es posible conceder permisos que la cuenta administradora no tiene. Los roles iniciales tienen protecciones de nombre/eliminación y el rol del dueño está protegido.

El permiso de **rectificación histórica** es independiente. Dar lectura o captura de un módulo no concede por sí solo permiso para rectificarlo.

### Crear o editar un usuario

1. Entrar en **Usuarios** y abrir el formulario de creación.
2. Capturar nombre, segundo nombre si corresponde, apellido paterno, apellido materno, correo y teléfono si se tiene.
3. Establecer una contraseña de al menos ocho caracteres y seleccionar el rol preparado.
4. Crear el usuario y entregar su acceso por un medio acordado.
5. Pedirle que inicie sesión y comprobar que puede hacer su trabajo y que no ve acciones ajenas a su función.

En edición, **Nueva contraseña** vacía conserva la contraseña actual. Cambiar contraseña, rol o estado invalida las sesiones anteriores de esa cuenta; tendrá que iniciar sesión otra vez. Para retirar acceso, usar **Desactivar**: los registros históricos permanecen.

La lista de Usuarios excluye a quien está conectado. No encontrar la cuenta propia en esa lista es el comportamiento previsto. La cuenta no puede desactivarse ni cambiarse el rol a sí misma; otra cuenta con permisos suficientes debe administrar esos cambios.

## Animales, razas y genealogía

### Registrar un animal que aún no existe

1. En **Animales**, buscarlo por nombre o SINIIGA para evitar duplicados.
2. Pulsar **Registrar**.
3. Indicar nombre/identificador disponibles, sexo, fecha de nacimiento conocida y origen real.
4. Seleccionar madre y padre solamente cuando se conozcan. No usar a la pareja como padre del adulto: los padres son quienes dieron origen al animal registrado.
5. Seleccionar su composición racial. Si se capturan razas, sus porcentajes deben sumar 100. No inventar una composición para completar el formulario.
6. Marcar reproductor solo cuando corresponda y guardar.
7. Abrir **Ver ficha** y comprobar identificación, padres, razas y nacimiento.

Si el animal nació en un parto que se va a registrar, seguir [el flujo de parto y crías](#parto-y-crías), para evitar darlo de alta dos veces.

En **Razas** se consulta, crea, edita y elimina el catálogo cuando sus vínculos lo permiten. El formulario de animal conserva también la posibilidad de agregar una raza. Editar un nombre del catálogo no cambia por sí mismo los porcentajes guardados en cada animal: revisar su composición en la ficha/formulario correspondiente.

### Revisar genealogía y evaluaciones

En **Genealogía**, seleccionar un animal para consultar padres, abuelos y descendientes conocidos. Las opciones de parentesco descartan vínculos incompatibles o cíclicos; no forzar un parentesco falso para hacer aparecer una opción.

“Datos genealógicos incompletos” significa que faltan antecedentes. No demuestra ausencia de parentesco. La revisión de montas compara padres y abuelos conocidos; no descarta relaciones más lejanas.

Desde **Animales → Evaluaciones físicas**, registrar fecha, evaluador y lo observado en los apartados del formulario. Dejar “sin evaluar” lo que no se revisó. Estas evaluaciones son descriptivas; no generan una calificación genética.

En **Animales → Decisiones vigentes** se consulta la última decisión de manejo. Desde la ficha puede registrarse una decisión y su motivo. Una decisión de prever venta o descarte no ejecuta una salida ni genera un ingreso.

## Lotes y ubicaciones

Un **lote** agrupa animales para manejo; una **ubicación** indica un lugar físico. Cambiar de lote no equivale automáticamente a trasladarse a otro corral.

### Lotes

1. En **Lotes**, crear o seleccionar el grupo correspondiente.
2. Entrar en sus animales y agregar la pertenencia con su fecha de inicio real.
3. Para cambiar de lote, cerrar la pertenencia anterior y registrar la nueva sin periodos superpuestos.
4. Revisar el historial del animal/lote para comprobar fechas y miembros.

Los intervalos incluyen sus días de inicio y final. Si se cierra una pertenencia el mismo día que comienza otra, puede existir solapamiento: revisar las fechas, sin inventar un día para resolverlo. El sistema trabaja con fechas, no con horas de pertenencia.

### Ubicaciones y traslados

1. En **Ubicaciones**, preparar el lugar físico y su tipo.
2. Abrir la opción de ubicación/traslados y registrar el animal, destino y fecha reales.
3. Consultar la ficha del animal para comprobar su ubicación actual.

Los costos repartidos por lote dependen de sus miembros históricos. Una corrección de pertenencias puede cambiar consultas posteriores de reparto; conservar el motivo del cambio y revisar el periodo afectado.

## Pesajes y destetes

### Consultar la evolución del peso

Entrar en **Hato → Animales**, abrir **Ver ficha** y consultar **Evolución del peso**. Se necesita permiso de lectura de pesajes. Se muestran todos los pesajes efectivos del animal, incluidos los registrados al destete; los registros reemplazados no vuelven a contarse. **Actualizar** vuelve a cargar el historial y sus rectificaciones.

La gráfica usa las fechas reales para separar las mediciones y ajusta la escala vertical a los pesos visibles. La línea solo une los puntos registrados. Con un solo pesaje se muestra el punto y se informa que todavía no hay una evolución para comparar; sin pesajes, se muestra un mensaje.

Pasar el cursor o tocar un punto muestra su tooltip; pulsarlo permite consultar fecha, peso, responsable y notas debajo de la gráfica. Con Tab, enfocar la gráfica y usar las flechas izquierda/derecha para seleccionar pesajes; Inicio y Fin llevan a los extremos. El cambio y el promedio diario comparan con el pesaje efectivo anterior, incluso cuando este queda fuera de las fechas filtradas. Un cambio negativo se identifica como pérdida de peso registrada.

Para acotar la consulta, elegir **Desde** y/o **Hasta** y pulsar **Aplicar fechas**. **Ver todo** restaura el historial completo. **Ver mediciones del periodo** despliega los valores exactos en una tabla. La gráfica se adapta al ancho del móvil y anima sus mediciones al cargarse, salvo que el dispositivo solicite reducir movimiento. **Ir a Pesajes** abre el módulo donde se capturan las mediciones.

### Comparar pesos entre animales

Entrar en **Operación → Pesajes → Comparar pesos**. Requiere permiso para consultar Pesajes. Escribir nombre o SINIIGA en **Agregar animal** y elegir una opción; repetir para seleccionar de dos a cinco animales. Se pueden incluir animales con salida registrada para comparar su historial. No cambia los animales disponibles al registrar un pesaje nuevo, donde solo se ofrecen activos. Las etiquetas muestran el color de cada animal; **×** permite quitarlo.

Elegir **Desde** y **Hasta** y pulsar **Comparar pesos**. Inicialmente se consultan seis meses; **Todo el historial** vacía Desde y permite consultar desde el primer registro al volver a pulsar Comparar pesos. Cambiar animales o fechas retira el resultado anterior para evitar mostrar una comparación con filtros desactualizados.

La gráfica usa las fechas reales y los pesos vigentes de cada historial completo, incluidos destetes con peso y las rectificaciones efectivas. Una fecha sin medición para un animal no se convierte en cero ni se estima: el detalle muestra **Sin pesaje ese día** y la tabla un guion. Las líneas solo unen los pesajes conocidos de cada animal. No se comparan edades ni se calculan tasas de crecimiento entre animales. Los animales sin pesajes en el periodo se identifican en la leyenda; si ninguno tiene mediciones, aparece un mensaje en lugar de una gráfica.

Pasar el cursor o tocar un punto muestra su tooltip oscuro. Pulsarlo o enfocar la gráfica con Tab y usar las flechas selecciona una fecha y muestra los pesos disponibles de todos los animales. **Ver pesos por fecha** presenta los valores exactos y señala los destetes. En móvil, la tabla se desplaza dentro de su propia área.

Para cargar ejemplos directamente en la base configurada, ejecutar `python -m scripts.seed_weight_comparison_demo` con el entorno virtual del backend activo. Crea **DEMO · Comparación Brisa** (`DEMO-COMP-002`) y **DEMO · Comparación Canelo** (`DEMO-COMP-003`), con seis pesajes ficticios cada uno y notas de **SIMULACIÓN**. Seleccionar ambos y pulsar Comparar pesos; opcionalmente agregar **DEMO · Gráfica de peso** (`DEMO-PESO-001`) si ya existe. El comando no modifica animales existentes ni duplica los pesajes si se repite con el mismo plan y fecha de ejecución.

### Pesaje ordinario

1. Entrar en **Manejo** y abrir **Registrar pesaje**.
2. Seleccionar el animal, fecha y peso medido en kilogramos.
3. Agregar una nota si ayuda a interpretar la captura y guardar.
4. Consultar su historial para comprobar el dato.

Si ya existe un pesaje efectivo de ese día, revisar el registro antes de volver a capturarlo. No registrar el mismo hecho con otra fecha para eludir un duplicado.

### Destete

1. En **Manejo → Destetes**, abrir el registro de destete.
2. Elegir el animal activo elegible y capturar la fecha y peso reales del destete.
3. Guardar y verificarlo en su ficha y en la lista de destetes.
4. Consultar **Reportes → Destetes** cuando se necesite exportar el periodo.

La edad mostrada se calcula con el nacimiento conservado al registrar el destete. Si un animal no aparece, revisar si ya tiene destete, si tiene una salida o si sus fechas son incompatibles. No crear otro animal para volver a registrar el mismo destete.

## Sanidad

### Observación, caso nuevo o vínculo a un caso

Una **observación** describe lo encontrado. Un **caso** reúne su atención y seguimiento.

1. En **Sanidad**, pulsar **Observación** y guardar animal, fecha y descripción de lo observado.
2. En la pestaña **Observaciones**, localizar el hallazgo.
3. Si requiere seguimiento, pulsar **Atender hallazgo**.
4. Abrir **un caso nuevo** si es un problema independiente. Vincular **un caso existente del mismo animal** cuando el hallazgo pertenece al problema que ya se atiende.
5. Abrir **Ver caso** y comprobar **Hallazgos de origen**.

No abrir varios casos para el mismo seguimiento solo porque se capturó otra observación. Si el hallazgo ya está vinculado, aparece **Ver caso**. También se puede usar **Abrir caso** para un problema sin observación previa registrada.

### Diagnóstico, tratamiento y evolución

Dentro de **Ver caso**:

1. Revisar animal, motivo, hallazgos de origen y antecedentes.
2. Usar **Agregar diagnóstico** para registrar la valoración realizada y su gravedad.
3. Usar **Agregar tratamiento** para capturar la pauta que haya indicado el responsable sanitario: producto, dosis/unidad, vía, frecuencia, duración e inicio, según corresponda.
4. En **Evolución y revisiones**, pulsar **Registrar evolución** para registrar resultado observado y próxima revisión, si se programa.
5. En **Cambiar estado**, seleccionar el estado real y pulsar **Guardar estado**. Para cerrar, capturar su fecha de cierre. Revisar después la actividad del caso.

No llenar dosis, vías, duración o periodos con valores de ejemplo en una atención real. El sistema conserva lo capturado; no elige tratamientos ni verifica la indicación clínica por el operador.

### Registrar lo realmente aplicado

La pauta y las aplicaciones reales son registros separados.

1. Dentro del tratamiento, desplegar las dosis aplicadas.
2. Pulsar **Registrar dosis aplicada** solo después de que se haya realizado una aplicación.
3. Capturar fecha/hora y zona, cantidad, unidad, vía y quién aplicó. El capturista conectado se conserva por separado.
4. Si difiere de la pauta, registrar la explicación requerida.
5. Guardar y comprobar que aparece en la bitácora.

No registrar dosis futuras como si ya hubieran ocurrido. Una pauta guardada no genera dosis automáticamente.

### Productos, principios activos y precios

En **Sanidad → Productos**, dar de alta el producto con tipo, unidad, principios activos conocidos y días de retiro documentados para ese producto. Los principios se administran en **Principios activos** y pueden agregarse desde la composición.

El precio inicial es opcional; si se conoce, guardar importe por unidad y fecha de vigencia. Los cambios posteriores van en el historial de precios. Si no se conoce un dato de retiro o no hay respaldo para una captura anterior, revisarlo con el responsable; no asignar cero ni un número arbitrario para quitar una advertencia.

Editar hoy un producto no garantiza que se complete el periodo histórico de un tratamiento anterior. Revisar el detalle del tratamiento y su estado de retiro, en lugar de modificar repetidamente el catálogo.

### Programas y avisos

1. En **Programas y avisos**, crear el programa con producto, intervalo, edad mínima, sexo si aplica y días de aviso definidos para el manejo del rancho.
2. Revisar qué animales aparecen pendientes según los registros.
3. Registrar la pauta/aplicación de programa correspondiente cuando se realice la actividad.
4. Capturar también sus dosis efectivamente aplicadas en la bitácora disponible.
5. Volver a consultar los avisos y comprobar las fechas.

Un aviso interno no equivale a una notificación enviada por WhatsApp, correo o teléfono. Que un animal aparezca en la lista no constituye una indicación sanitaria automática.

### Retiro sanitario y revisiones

En **Sanidad → Retiro sanitario**, seleccionar el animal y abrir el detalle de tratamientos. Leer la última aplicación, los días históricos conservados y las advertencias. **Por verificar** indica que faltan datos o existe una condición que requiere revisión; no significa “liberado”. El cálculo tampoco sustituye la autorización del responsable sanitario.

En **Revisiones clínicas**, consultar casos con revisión vencida, para hoy o próxima. Abrir el caso, registrar la nueva evolución y programar la siguiente revisión si corresponde. Cerrar el caso conserva su historia y lo retira de esa agenda operativa.

### Alergias, reacciones e incidentes

- **Alergias y reacciones → Registrar reporte**: animal, fecha, descripción y agente/producto/dosis relacionados si se conocen. No confundir la asociación registrada con una causalidad confirmada.
- **Incidentes → Registrar incidente**: animal, tipo, fecha, descripción y lugar/acciones/caso cuando corresponda. Agregar seguimientos al mismo incidente; cerrar o reabrir con el motivo requerido.

Revisar antecedentes en ficha y casos antes de nuevas capturas. Cerrar un seguimiento no elimina la reacción ni descarta una alergia. “Sin reportes” significa ausencia de reportes capturados, no ausencia comprobada de problemas.

## Reproducción

### Monta y diagnóstico de gestación

1. Registrar previamente a la hembra y al macho como animales distintos, con sexo y datos conocidos correctos.
2. En **Reproducción**, seleccionar montas y pulsar **Registrar monta**.
3. Elegir hembra, macho y fecha; revisar el parentesco mostrado y cualquier dato genealógico faltante antes de guardar.
4. Cuando exista una evaluación real, pasar a diagnósticos y pulsar **Registrar diagnóstico**.
5. Capturar hembra, fecha, resultado y monta relacionada si corresponde.
6. Comprobar el historial reproductivo y **Partos próximos** cuando aplique.

Una monta no confirma gestación. Un parto estimado es una previsión basada en registros; no confirma que el parto haya ocurrido.

### Parto y crías

1. En **Reproducción**, seleccionar partos y pulsar **Registrar parto**.
2. Elegir la madre, fecha, tipo de parto y observaciones.
3. Usar **Agregar cría** para cada cría de ese parto y completar los datos solicitados, incluidos sexo, condición al nacer y peso si se midió.
4. Revisar todas las crías antes de guardar el conjunto.
5. Comprobar parto, descendientes y nuevas fichas en Animales.

No registrar primero otra ficha independiente para la misma cría si se va a crear mediante este formulario. “Vivo al nacer” y “muerte posterior” son hechos diferentes: una salida posterior no debe cambiar la condición original del nacimiento.

### Evaluaciones e indicadores

En **Evaluaciones maternas y de crías**, vincular el parto, fecha y evaluador, y describir únicamente lo observado en la madre y sus crías. No completar criterios no evaluados con una valoración favorable por defecto.

En **Desempeño de reproductores**, revisar hembras/machos y **Ver crías**; con permisos sanitarios se pueden consultar los casos de las crías. En **Indicadores reproductivos**, seleccionar corte/periodo y abrir **Detalle del cálculo** para entender qué registros entran. Sin registros para una sección puede ser un resultado válido.

Los indicadores se basan en datos capturados. No infieren fertilidad biológica, parentesco desconocido o salud de una cría sin reportes. Fechas, desconocidos y denominadores forman parte de la interpretación.

## Alimentación

### Preparar alimento y precio

1. Entrar en **Alimentación → Alimentos** y pulsar **Agregar alimento**.
2. Capturar nombre y unidad real de registro.
3. Si se conoce, agregar el precio inicial por esa unidad y su fecha de vigencia en el mismo formulario.
4. Guardar y comprobar el precio visible. Para un cambio posterior, abrir sus precios y añadir la nueva vigencia.

No cambiar de unidad como si el sistema convirtiera automáticamente kg, sacos o litros. Verificar que el precio unitario coincide con la unidad de la cantidad consumida.

### Registrar consumo

1. En consumos, pulsar **Registrar consumo**.
2. Elegir **animal o lote**, no ambos, y seleccionar el destinatario.
3. Capturar fecha, alimento y cantidad suministrada en la unidad indicada.
4. Guardar y consultar su historial.

Para calcular el costo se necesita un precio vigente en esa fecha. “Sin precio” no equivale a costo cero. El consumo del lote corresponde al grupo; su reparto calculado entre miembros es una consulta separada.

## Salidas y economía

### Registrar una salida

1. Revisar ficha, identificación, historial y retiro sanitario del animal.
2. En **Salidas**, capturar animal, fecha, tipo real y motivo/contexto solicitado.
3. Para venta o sacrificio, leer el resumen sanitario a la fecha y resolver con el responsable los datos pendientes antes de decidir la operación.
4. Guardar y comprobar el estado de la ficha.

Un aviso del sistema no sustituye la decisión del responsable ni impide necesariamente guardar. Registrar la salida no equivale a registrar que se recibió dinero.

### Venta por kilogramo

El orden es **pesaje → salida por venta → ingreso**:

1. Registrar el pesaje real del día de la salida en **Manejo**.
2. Registrar la salida por venta de ese animal en **Salidas**.
3. En **Economía → Ingresos**, registrar el ingreso, vincular esa salida y elegir **Venta por kilogramo**.
4. Seleccionar el pesaje del mismo animal y día y capturar el precio por kilogramo.
5. Revisar el importe calculado y guardar.

No crear otro ingreso para la misma venta si ya existe uno vinculado. Las ventas capturadas por importe total siguen siendo válidas; no necesitan convertirse retroactivamente a venta por peso.

### Gastos, ingresos y asignaciones

1. Preparar las categorías y proveedores necesarios en **Economía**.
2. En **Gastos**, registrar fecha, categoría, importe, proveedor si corresponde y descripción.
3. Abrir su asignación y elegir destinos animal, lote o caso sanitario con porcentajes que completen el total asignado.
4. En **Ingresos**, registrar el movimiento real y vincular animal o salida cuando corresponda.
5. Comprobar fechas/importes y después consultar costos o resultados.

Si un gasto es general y todavía no hay criterio para atribuirlo, no repartirlo arbitrariamente para quitar un pendiente. El reporte lo conserva como pendiente de atribución.

### Interpretar costos y resultado por animal

| Pantalla | Qué muestra | Cómo usarla |
| --- | --- | --- |
| Costos por animal o lote | Gastos registrados asignados y costo conocido de alimentación, separados. | Elegir tipo/destino, periodo y consultar; abrir el origen de los importes. |
| Reparto calculado de lotes | Partes por igual entre miembros históricos del lote. | Revisar miembros y fecha del movimiento; identificar periodos sin destinatarios. |
| Resultado por animal | Ingresos vinculados menos gastos registrados atribuidos, incluidos casos y partes de lote. | Seleccionar animal/estado/fechas, consultar y abrir detalle y cobertura. |
| Costo de aplicaciones | Producto realmente aplicado por su precio histórico disponible. | Consultar dosis y precios faltantes; no interpretarlo como un pago registrado. |

Los consumos y las dosis valoradas no son nuevos gastos pagados. No volver a sumarlos a una compra ya capturada. Resultado por animal se basa en registros atribuidos; no certifica utilidad final, valor del inventario ni costos no capturados.

En **Resultado por animal**, escribir y seleccionar al animal, pulsar **Consultar resultado** y revisar también **Gastos pendientes de atribuir** e **Ingresos sin animal**. Limpiar la selección permite consultar todos los animales; la cobertura de pendientes corresponde al rancho para el periodo, no solo al animal filtrado.

## Historial, correcciones y auditoría

### Encontrar un registro

1. Entrar en **Animales → Ver ficha → Historial completo**.
2. Filtrar por área y fechas y pulsar **Aplicar filtros**.
3. Revisar la fecha del hecho, el autor y el detalle. Se muestran las áreas que la cuenta puede consultar.
4. Usar **Limpiar** si un filtro oculta el registro esperado.

### Rectificar sin perder el original

1. Localizar el registro equivocado en ese historial.
2. Pulsar **Rectificar registro**, o **Ver rectificaciones** si ya tiene antecedentes.
3. Leer la explicación de lo que permite corregir esa fuente.
4. Elegir aclaración o sustitución cuando esta última esté disponible, y escribir un motivo concreto.
5. Revisar original y datos nuevos; guardar y actualizar el historial para comprobar ambos.

**Aclaración:** agrega una nota; no cambia fechas, importes, pesos ni resultados. **Sustitución:** crea un nuevo registro conservando el original; los cálculos correspondientes usan el vigente.

Actualmente se permite sustitución estructurada de pesajes ordinarios sin comprobantes asociados, observaciones sin caso vinculado y diagnósticos de casos no cerrados. Dosis, partos, destetes, ventas y otras fuentes admiten aclaración cuando corresponda, pero esa nota no corrige su efecto operativo. No registrar una operación inversa ficticia ni modificar la base directamente: entregar al responsable el registro exacto para revisar la corrección necesaria.

Si otra persona cambió el registro mientras se tenía abierto, actualizar y volver a revisar. No volver a enviar la captura sin comprobar qué quedó guardado.

### Auditoría

En **Auditoría**, filtrar el periodo/área según las opciones disponibles y consultar quién hizo los cambios y sus valores anteriores/nuevos. No todas las cuentas tienen ese permiso. La auditoría complementa al historial del animal y no sustituye los comprobantes externos del rancho.

## Reportes y cierre de jornada

1. Entrar en **Reportes** y seleccionar animales, sanidad, reproducción, economía, alimentación, pesajes o destetes según la necesidad.
2. Fijar el periodo/filtros y consultar antes de exportar a Excel.
3. Revisar corte, unidad e importes desconocidos del reporte.
4. Guardar el archivo en una carpeta autorizada, indicando periodo y propósito.

Antes de cerrar sesión, comprobar capturas importantes en la ficha/historial, pendientes sanitarios y revisiones programadas, partos próximos, y movimientos económicos sin vínculo/asignación. Un Excel exportado no es un respaldo recuperable de la base completa.

## Problemas frecuentes

| Lo que ocurre | Qué revisar y hacer |
| --- | --- |
| No aparece un menú o botón. | Confirmar permisos con quien administra el rol. Si cambiaron el acceso, iniciar sesión de nuevo para comprobarlo. |
| No aparece un animal en un selector. | Buscar nombre/SINIIGA, limpiar filtros y revisar sexo, estado, fechas y requisitos de esa operación. En la ficha comprobar si ya tiene destete/salida. |
| La búsqueda muestra texto, pero no deja guardar. | Seleccionar el resultado de la lista; escribir el nombre no basta. Revisar los campos marcados. |
| El precio/costo no se conoce. | Revisar unidad y fecha de vigencia. Conservar el dato como desconocido si falta respaldo. |
| El retiro dice “Por verificar”. | Abrir detalle y revisar dosis reales, pauta, periodo histórico y variaciones con el responsable sanitario. |
| Un registro fue rechazado como duplicado. | Buscarlo en el historial antes de repetir; no cambiar fecha/animal para evitar el control. |
| La sesión dejó de funcionar. | Puede haber vencido o haberse cambiado contraseña/rol/estado. Iniciar sesión nuevamente; si persiste, revisar la cuenta con otra persona autorizada. |
| No se puede eliminar un catálogo o rol. | Revisar si es inicial/protegido o está vinculado a registros. Conservar el historial; usar desactivación cuando la pantalla la ofrezca. |
| Se perdió la conexión al guardar. | Recuperar conexión y consultar si el registro existe antes de reenviarlo. No hay captura offline con sincronización automática. |
| Un registro cambió mientras se editaba. | Actualizar, comparar el dato vigente y decidir si aún corresponde la operación. |
| El historial está vacío. | Limpiar filtros, revisar fechas/área/permisos y confirmar identidad del animal. “Sin registros” no demuestra ausencia del hecho. |

Para reportar un problema: indicar pantalla, animal/identificador, fecha del hecho, acción realizada y mensaje visible. No enviar contraseña, token ni archivos privados de configuración. Las pruebas de captura deben hacerse en el entorno de pruebas y llevar “SIMULACIÓN” en su descripción.

## Cambio de responsable

Usar [el formato de entrega](ENTREGA_DE_RESPONSABILIDADES.md) y realizar la transición con quien entra y quien entrega.

1. Revisar casos abiertos, próximas revisiones, pautas/dosis pendientes de registrar, reacciones/incidentes, retiros por verificar, partos próximos y decisiones vigentes.
2. Entregar los registros concretos mediante nombre/SINIIGA, fechas e identificadores cuando estén disponibles; no solo una descripción verbal.
3. Revisar lotes, ubicaciones, catálogos, precios, gastos pendientes de atribuir e ingresos sin animal. Anotar por separado la información todavía desconocida.
4. Crear **una cuenta personal nueva** para quien entra y asignarle el rol aprobado. No renombrar la cuenta de quien sale para que otra persona la use: se perdería claridad sobre la identidad del autor.
5. Comprobar con esa persona el login y las acciones necesarias. Mantener al dueño con acceso a la administración durante la entrega.
6. Cuando se confirme la transición, una cuenta autorizada desactiva la cuenta saliente. Comprobar que su acceso ya no funciona; sus capturas históricas deben permanecer.
7. Entregar instrucciones de respaldo/recuperación y contacto técnico por el medio acordado; no incorporar secretos al acta.

El cambio de encargado o veterinario no implica transferir el rol de dueño. Un cambio de propietario o recuperación del único acceso administrativo necesita planificación específica; no desactivar el único acceso autorizado antes de comprobar su reemplazo.

## Entrega al servidor definitivo

El dueño y responsable técnico deberán identificar servidor, dominio, versión compatible de MySQL, acceso administrativo y ubicación de respaldos. Las instrucciones de instalación están en [Despliegue](DESPLIEGUE.md) y la prueba de recuperación en [Respaldos y restauración](RESPALDOS_Y_RESTAURACION.md).

Antes del cambio, decidir qué datos de prueba se conservan. No borrar automáticamente registros “SIMULACIÓN”, crear una base vacía ni trasladar todas las cuentas de prueba sin revisar y aprobar el conjunto de datos que se entregará. Conservar una copia recuperable previa.

En el entorno definitivo, verificar login/permisos, fichas e historiales conocidos, fechas/unidades/importes, HTTPS, conexión a la base, supervisión y una restauración aislada. No trabajar simultáneamente en dos bases distintas creyendo que son el mismo rancho. Comunicar la dirección y el momento del cambio a los usuarios por el responsable designado.

La guía documenta las funciones actuales; no incluye autoservicio de contraseña, uso offline, mensajes externos, múltiples ranchos ni otras ampliaciones que aún no se han acordado.
