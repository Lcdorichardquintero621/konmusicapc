# KonMusic para PC

Descarga video (144p a 4K) y audio (MP3, M4A, OPUS, OGG, WAV, FLAC), biblioteca con miniaturas,
listas por carpeta (se recuerdan al cerrar) y reproductor integrado con pantalla completa.

## Obtener el programa (.exe) con GitHub
1. Crea un repositorio nuevo y sube `KonMusicPC_proyecto.zip` (Add file > Upload files).
2. Add file > Create new file, nombre `.github/workflows/build.yml`, pega el contenido de
   `KonMusicPC/.github/workflows/build.yml` y confirma.
3. En **Actions** espera la marca verde (10 a 15 min) y descarga el artefacto **KonMusic-Windows**:
   - `KonMusic_PC_portable.zip`: descomprime y abre `KonMusic.exe`.
   - `KonMusic_Setup.exe`: instalador (si se pudo generar).

## Probar desde el codigo
Instala Python 3.10+ y VLC, y ejecuta `run_windows.bat` (o `python main.py`).

## Donde guarda las cosas
- Descargas: `Videos\KonMusic` y `Music\KonMusic` de tu usuario.
- Configuracion y listas: `%APPDATA%\KonMusic`.

## Notas
- Si YouTube pide iniciar sesion, importa un `cookies.txt` desde la pestana Descargar.
- Si una plataforma deja de funcionar, usa "Actualizar motor ahora".
- Usalo solo con contenido tuyo, libre o con permiso del autor.
