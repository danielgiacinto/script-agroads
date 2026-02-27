import os
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# Funcion para normalizar texto ignorando acentos
def _normalize_text(s: str) -> str:
    n = unicodedata.normalize("NFD", s)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").lower()

from config import (
    AGROADS_BASE_URL,
    AGROADS_EMAIL,
    AGROADS_PASSWORD,
    BROWSER_USER_DATA,
    DELAY_SECONDS,
    IMAGES_FOLDER,
)
from excel_reader import read_products
from image_handler import get_images_for_product


def run(executable_path: Path, images_folder: Path):
    if getattr(sys, "frozen", False):
        browsers_path = Path(sys.executable).parent / "browsers"
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_path)
    start_time = time.time()
    products = read_products(executable_path)
    print(f"Publicando {len(products)} productos", flush=True)
    with sync_playwright() as p:
        if BROWSER_USER_DATA:
            context = p.chromium.launch_persistent_context(
                BROWSER_USER_DATA, headless=False
            )
            browser = None
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
        page.goto(f"{AGROADS_BASE_URL}/miembros/login.asp?destino=/index.asp")
        page.wait_for_load_state("domcontentloaded")

        _do_login(page)
        time.sleep(2)

        for i, product in enumerate(products):
            try:
                _publish_product(page, product, images_folder, index=i + 1, total=len(products))
            except Exception as e:
                print(f"Error publicando producto {i + 1}: {e}")
                raise
            if i < len(products) - 1:
                time.sleep(DELAY_SECONDS)

        elapsed = time.time() - start_time
        if elapsed >= 60:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"Proceso finalizado correctamente. Tiempo total: {mins} min {secs} seg", flush=True)
        else:
            print(f"Proceso finalizado correctamente. Tiempo total: {int(elapsed)} seg", flush=True)

        if browser:
            browser.close()
        else:
            context.close()


def _do_login(page: Page):
    page.get_by_placeholder("Ingrese su email").wait_for(state="visible", timeout=10000)
    page.get_by_placeholder("Ingrese su email").fill(AGROADS_EMAIL)
    page.get_by_placeholder("Ingrese su contraseña").fill(AGROADS_PASSWORD)
    page.get_by_role("button", name="Ingresar").click()
    page.wait_for_load_state("domcontentloaded")


def _publish_product(page: Page, product: dict, images_folder: Path, index: int = 1, total: int = 1):
    if "/publicacion.asp" not in page.url:
        page.get_by_role("link", name="Publicar", exact=True).click()
        page.wait_for_url("**/publicacion.asp**")
    page.wait_for_load_state("domcontentloaded")

    _select_category(page, product)
    page.wait_for_url("**paso=2**")
    page.wait_for_load_state("domcontentloaded")

    _fill_form(page, product, images_folder)

    help_el = page.locator('span.help-block').filter(has_text="código de su sistema interno")
    if help_el.count() > 0:
        help_el.first.click()
    page.wait_for_timeout(1000)
    page.locator("#publicacion-continuar").click()
    page.wait_for_url("**paso=3**", timeout=90000)
    titulo = _get(product, "titulo", "Título") or "sin título"
    print(f"Producto ({titulo}) publicado correctamente {index} de {total}", flush=True)
    page.wait_for_timeout(2000)

    page.locator('a[href*="publicacion.asp"]').filter(has_text="otro anuncio").first.click()
    page.wait_for_url("**/publicacion.asp**")
    page.wait_for_load_state("domcontentloaded")


