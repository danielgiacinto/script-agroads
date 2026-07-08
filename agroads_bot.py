import os
import re
import sys
import time
import unicodedata
from pathlib import Path

from playwright.sync_api import Page, sync_playwright, TimeoutError as PlaywrightTimeout

# Funcion para normalizar texto ignorando acentos
def _normalize_text(s: str) -> str:
    n = unicodedata.normalize("NFD", s)
    return "".join(c for c in n if unicodedata.category(c) != "Mn").lower()


def _normalize_modelo(s: str) -> str:
    t = str(s).strip()
    for c in ("›", "»", "‹", "«"):
        t = t.replace(c, ">")
    for c in ("–", "—", "−", "‑", "‒", "﹘", "﹣", "－"):
        t = t.replace(c, "-")
    t = t.replace("-", " ")
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return _normalize_text(t)

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

_CATEGORY_ALIASES: dict[str, list[str]] = {
    "elevdores": ["Elevadores", "Elevdores"],
}

MIN_ESPERA_TRAS_FOTOS_SEG = 15
FOTOS_POLL_MS = 1000
FOTOS_TIMEOUT_SEG = 600


def _page_en_error_red(page: Page) -> bool:
    return "chrome-error://" in page.url or page.url.startswith("about:")


def _recuperar_si_error_red(page: Page, url_fallback: str) -> None:
    if _page_en_error_red(page):
        page.goto(url_fallback, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_load_state("domcontentloaded")


def _cantidad_fotos_esperadas(product: dict, images_folder: Path) -> int:
    product_id = _get(product, "id", "ID")
    if not product_id:
        return 0
    imagenes = get_images_for_product(images_folder, product_id)
    return min(len(imagenes), 10) if imagenes else 0


def _estado_fotos_subida(page: Page) -> dict:
    return page.evaluate(
        """
        () => {
          const items = Array.from(document.querySelectorAll('ul.ui-sortable li.imagen'));
          let listas = 0;
          let enCarga = 0;
          for (const li of items) {
            const fotoCargando = li.querySelector('.foto-cargando');
            const ok = li.querySelector('.foto-ok.imagen-sube');
            const pct = fotoCargando && fotoCargando.querySelector('.porcentaje');
            const inputNueva = li.querySelector('input[name$="-nueva"]');
            const cargandoVisible = fotoCargando && getComputedStyle(fotoCargando).display !== 'none';
            const pctText = pct ? pct.textContent.trim() : '';
            if (cargandoVisible || (pctText && pctText !== '100%')) {
              enCarga++;
              continue;
            }
            if (!ok || getComputedStyle(ok).display === 'none') {
              enCarga++;
              continue;
            }
            if (inputNueva && inputNueva.value === 'si') {
              enCarga++;
              continue;
            }
            listas++;
          }
          return { total: items.length, listas, en_carga: enCarga };
        }
        """
    )


def _esperar_fotos_listas(
    page: Page,
    cantidad_esperada: int,
    index: int,
    total: int,
    timeout_seg: int = FOTOS_TIMEOUT_SEG,
) -> None:
    if cantidad_esperada <= 0:
        return

    print(
        f"[{index}/{total}] Esperando subida de {cantidad_esperada} foto(s)...",
        flush=True,
    )
    inicio = time.time()
    ultimo_log = -1
    ultimo_log_tiempo = 0.0

    while time.time() - inicio < timeout_seg:
        estado = _estado_fotos_subida(page)
        listas = int(estado["listas"])
        total_dom = int(estado["total"])
        en_carga = int(estado["en_carga"])

        if listas != ultimo_log or time.time() - ultimo_log_tiempo >= 10:
            extra = f" ({en_carga} en carga)" if en_carga else ""
            print(
                f"[{index}/{total}] Fotos: {listas}/{cantidad_esperada} listas{extra}",
                flush=True,
            )
            ultimo_log = listas
            ultimo_log_tiempo = time.time()

        if total_dom >= cantidad_esperada and listas >= cantidad_esperada:
            print(
                f"[{index}/{total}] Fotos: {listas}/{cantidad_esperada} — todas listas.",
                flush=True,
            )
            return

        page.wait_for_timeout(FOTOS_POLL_MS)

    estado_final = _estado_fotos_subida(page)
    raise PlaywrightTimeout(
        f"Timeout esperando fotos: {estado_final['listas']}/{cantidad_esperada} listas "
        f"({estado_final['total']} en pantalla, {estado_final['en_carga']} en carga)"
    )


def _intentar_click_publicar(page: Page, btn_continuar, *, force: bool = False) -> bool:
    try:
        btn_continuar.first.scroll_into_view_if_needed()
        btn_continuar.first.click(timeout=30000, force=force, no_wait_after=True)
        return True
    except Exception:
        if not force:
            return False
        try:
            return bool(
                page.evaluate(
                    """() => {
                      const b = document.querySelector('#publicacion-continuar');
                      if (!b) return false;
                      b.click();
                      return true;
                    }"""
                )
            )
        except Exception:
            return False


def _url_seleccion_categoria() -> str:
    return f"{AGROADS_BASE_URL}/miembros/publicacion.asp"


def _ir_a_seleccion_categoria(page: Page) -> None:
    if "publicacion.asp" in page.url and "paso=" not in page.url:
        _esperar_pantalla_categoria_lista(page)
        return
    page.goto(_url_seleccion_categoria(), wait_until="domcontentloaded", timeout=60000)
    _esperar_pantalla_categoria_lista(page)


def _esperar_pantalla_categoria_lista(page: Page) -> None:
    try:
        page.locator("button.category-button").first.wait_for(state="visible", timeout=15000)
        return
    except Exception:
        pass
    page.get_by_role("button", name="Continuar").wait_for(state="visible", timeout=10000)


def _esperar_tras_seleccion_categoria(page: Page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=3000)
    except Exception:
        pass
    try:
        page.wait_for_function(
            """() => {
              const btns = document.querySelectorAll('button.category-button');
              const continuar = Array.from(document.querySelectorAll('button')).find(
                b => /^\\s*continuar\\s*$/i.test(b.textContent)
              );
              return btns.length > 0 || (continuar && continuar.offsetParent !== null);
            }""",
            timeout=5000,
        )
    except Exception:
        page.wait_for_timeout(200)


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
        try:
            btn_entendido = page.get_by_role("button", name="Entendido")
            btn_entendido.wait_for(state="visible", timeout=3000)
            btn_entendido.click()
            page.wait_for_timeout(500)
        except Exception:
            pass

        failed_products = []
        for i, product in enumerate(products):
            try:
                _publish_product(page, product, images_folder, index=i + 1, total=len(products))
            except Exception as e:
                titulo_fail = _get(product, "titulo", "Título") or "sin título"
                print(f"Error publicando producto {i + 1}: {e}", flush=True)
                failed_products.append((i + 1, titulo_fail, str(e)))
                try:
                    _ir_a_seleccion_categoria(page)
                except Exception:
                    pass
                continue
            if i < len(products) - 1:
                time.sleep(DELAY_SECONDS)

        elapsed = time.time() - start_time
        if elapsed >= 60:
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"Proceso finalizado correctamente. Tiempo total: {mins} min {secs} seg", flush=True)
        else:
            print(f"Proceso finalizado correctamente. Tiempo total: {int(elapsed)} seg", flush=True)
        total_prod = len(products)
        fallidos = len(failed_products)
        exitos = total_prod - fallidos
        print(
            f"Resumen: Total productos: {total_prod}. Publicados con éxito: {exitos}. No publicados: {fallidos}.",
            flush=True,
        )
        if failed_products:
            print(f"Detalle de errores ({len(failed_products)}):", flush=True)
            for idx, titulo_fail, err in failed_products:
                print(f"- [{idx}] {titulo_fail} -> {err}", flush=True)

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
    titulo_short = _get(product, "titulo", "Título") or "sin título"
    if len(titulo_short) > 50:
        titulo_short = titulo_short[:47] + "..."
    print(f"[{index}/{total}] Procesando: {titulo_short}", flush=True)
    _ir_a_seleccion_categoria(page)

    for intento_cat in range(2):
        try:
            _select_category(page, product)
            break
        except Exception as e_cat:
            err = str(e_cat).lower()
            if intento_cat == 0 and (
                "detached" in err or "err_aborted" in err or "aborted" in err
            ):
                _ir_a_seleccion_categoria(page)
                continue
            raise
    if "paso=2" not in page.url:
        page.wait_for_url("**paso=2**", timeout=30000)
    cantidad_fotos = _subir_fotos_y_esperar(page, product, images_folder, index, total)

    print(f"[{index}/{total}] Completando formulario...", flush=True)
    _fill_form(page, product, images_folder)

    help_el = page.locator('span.help-block').filter(has_text="código de su sistema interno")
    if help_el.count() > 0:
        help_el.first.click()

    if cantidad_fotos > 0:
        print(
            f"[{index}/{total}] Espera de seguridad de {MIN_ESPERA_TRAS_FOTOS_SEG} seg "
            f"tras {cantidad_fotos}/{cantidad_fotos} fotos...",
            flush=True,
        )
        page.wait_for_timeout(MIN_ESPERA_TRAS_FOTOS_SEG * 1000)

    _recuperar_si_error_red(page, f"{AGROADS_BASE_URL}/miembros/publicacion.asp?paso=2")
    btn_continuar = page.locator("#publicacion-continuar")
    btn_continuar.wait_for(state="visible", timeout=60000)
    btn_continuar.first.scroll_into_view_if_needed()
    clic_publicar = False
    for intento in range(5):
        _recuperar_si_error_red(page, f"{AGROADS_BASE_URL}/miembros/publicacion.asp?paso=2")
        btn_continuar = page.locator("#publicacion-continuar")
        if btn_continuar.count() == 0:
            page.wait_for_timeout(2000)
            continue
        if _intentar_click_publicar(page, btn_continuar, force=intento == 4):
            print(f"[{index}/{total}] Enviando publicación...", flush=True)
            clic_publicar = True
            break
        print(
            f"[{index}/{total}] No se pudo hacer clic en publicar (intento {intento + 1}/5)",
            flush=True,
        )
        page.wait_for_timeout(2000)
    if not clic_publicar:
        raise PlaywrightTimeout("No se pudo hacer clic en #publicacion-continuar")
    _url_publicacion_ok = re.compile(r".*(paso=3|panel_de_control\.asp|/central).*")

    def _esperar_post_publicar() -> None:
        page.wait_for_url(_url_publicacion_ok, timeout=120000, wait_until="domcontentloaded")
        if _page_en_error_red(page):
            raise PlaywrightTimeout("La navegación terminó en página de error del navegador")

    ultimo_timeout: BaseException | None = None
    try:
        _esperar_post_publicar()
    except PlaywrightTimeout as e_pub:
        ultimo_timeout = e_pub
        if "paso=2" not in page.url:
            print(
                f"[{index}/{total}] La página no redirigió a paso=3/panel/central (sigue en {page.url}).",
                flush=True,
            )
            raise
        for reintento in range(3):
            _recuperar_si_error_red(page, f"{AGROADS_BASE_URL}/miembros/publicacion.asp?paso=2")
            btn_reintento = page.locator("#publicacion-continuar")
            if btn_reintento.count() == 0:
                print(
                    f"[{index}/{total}] No se pudo completar la publicación (sigue en {page.url}).",
                    flush=True,
                )
                raise ultimo_timeout
            page.wait_for_timeout(4000 * (reintento + 1))
            try:
                btn_reintento.first.click(timeout=15000, force=True, no_wait_after=True)
            except Exception:
                pass
            try:
                _esperar_post_publicar()
                ultimo_timeout = None
                break
            except PlaywrightTimeout as e2:
                ultimo_timeout = e2
                if reintento == 2:
                    print(
                        f"[{index}/{total}] No se pudo completar la publicación (sigue en {page.url}).",
                        flush=True,
                    )
                    raise ultimo_timeout
    titulo = _get(product, "titulo", "Título") or "sin título"
    print(f"[{index}/{total}] OK - Producto publicado: {titulo}", flush=True)
    _ir_a_seleccion_categoria(page)


