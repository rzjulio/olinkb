# Auditoria Tecnica Completa del Codigo OlinKB

Fecha: 2026-04-14

## Resumen Ejecutivo

Se realizo una auditoria completa del repositorio enfocada en seguridad, autorizacion, arquitectura, rendimiento, confiabilidad, mantenibilidad y cobertura de pruebas.

Estado general:

- La base arquitectonica es razonable y la suite actual pasa completamente.
- Existen riesgos importantes en autenticacion y autorizacion.
- Hay funcionalidades de managed memory que quedaron incompletas a nivel de persistencia y filtrado.
- El viewer tiene cuellos de botella claros de escalabilidad para datasets grandes.
- La cobertura de tests valida happy paths, pero no cubre varios escenarios criticos de seguridad y permisos.

Resultado de verificacion:

- Suite ejecutada: `pytest -q`
- Resultado: `125 passed in 0.52s`

## Alcance de la Auditoria

Se revisaron principalmente estas areas:

- `src/olinkb/viewer_server.py`
- `src/olinkb/viewer.py`
- `src/olinkb/app.py`
- `src/olinkb/server.py`
- `src/olinkb/storage/postgres.py`
- `src/olinkb/storage/cache.py`
- `src/olinkb/storage/migrations/*.sql`
- `tests/*.py`

## Metodologia

La auditoria combino:

- Analisis estatico del codigo fuente.
- Verificacion directa de los hallazgos de mayor impacto.
- Revisión de las migraciones y del modelo de permisos.
- Revision del viewer y sus rutas HTTP.
- Revisión de la suite de pruebas existente.
- Ejecucion de la suite para distinguir entre fallas ya detectadas y riesgos latentes.

## Hallazgos Prioritarios

### 1. Critico: credenciales hardcodeadas y en texto plano en el viewer

Severidad: Critica

Archivos relevantes:

- `src/olinkb/viewer_server.py:27`
- `src/olinkb/viewer_server.py:541`
- `src/olinkb/viewer.py:254`
- `src/olinkb/viewer.py:258`

Evidencia:

- El viewer define un usuario `admin` con password `admin` en codigo.
- La comparacion de password es directa, en texto plano.
- La UI del viewer precompleta o sugiere esas credenciales.

Impacto:

- Acceso administrativo trivial si el viewer queda expuesto.
- Falla total de confidencialidad e integridad del flujo administrativo del viewer.
- El riesgo no es teorico: la credencial esta en codigo y la UI la delata.

Riesgo adicional:

- El login del viewer ademas provisiona al usuario como `admin` en membresias persistidas.

Recomendacion:

- Eliminar credenciales hardcodeadas.
- Pasar a credenciales configuradas externamente.
- Almacenar solo hashes fuertes de password.
- Deshabilitar el login si no existe configuracion explicita.
- Remover cualquier hint visual con credenciales por defecto.

### 2. Alto: autoaprovisionamiento de membresia de proyecto rompe el modelo de autorizacion

Severidad: Alta

Archivos relevantes:

- `src/olinkb/app.py:146`
- `src/olinkb/app.py:171`
- `src/olinkb/app.py:203`
- `src/olinkb/app.py:239`
- `src/olinkb/storage/postgres.py:230`

Evidencia:

- Las operaciones de escritura, propuesta y revisión invocan `ensure_project_member(...)`.
- Si el usuario no existe en `project_members`, la capa storage lo crea automaticamente con rol por defecto.

Impacto:

- Cualquier usuario con acceso al proceso puede terminar convirtiendose en contributor de cualquier proyecto si usa un URI del tipo `project://...`.
- El chequeo de permisos deja de validar pertenencia real y pasa a crearla.
- El sistema de revisión de convenciones y memoria de proyecto pierde aislamiento real entre proyectos.

Recomendacion:

- En rutas de autorizacion usar `get_project_member(...)`, no `ensure_project_member(...)`.
- Si la membresia no existe, negar acceso.
- Reservar `ensure_*` solo para flujos explicitos de bootstrap o administracion.

### 3. Alto: el actor puede ser falsificado via parametro `author`

Severidad: Alta

Archivos relevantes:

- `src/olinkb/server.py:88`
- `src/olinkb/server.py:117`
- `src/olinkb/server.py:145`
- `src/olinkb/server.py:177`
- `src/olinkb/app.py:59`
- `src/olinkb/app.py:171`
- `src/olinkb/app.py:203`
- `src/olinkb/app.py:239`

Evidencia:

- Las herramientas MCP exponen un campo opcional `author`.
- La app resuelve identidad como `author or self.settings.user`.

Impacto:

- Suplantacion de identidad en auditoria y trazabilidad.
- Escrituras en namespaces personales aparentando ser otro usuario.
- Contaminacion del audit log y perdida de confianza en la autoria real.

Alcance real:

- Esto es especialmente serio si el cliente MCP o la integracion que consume el server no es totalmente confiable.

Recomendacion:

