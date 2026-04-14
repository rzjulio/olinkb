# OlinKB Viewer

This directory contains the read-only static artifact for OlinKB.

For large-scale exploration or scalable search, use the live viewer first:

```bash
olinkb viewer
```

That mode queries PostgreSQL live and is the main path when there are many notes.

Generate a static snapshot only when you need a portable point-in-time export:

```bash
olinkb viewer build
```

The result is written to `olinkb-viewer/index.html` with all data embedded, ready to open locally or publish on any static hosting platform.