def _select_category(page: Page, product: dict):
    niveles = [
        _get(product, "categoria", "Categoria"),
        _get(product, "tipo", "Tipo"),
        _get(product, "sub_tipo", "sub tipo", "Sub_tipo"),
        _get(product, "sub_sub_tipo", "sub sub tipo", "Sub_sub_tipo"),
    ]

    for nivel in niveles:
        if not nivel:
            continue
        _esperar_pantalla_categoria_lista(page)
        _click_text_ignoring_accents(page, nivel)
        _esperar_tras_seleccion_categoria(page)
        if _click_continuar_if_visible(page):
            return

    btn_cont = page.get_by_role("button", name="Continuar")
    try:
        btn_cont.wait_for(state="visible", timeout=15000)
        btn_cont.scroll_into_view_if_needed()
        btn_cont.click()
        page.wait_for_url("**paso=2**", timeout=30000)
    except PlaywrightTimeout:
        print(
            f"No apareció el botón Continuar. Revisá en el Excel categoría/tipo/subtipo para este ítem. URL: {page.url}",
            flush=True,
        )
        raise


def _category_text_variants(text: str) -> list[str]:
    variants = [text]
    key = _normalize_text(text)
    for alias in _CATEGORY_ALIASES.get(key, []):
        if alias not in variants:
            variants.append(alias)
    return variants