- Quitar `author` del contrato MCP publico.
- Resolver el actor desde contexto del proceso o de la sesion autenticada.
- Si `author` se mantiene por compatibilidad, rechazar cualquier override que no coincida con el usuario autenticado.

### 4. Alto: managed memory incompleta a nivel de persistencia y scoping real

Severidad: Alta

Archivos relevantes:

- `src/olinkb/storage/migrations/005_add_managed_memory_support.sql:11`
- `src/olinkb/storage/postgres.py:960`
- `src/olinkb/viewer_server.py:407`
- `src/olinkb/viewer_server.py:456`

Evidencia:

- Existe la tabla `managed_memory_targets`.
- `save_memory(...)` no la pobla.
- Las consultas del viewer y de memoria no dependen de esa tabla para filtrar alcance real.
- El viewer guarda `documentation_scope` y `applicable_projects` en metadata, pero no hay enforcement relacional equivalente.

Impacto:

- El soporte de documentacion multi-repo o global queda incompleto.
- Parte del comportamiento esperado depende solo de metadata ad hoc.
- La base de datos sugiere un modelo mas fuerte que el codigo actual no implementa.

Riesgo funcional:

- Puede haber documentos que aparentan estar limitados a ciertos proyectos pero que, por diseño actual, no usan una tabla de targets efectiva para consultas y enforcement.

Recomendacion:

- Poblar `managed_memory_targets` en create y update.
- Recalcular targets cuando cambie metadata.
- Hacer que las consultas usen esa tabla como fuente de verdad.
- Agregar tests de alcance global y por proyecto.

### 5. Medio: la landing del viewer carga todo el dataset y construye todo el grafo

Severidad: Media

Archivos relevantes:

- `src/olinkb/viewer_server.py:275`
- `src/olinkb/viewer_server.py:286`
- `src/olinkb/viewer.py:116`
- `src/olinkb/viewer.py:3089`

Evidencia:

- En la vista por defecto, `_load_viewer_payload(...)` cambia el `limit` al total de memorias.
- `build_viewer_payload(...)` procesa la lista completa.
- `_build_graph(...)` genera nodos y edges para todo el conjunto cargado.

Impacto:

- Latencia creciente con el tamaño del corpus.
- Respuestas JSON mucho mas pesadas de lo necesario.
- Presion de memoria y CPU en servidor y navegador.

Importante:

- No se confirmo una complejidad cuadratica dominante en el armado del grafo.
- Si se confirmo una estrategia de carga total que no escala bien.

Recomendacion:

- Mantener paginacion real en la landing.
- Limitar el grafo a la pagina visible o a un subconjunto relevante.
- Separar metricas globales de datos detallados.

### 6. Medio: busqueda costosa por uso intensivo de `metadata::text`

Severidad: Media

Archivos relevantes:

- `src/olinkb/storage/postgres.py:733`
- `src/olinkb/storage/postgres.py:804`

Evidencia:

- Las busquedas aplican `similarity(...)` e `ILIKE` sobre `metadata::text`.
- El costo crece con el tamaño del JSON y la cantidad de terminos.

Impacto:

- Degradacion de rendimiento en datasets medianos o grandes.
- Carga innecesaria en PostgreSQL por serializacion textual de JSONB.

Recomendacion:

- Indexar campos concretos de metadata que realmente se consultan.
- Evitar trigram generalizado sobre `metadata::text` salvo necesidad fuerte.
- Considerar columnas derivadas para busqueda de alto valor.

### 7. Medio: sesiones del viewer sin expiracion ni recoleccion

Severidad: Media

Archivos relevantes:

- `src/olinkb/viewer_server.py:41`
- `src/olinkb/viewer_server.py:50`
- `src/olinkb/viewer_server.py:359`

Evidencia:

- Las sesiones se almacenan en un diccionario en memoria.
- No hay TTL, rotacion, invalidacion por tiempo ni garbage collection.

Impacto:

- Riesgo operativo en procesos largos.
- Modelo debil para entornos mas alla de desarrollo local.
- La cookie no marca `Secure`.

Recomendacion:

- Agregar expiracion por tiempo.
- Limpiar sesiones vencidas.
- Activar `Secure` si corre sobre HTTPS.
- Separar claramente el modo local de un modo mas endurecido.

### 8. Medio: invalidacion de cache demasiado amplia

Severidad: Media

Archivos relevantes:

- `src/olinkb/app.py:159`
- `src/olinkb/app.py:188`
- `src/olinkb/app.py:227`
- `src/olinkb/app.py:285`

Evidencia:

- Varias operaciones invalidan `remember:` completo.

Impacto:

- Cache thrashing innecesario.
- Menor beneficio de cache cuando crezca el volumen o el numero de usuarios.

Recomendacion:

- Invalidar por prefijos mas granulares usando scope, team, project y usuario cuando corresponda.

### 9. Medio: dependencia fuerte de `assert` para asegurar pool inicializado

Severidad: Media

Archivos relevantes:

- `src/olinkb/storage/postgres.py` en multiples metodos

Evidencia:

- Muchos metodos usan `assert self._pool is not None` despues de `connect()`.

