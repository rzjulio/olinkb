# OlinKB Viewer

Este directorio contiene el artefacto estático de solo lectura para OlinKB.

Para exploración grande o búsqueda escalable, usa primero el visor vivo:

```bash
olinkb viewer
```

Ese modo consulta PostgreSQL en vivo y es el camino principal cuando hay muchas notas.

Genera un snapshot estático solo cuando necesites una exportación portable de punto en el tiempo:

```bash
olinkb viewer build
```

El resultado se escribe en `olinkb-viewer/index.html` con todos los datos embebidos, listo para abrir localmente o publicar en cualquier hosting estático.