def _click_text_ignoring_accents(page: Page, text: str):
    def _match(a: str, b: str) -> bool:
        na, nb = _normalize_text(a), _normalize_text(b)
        if na == nb:
            return True
        short, long = (na, nb) if len(na) <= len(nb) else (nb, na)
        if long.startswith(short):
            return True
        if len(short) >= 5 and short in long:
            return True
        return False

    for variant in _category_text_variants(text):
        buttons = page.locator("button.category-button")
        for i in range(buttons.count()):
            try:
                btn = buttons.nth(i)
                name_el = btn.locator("span.category-name")
                if name_el.count() > 0 and _match(variant, name_el.first.inner_text()):
                    btn.click()
                    return
            except Exception:
                continue
        for el in page.locator("a.ripple, a[href*='seccion.asp']").all():
            try:
                if _match(variant, el.inner_text()):
                    el.click()
                    return
            except Exception:
                continue
        try:
            loc = page.get_by_text(variant, exact=False).first
            loc.wait_for(state="visible", timeout=3000)
            loc.click()
            return
        except Exception:
            continue

    visibles: list[str] = []
    for btn in page.locator("button.category-button span.category-name").all():
        try:
            t = btn.inner_text().strip()
            if t:
                visibles.append(t)
        except Exception:
            continue
    opciones = ", ".join(visibles[:12]) if visibles else "(ninguna categoría visible)"
    raise PlaywrightTimeout(
        f"No se encontró '{text}' en la pantalla de categorías. Opciones visibles: {opciones}"
    )