Impacto:

- Si se ejecuta Python con optimizaciones, los `assert` desaparecen.
- La proteccion deja de existir y los fallos se vuelven menos controlados.

Recomendacion:

- Reemplazar `assert` por chequeos explicitos con excepciones claras.

## Hallazgos Secundarios

### 10. El viewer no tiene protecciones propias de endurecimiento para produccion

Observaciones:

- No hay rate limiting para login.
- No hay expiracion de sesion.
- No hay un backend real de identidad.
- El flujo esta mas cerca de un modo dev/admin tool que de un panel endurecido.

Conclusion:

- Si el viewer se usa solo localmente, el riesgo es mas acotado.
- Si se expone remotamente, hoy no esta listo.

### 11. Uso de `ensure_member(...)` y `ensure_project_member(...)` mezcla bootstrap con autorizacion

Observaciones:

- Hay una mezcla conceptual entre "crear si no existe" y "verificar permiso".
- Esa mezcla hace facil introducir bypasses como el ya detectado.

Recomendacion:

- Separar funciones de lectura de membresia de funciones de provisionamiento.

### 12. Parte de la arquitectura de documentacion administrada sugiere una direccion mas madura que aun no se completo

Observaciones:

- Las migraciones y tipos muestran una intencion valida.
- El codigo de aplicacion todavia no usa toda esa estructura.

Conclusion:

- No es un problema de diseño conceptual sino de implementacion incompleta.

## Cobertura de Tests y Gaps Detectados

La suite actual esta sana para comportamiento basico, pero faltan pruebas para escenarios criticos.

Gaps principales:

- No hay tests que impidan explicitamente la suplantacion de `author`.
- No hay tests que impidan autoalta en `project_members` durante rutas de autorizacion.
- No hay tests que validen persistencia real de `managed_memory_targets`.
- No hay tests de expiracion de sesion del viewer.
- No hay tests de endurecimiento del login del viewer.
- No hay tests de escalabilidad o comportamiento con grandes datasets en la landing del viewer.

Tests recomendados:

- `test_save_memory_rejects_author_override_when_not_authenticated_user`
- `test_project_write_requires_existing_project_membership`
- `test_proposal_review_requires_existing_project_membership`
- `test_save_memory_populates_managed_memory_targets`
- `test_update_memory_rewrites_managed_memory_targets`
- `test_viewer_default_landing_keeps_pagination`
- `test_viewer_session_expires_after_ttl`
- `test_viewer_login_disabled_without_explicit_credentials`

## Riesgos Operativos

### Riesgo de seguridad

- Alto si el viewer se expone fuera de localhost.
- Alto si el servidor MCP puede ser consumido por clientes no plenamente confiables.

### Riesgo de integridad

- Medio a alto por la falsificacion de autor y el autoaprovisionamiento de membresias.

### Riesgo de rendimiento

- Medio hoy.
- Alto si la cantidad de memorias crece y se mantiene la estrategia de carga total del viewer.

### Riesgo de mantenibilidad

- Medio.
- La base es razonable, pero hay limites difusos entre bootstrap, autorizacion y persistencia.

## Fortalezas Encontradas

- La arquitectura general no esta desordenada; app, storage y viewer estan relativamente bien separados.
- Las migraciones muestran una evolucion incremental consistente.
- La suite actual pasa completamente y cubre bastante comportamiento funcional base.
- El modelo de dominio tiene validaciones utiles para scopes y memory types.
- El viewer no expone memorias personales en su payload normal.

## Plan de Remediacion Recomendado

### Fase 1: seguridad y permisos

1. Eliminar credenciales hardcodeadas del viewer.
2. Quitar `author` del contrato MCP o bloquear overrides arbitrarios.
3. Sustituir `ensure_project_member(...)` por validacion de membresia existente en rutas protegidas.
4. Agregar tests de no regresion para estos tres puntos.

### Fase 2: managed memory

1. Persistir `managed_memory_targets` en altas y updates.
2. Usar esa tabla en consultas y enforcement.
3. Verificar comportamiento repo/global con pruebas reales.

### Fase 3: escalabilidad del viewer

1. Rehabilitar paginacion real en la landing.
2. Desacoplar metricas globales de carga detallada.
3. Construir el grafo de forma parcial o bajo demanda.

### Fase 4: rendimiento de busqueda y endurecimiento operativo

1. Revisar estrategia de busqueda sobre `metadata::text`.
2. Afinar invalidacion de cache.
3. Agregar expiracion y limpieza de sesiones del viewer.
4. Reemplazar `assert` por validaciones explicitas en storage.

## Conclusión

El proyecto no esta en mal estado general, pero hoy tiene problemas serios en tres frentes: autenticacion del viewer, autorizacion de proyecto y consistencia del modelo de managed memory.

La buena noticia es que los problemas mas importantes son corregibles sin rehacer toda la arquitectura. El mayor valor inmediato esta en endurecer identidad y permisos, y luego completar la capa de managed memory para que el modelo que ya existe en base de datos sea realmente efectivo en el runtime.