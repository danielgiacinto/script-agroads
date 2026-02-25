from pathlib import Path

EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def get_images_for_product(images_folder: Path, product_id: str | int) -> list[Path]:
    folder = images_folder / str(product_id)
    if not folder.is_dir():
        return []
    imagenes = []
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.suffix.lower() in EXTENSIONES:
            imagenes.append(f)
    return imagenes