def _select_category(page: Page, product: dict):
    categoria = _get(product, "categoria", "Categoria")
    tipo = _get(product, "tipo", "Tipo")
    sub_tipo = _get(product, "sub_tipo", "sub tipo", "Sub_tipo")
    sub_sub_tipo = _get(product, "sub_sub_tipo", "sub sub tipo", "Sub_sub_tipo")

    if categoria:
        _click_text_ignoring_accents(page, categoria)
        page.wait_for_timeout(500)
    if _click_continuar_if_visible(page):
        return
    if tipo:
        _click_text_ignoring_accents(page, tipo)
        page.wait_for_timeout(500)
    if _click_continuar_if_visible(page):
        return
    if sub_tipo:
        _click_text_ignoring_accents(page, sub_tipo)
        page.wait_for_timeout(500)
    if _click_continuar_if_visible(page):
        return
    if sub_sub_tipo:
        _click_text_ignoring_accents(page, sub_sub_tipo)
        page.wait_for_timeout(500)
    page.get_by_role("button", name="Continuar").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Continuar").click()


def _click_text_ignoring_accents(page: Page, text: str):
    def _match(a: str, b: str) -> bool:
        na, nb = _normalize_text(a), _normalize_text(b)
        if na == nb:
            return True
        short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
        return long.startswith(short)
    buttons = page.locator("button.category-button")
    for i in range(buttons.count()):
        try:
            btn = buttons.nth(i)
            name_el = btn.locator("span.category-name")
            if name_el.count() > 0 and _match(text, name_el.first.inner_text()):
                btn.click()
                return
        except Exception:
            continue
    for el in page.locator("a.ripple, a[href*='seccion.asp']").all():
        try:
            if _match(text, el.inner_text()):
                el.click()
                return
        except Exception:
            continue
    page.get_by_text(text, exact=False).first.click()


def _click_continuar_if_visible(page: Page) -> bool:
    btn = page.get_by_role("button", name="Continuar")
    try:
        btn.wait_for(state="visible", timeout=2000)
        btn.click()
        return True
    except Exception:
        return False


def _fill_titulo(page: Page, product: dict):
    val = _get(product, "titulo", "Título")
    if val:
        page.locator("#publicacion-titulo").fill(val)
        page.keyboard.press("Tab")
        page.wait_for_timeout(300)


def _fill_moneda(page: Page, product: dict):
    val = _get(product, "moneda", "Moneda")
    if not val:
        return
    v = _normalize_text(str(val))
    if v in ("peso", "pesos", "1") or v == "$":
        page.locator('label[for="publicacion-moneda-peso"]').click()
    elif v in ("dolar", "dolares", "0", "usd") or "u$d" in v:
        page.locator('label[for="publicacion-moneda-dolar"]').click()
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")
    page.wait_for_timeout(200)


def _fill_monto(page: Page, product: dict):
    val = _get(product, "monto", "Monto")
    if val is not None and str(val).strip() != "":
        page.locator("#publicacion-precio").fill(str(val).strip())


def _fill_dto_pago(page: Page, product: dict):
    val = _get(product, "dto_pago", "dto pago", "descuento")
    if val is not None and str(val).strip() != "":
        page.locator("#publicacion-descuento").fill(str(val).strip())


def _fill_condiciones_comerciales(page: Page):
    try:
        section = page.locator(".form-section:has(#publicacion-condicion-comercial-10)")
        if section.count() > 0:
            section.first.scroll_into_view_if_needed()
        page.locator("h3.section-title:has-text('Financiación')").first.click()
        page.wait_for_timeout(300)
    except Exception:
        pass

    def _click_icheck(checkbox_id: str):
        try:
            box = page.locator(f"div.icheckbox_square:has(input#{checkbox_id})").first
            if box.count() > 0:
                box.click(force=True)
                page.wait_for_timeout(200)
        except Exception:
            pass

    try:
        _click_icheck("publicacion-condicion-comercial-10")
        val10 = page.locator("#publicacion-condicion-comercial-value-10")
        if val10.count() > 0:
            val10.first.fill("6")
            page.wait_for_timeout(200)
    except Exception:
        pass
    try:
        _click_icheck("publicacion-condicion-comercial-6")
        val6 = page.locator("#publicacion-condicion-comercial-value-6")
        if val6.count() > 0:
            val6.first.fill("30")
            page.wait_for_timeout(200)
    except Exception:
        pass
    try:
        _click_icheck("publicacion-condicion-comercial-9")
        val9 = page.locator("#publicacion-condicion-comercial-value-9")
        if val9.count() > 0:
            val9.first.fill("0")
            page.wait_for_timeout(200)
    except Exception:
        pass
    try:
        _click_icheck("publicacion-condicion-comercial-4")
    except Exception:
        pass
    try:
        _click_icheck("publicacion-condicion-comercial-11")
    except Exception:
        pass
    try:
        _click_icheck("publicacion-condicion-comercial-2")
    except Exception:
        pass
    try:
        sel_principal = page.locator("#condicion-comercial-principal")
        if sel_principal.count() > 0:
            sel_principal.first.select_option(value="11")
            page.wait_for_timeout(200)
    except Exception:
        pass
    try:
        sel_secundaria = page.locator("#condicion-comercial-secundaria")
        if sel_secundaria.count() > 0:
            sel_secundaria.first.select_option(value="9")
    except Exception:
        pass