def _click_continuar_if_visible(page: Page) -> bool:
    btn = page.get_by_role("button", name="Continuar")
    try:
        if btn.count() == 0 or not btn.first.is_visible():
            return False
        btn.first.scroll_into_view_if_needed()
        btn.first.click()
        page.wait_for_url("**paso=2**", timeout=30000)
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
    raw = str(val).strip().replace("--&gt;", "").replace("-->", "").replace("->", "").strip()
    target = _normalize_text(raw)
    if target == "otra marca" or target.startswith("otra marca"):
        sel.select_option(value="0")
        page.wait_for_timeout(1000)
        return
    match_parcial = None
    for opt in sel.locator("option").all():
        try:
            txt = opt.inner_text()
            if not txt:
                continue
            opt_raw = txt.replace("-->", "").replace("->", "").strip()
            opt_norm = _normalize_text(opt_raw)
            opt_value = opt.get_attribute("value")
            if target == opt_norm:
                sel.select_option(value=opt_value)
                page.wait_for_timeout(1000)
                return
            if match_parcial is None and target in opt_norm:
                match_parcial = opt_value
        except Exception:
            continue
    if match_parcial:
        sel.select_option(value=match_parcial)
    page.wait_for_timeout(1000)


def _fill_anio(page: Page, product: dict):
    val = _get(product, "ano", "año", "anio", "Año")
    if not val or str(val).strip() == "":
        return
    val_str = str(val).strip()
    v_norm = _normalize_text(val_str)
    if v_norm in ("no lo se", "no lo sé", "no se"):
        page.locator("#publicacion-ano").select_option(value="0")
        return
    try:
        anio = int(float(val_str))
        page.locator("#publicacion-ano").select_option(value=str(anio))
    except (ValueError, TypeError):
        sel = page.locator("#publicacion-ano")
        for opt in sel.locator("option").all():
            try:
                if _normalize_text(opt.inner_text()) == v_norm:
                    sel.select_option(value=opt.get_attribute("value"))
                    return
            except Exception:
                continue
        if page.locator("#publicacion-ano option[value='0']").count() > 0:
            page.locator("#publicacion-ano").select_option(value="0")


