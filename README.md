# Script Agroads - Carga automatizada de maquinaria

Bot para publicar maquinaria agrícola en [Agroads](https://www.agroads.com.ar/) a partir de un Excel y carpetas de fotos.

## Requisitos

- Python 3.10+
- Cuenta en Agroads

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

## Configuración

1. Copiar `.env.example` a `.env`
2. Configurar en `.env`:
   - `AGROADS_EMAIL`: email para ingresar en Agroads
   - `AGROADS_PASSWORD`: contraseña
   - `EXCEL_PATH`: ruta al archivo Excel (por defecto `datos.xlsx`)
   - `IMAGES_FOLDER`: carpeta base de fotos (por defecto `fotos`)
   - `DELAY_SECONDS`: segundos entre publicaciones (por defecto 5)
   - `BROWSER_USER_DATA`: (opcional) ruta a una carpeta para guardar sesión de Chrome. Si la configurás, el navegador conserva cookies y login entre ejecuciones.
   - `AGROADS_BASE_URL`: (opcional) URL base del sitio (por defecto `https://www.agroads.com.ar`)

## Estructura de datos

### Excel (`datos.xlsx`)

Las columnas deben coincidir con los labels del formulario de Agroads (orden sugerido: como aparecen en la página de arriba hacia abajo). Incluir:

- `id`: numérico, coincide con la subcarpeta en `fotos/`
- Categoría, subcategoría, sub-subcategoría
- Título, descripción, precio, moneda
- Marca, año, modelo, condición (Nuevo/Usado)
- HP, combustible, horas de uso (según categoría)
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

El script abre un navegador Chromium, inicia sesión en Agroads con las credenciales del `.env`, navega a Publicar y para cada fila del Excel:

1. Selecciona categoría y subcategorías según el Excel
2. Completa el formulario (título, precio, moneda, marca, año, modelo, descripción, condiciones comerciales, etc.)
3. Sube las fotos de la carpeta correspondiente
4. Espera a que todas las fotos terminen de subir (100%, confirmación del servidor) y aguarda unos segundos extra antes de continuar
5. Pulsa "Publicar", espera la redirección a paso 3 y vuelve automáticamente a la pantalla para cargar el siguiente anuncio

Entre cada publicación hay una pausa configurable con `DELAY_SECONDS`. Si usás `BROWSER_USER_DATA`, la sesión se reutiliza entre ejecuciones.

## Generar ejecutable (.exe) para distribución

Para crear un ejecutable que el cliente pueda usar sin instalar Python:

1. Ejecutar: `build.bat` (o `pyinstaller agroads_bot.spec --noconfirm`)
2. La carpeta `dist/AgroadsBot/` contendrá `AgroadsBot.exe` y dependencias
3. Para entregar al cliente: comprimir esa carpeta e incluir:
   - `AgroadsBot.exe` y todos los archivos generados
   - `.env` con credenciales y rutas configuradas
   - `datos.xlsx`
   - carpeta `fotos/` con subcarpetas `1/`, `2/`, etc.

El cliente ejecuta `AgroadsBot.exe` desde esa carpeta. La primera vez, Playwright descargará Chromium (~150 MB) automáticamente si no está instalado.