def _fill_condicion(page: Page, product: dict):
    val = _get(product, "condicion", "estado")
    if not val:
        return
    v = _normalize_text(str(val))
    radio_list = page.locator(".form-group.tipo ul.list-radio-h")
    if v in ("nuevo", "0"):
        li = radio_list.locator("li:has(label[for='publicacion-tipo-nuevo'])")
        li.scroll_into_view_if_needed()
        li.click()
    elif v in ("usado", "1"):
        li = radio_list.locator("li:has(label[for='publicacion-tipo-usado'])")
        li.scroll_into_view_if_needed()
        li.click()
    page.wait_for_timeout(200)


def _fill_marca(page: Page, product: dict):
    val = _get(product, "marca", "Marca")
    if not val:
        return
    sel = page.locator("#publicacion-marca")
    target = _normalize_text(str(val))
    for opt in sel.locator("option").all():
        try:
            txt = opt.inner_text()
            if txt and target in _normalize_text(txt):
                sel.select_option(value=opt.get_attribute("value"))
                break
        except Exception:
            continue
    page.wait_for_timeout(1000)


def _fill_anio(page: Page, product: dict):
    val = _get(product, "ano", "año", "anio", "Año")
    if not val:
        return
    page.locator("#publicacion-ano").select_option(value=str(int(val)))


def _fill_modelo(page: Page, product: dict):
    modelo_sel = page.locator("#publicacion-modelo")
    try:
        modelo_sel.wait_for(state="visible", timeout=3000)
    except Exception:
        nuevo = page.locator("#publicacion-modelo-nuevo")
        if nuevo.is_visible():
            val = _get(product, "modelo", "Modelo")
            if val:
                nuevo.fill(str(val))
        return
    page.wait_for_timeout(800)
    val = _get(product, "modelo", "Modelo")
    if val:
        target = _normalize_text(str(val))
        for opt in modelo_sel.locator("option").all():
            try:
                txt = opt.inner_text()
                if not txt or opt.get_attribute("value") == "":
                    continue
                if _normalize_text(txt) == target:
                    modelo_sel.select_option(value=opt.get_attribute("value"))
                    return
            except Exception:
                continue
        try:
            modelo_sel.select_option(label=str(val))
            return
        except Exception:
            pass
    modelo_sel.select_option(value="0")

def _fill_hp(page: Page, product: dict):
    hp_el = page.locator("#publicacion-hp")
    if hp_el.count() == 0 or not hp_el.is_visible():
        return
    val = _get(product, "hp", "HP")
    if val is not None and str(val).strip() != "":
        hp_el.fill(str(val).strip())


def _fill_horas(page: Page, product: dict):
    horas_el = page.locator("#publicacion-hs-uso")
    if horas_el.count() == 0 or not horas_el.is_visible():
        return
    val = _get(product, "horas", "Horas")
    if val is not None and str(val).strip() != "":
        horas_el.fill(str(val).strip())