def _fill_modelo(page: Page, product: dict):
    def _modelo_en_error() -> bool:
        sel = page.locator("#publicacion-modelo")
        if sel.count() == 0:
            return False
        if (sel.first.get_attribute("aria-invalid") or "").lower() == "true":
            return True
        err = page.locator("#publicacion-modelo-error")
        if err.count() > 0 and err.first.is_visible():
            txt = (err.first.inner_text() or "").strip().lower()
            if "debe seleccionar el modelo" in txt:
                return True
        return False

    def _aplicar_modelo(value: str | None, label: str | None) -> bool:
        modelo_sel_local = page.locator("#publicacion-modelo")
        try:
            if value:
                modelo_sel_local.select_option(value=value)
            elif label:
                modelo_sel_local.select_option(label=label)
            else:
                return False
            page.wait_for_timeout(250)
            if _modelo_en_error():
                modelo_sel_local.click()
                page.wait_for_timeout(150)
                if value:
                    modelo_sel_local.select_option(value=value)
                elif label:
                    modelo_sel_local.select_option(label=label)
                page.wait_for_timeout(250)
            return not _modelo_en_error()
        except Exception:
            return False

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
        target = _normalize_modelo(str(val))
        for opt in modelo_sel.locator("option").all():
            try:
                txt = opt.inner_text()
                opt_value = opt.get_attribute("value")
                if not txt or opt_value == "":
                    continue
                if _normalize_modelo(txt) == target:
                    if _aplicar_modelo(opt_value, None):
                        return
            except Exception:
                continue
        if _aplicar_modelo(None, str(val)):
            return
    _aplicar_modelo("0", None)

def _fill_hp(page: Page, product: dict):
    hp_el = page.locator("#publicacion-hp")
    if hp_el.count() == 0 or not hp_el.is_visible():
        return
    val = _get(product, "hp", "HP")
    if val is not None and str(val).strip() != "":
        hp_el.fill(str(val).strip())


def _fill_combustible(page: Page, product: dict):
    val = _get(product, "combustible", "Combustible")
    if not val or str(val).strip() == "":
        return
    sel = page.locator("#publicacion-combustible")
    if sel.count() == 0:
        return
    v = _normalize_text(str(val))
    if v in ("nafta", "1"):
        sel.select_option(value="1")
    elif v in ("diesel", "gasoil", "2"):
        sel.select_option(value="2")
    elif "gnc" in v or "nafta y gnc" in v or v == "3":
        sel.select_option(value="3")


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
        val = "Hernando, Córdoba, Argentina"
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


def _subir_fotos_y_esperar(
    page: Page,
    product: dict,
    images_folder: Path,
    index: int,
    total: int,
) -> int:
    cantidad_esperada = _cantidad_fotos_esperadas(product, images_folder)
    if cantidad_esperada <= 0:
        return 0

    product_id = _get(product, "id", "ID")
    imagenes = get_images_for_product(images_folder, product_id)
    if not imagenes:
        return 0

    print(
        f"[{index}/{total}] Subiendo {cantidad_esperada} foto(s) antes del formulario...",
        flush=True,
    )
    _upload_images(page, imagenes)
    _esperar_fotos_listas(page, cantidad_esperada, index, total)
    return cantidad_esperada


def _fill_form(page: Page, product: dict, images_folder: Path):
    _fill_titulo(page, product)
    _fill_moneda(page, product)
    _fill_monto(page, product)
    _fill_dto_pago(page, product)

    _fill_condicion(page, product)
    _fill_marca(page, product)
    _fill_modelo(page, product)
    _fill_anio(page, product)
    _fill_hp(page, product)
    _fill_horas(page, product)
    _fill_combustible(page, product)
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
