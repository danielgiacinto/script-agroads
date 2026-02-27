# Script Agroads - Carga automatizada de maquinaria

Bot para publicar maquinaria agrícola en [Agroads](https://www.agroads.com.ar/) a partir de un Excel y carpetas de fotos.

## Requisitos

- Python 3.10+
- Cuenta en Agroads (el usuario debe estar logueado antes de ejecutar)

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

## Configuración

1. Copiar `.env.example` a `.env`
2. Configurar en `.env`:
   - `EXCEL_PATH`: ruta al archivo Excel (por defecto `datos.xlsx`)
   - `IMAGES_FOLDER`: carpeta base de fotos (por defecto `fotos`)
   - `DELAY_SECONDS`: segundos entre publicaciones (por defecto 10)
   - `BROWSER_USER_DATA`: (opcional) ruta a una carpeta para guardar sesión de Chrome. Si la configurás, el navegador conserva el login de Agroads entre ejecuciones.

## Estructura de datos

### Excel (`datos.xlsx`)

Las columnas deben coincidir con los labels del formulario de Agroads (orden sugerido: como aparecen en la página de arriba hacia abajo). Incluir:

- `id`: numérico, coincide con la subcarpeta en `fotos/`
- Categoría, subcategoría, sub-subcategoría
- Título, descripción, precio, moneda
- Marca, año, condición (Nuevo/Usado)
- Resto de campos del formulario según corresponda

### Fotos (`fotos/{id}/`)

Cada producto tiene una carpeta con el mismo `id` del Excel. Dentro, las imágenes a subir (jpg, png, webp, gif). Ejemplo:

```
fotos/
├── 1/
│   ├── frontal.jpg
│   └── detalle.jpg
└── 2/
    └── vista1.jpg
```

## Uso

1. Ejecutar: `python main.py`

El script abre un navegador Chromium. Si usás `BROWSER_USER_DATA`, la primera vez deberás iniciar sesión en Agroads manualmente; las ejecuciones siguientes reutilizarán la sesión. Luego el bot pulsa "Publicar", completa el formulario para cada fila del Excel y sube las fotos de cada carpeta.

## Generar ejecutable (.exe) para distribución

Para crear un ejecutable que el cliente pueda usar sin instalar Python:

1. Ejecutar: `build.bat` (o `pyinstaller agroads_bot.spec --noconfirm`)
2. La carpeta `dist/AgroadsBot/` contendrá `AgroadsBot.exe` y dependencias
3. Para entregar al cliente: comprimir esa carpeta y dentro incluir:
   - `AgroadsBot.exe` (y todos los archivos generados)
   - `.env` (con credenciales configuradas)
   - `datos.xlsx` (el Excel del cliente)
   - carpeta `fotos/` con subcarpetas `1/`, `2/`, etc.

El cliente ejecuta `AgroadsBot.exe` desde esa carpeta. La primera vez, Playwright descargará Chromium (~150 MB) automáticamente si no está instalado.