def _fill_descripcion(page: Page, product: dict):
    val = _get(product, "descripcion", "Descripcion", "Descripción")
    if not val:
        return
    if page.locator("iframe#publicacion-descripcion_ifr, iframe[id*='descripcion_ifr']").count() > 0:
        page.frame_locator("iframe#publicacion-descripcion_ifr, iframe[id*='descripcion_ifr']").locator("body").fill(str(val))
        return
    desc_el = page.locator("#publicacion-descripcion, textarea[name*='descripcion']")
    if desc_el.count() > 0:
        desc_el.first.fill(str(val))


def _fill_ubicacion(page: Page, product: dict):
    val = _get(product, "ubicacion", "ubicación", "Ubicacion", "Ubicación")
    if not val or str(val).strip() == "":
        val = "Córdoba, Córdoba"
    ubic_el = page.locator("#publicacion-ubicacion")
    if ubic_el.count() > 0:
        ubic_el.first.fill(str(val).strip())
        page.wait_for_timeout(800)
        sugerencia = page.locator("ul.ui-autocomplete.ui-menu li.ui-menu-item a").first
        try:
            sugerencia.wait_for(state="visible", timeout=3000)
            sugerencia.click()
        except Exception:
            page.keyboard.press("Tab")


def _fill_form(page: Page, product: dict, images_folder: Path):
    # Llena los campos del formulario de Agroads
    _fill_titulo(page, product)
    _fill_moneda(page, product)
    _fill_monto(page, product)
    _fill_dto_pago(page, product)
    _fill_condiciones_comerciales(page)

    product_id = _get(product, "id", "ID")
    if product_id:
        imagenes = get_images_for_product(images_folder, product_id)
        if imagenes:
            _upload_images(page, imagenes)

    _fill_condicion(page, product)
    _fill_marca(page, product)
    _fill_modelo(page, product)
    _fill_anio(page, product)
    _fill_hp(page, product)
    _fill_horas(page, product)
    _fill_descripcion(page, product)
    _fill_ubicacion(page, product)

    for key, value in product.items():
        key_lower = str(key).lower().strip()
        skip = ("id", "categoria", "tipo", "sub_tipo", "sub_sub_tipo", "titulo", "moneda", "monto", "dto_pago", "condicion", "marca", "modelo", "ano", "combustible", "hp", "horas", "descripcion", "ubicacion")
        if key_lower in skip or value == "" or value is None:
            continue
        _fill_field(page, key, value)


def _fill_field(page: Page, label: str, value):
    label_str = str(label)
    val_str = str(value).strip()
    if not val_str:
        return

    try:
        inp = page.get_by_label(label_str, exact=False)
        if inp.count() > 0:
            inp.first.fill(val_str)
            return
    except Exception:
        pass

    try:
        sel = page.locator(f'select:has(option:has-text("{val_str}"))').first
        if sel.count() > 0:
            sel.select_option(label=val_str)
            return
    except Exception:
        pass

    try:
        if str(value).lower() in ("si", "sí", "true", "1", "x"):
            cb = page.get_by_label(label_str, exact=False)
            if cb.count() > 0 and cb.first.get_attribute("type") == "checkbox":
                cb.first.check()
                return
    except Exception:
        pass

    try:
        radio = page.get_by_role("radio", name=label_str)
        if radio.count() > 0:
            page.get_by_text(val_str, exact=True).click()
            return
    except Exception:
        pass


def _upload_images(page: Page, imagenes: list[Path]):
    paths = [str(p) for p in imagenes[:10]]
    if not paths:
        return
    file_input = page.locator('input[type="file"][accept*="image"]').first
    file_input.set_input_files(paths)
    page.wait_for_timeout(2000)


def _get(d: dict, *keys: str):
    for k in keys:
        v = d.get(k, d.get(k.lower(), d.get(k.upper())))
        if v not in (None, "", []):
            return str(v).strip()
    keys_norm = [_normalize_text(str(k)) for k in keys]
    for k_actual in d:
        if k_actual and _normalize_text(str(k_actual)) in keys_norm:
            v = d.get(k_actual)
            if v not in (None, "", []):
                return str(v).strip()
    return None
