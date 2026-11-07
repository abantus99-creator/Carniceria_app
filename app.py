import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import threading

# ==================== FECHAS (hora de Chile) ====================
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Santiago")
except Exception:
    TZ = None


def ahora():
    return datetime.now(TZ) if TZ else datetime.now()


def hoy_str():
    return ahora().strftime("%Y-%m-%d")


def hace(dias):
    """Fecha (YYYY-MM-DD) de hace N días."""
    return (ahora() - timedelta(days=dias)).strftime("%Y-%m-%d")


def plata(x):
    try:
        return f"${x:,.0f}"
    except (TypeError, ValueError):
        return "—"


CATEGORIAS = ["Pollo", "Vacuno", "Cerdo", "Otros"]
ICONOS = {"Vacuno": "🥩", "Cerdo": "🐷", "Pollo": "🐔", "Otros": "📦"}


# ==================== BASE DE DATOS ====================
# Si en los Secrets de Streamlit existe DB_URL, todo se guarda en la nube
# (Supabase / PostgreSQL). Si no existe, se usa el archivo local carniceria.db.
TABLAS = {
    "productos": "id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, categoria TEXT, precio REAL, stock REAL, minimo REAL",
    "ventas": "id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, cantidad REAL, total REAL, fecha TEXT",
    "compras": "id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, cantidad REAL, precio REAL, fecha TEXT",
    "cierres": "id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, total REAL, kilos REAL, num INTEGER, notas TEXT",
    "pendientes": "id INTEGER PRIMARY KEY AUTOINCREMENT, items TEXT, total REAL, fecha TEXT, estado TEXT DEFAULT 'pendiente', fecha_cobro TEXT",
    "cambios_precio": "id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER, precio_anterior REAL, precio_nuevo REAL, fecha TEXT, motivo TEXT",
}


def _db_url():
    try:
        url = st.secrets["DB_URL"]
    except Exception:
        url = os.environ.get("DB_URL")
    return url.strip() if url else None


class Fila(dict):
    """Fila que se puede leer por nombre (fila['total']) o por posición (fila[0])."""
    def __init__(self, cols, vals):
        super().__init__(zip(cols, vals))
        self._v = tuple(vals)

    def __getitem__(self, k):
        return self._v[k] if isinstance(k, int) else super().__getitem__(k)


class Resultado:
    def __init__(self, cur):
        self.cols = [d[0] for d in cur.description] if cur.description else []
        self.rows = cur.fetchall() if cur.description else []

    def fetchone(self):
        return Fila(self.cols, self.rows[0]) if self.rows else None

    def fetchall(self):
        return [Fila(self.cols, r) for r in self.rows]


def _limpiar(params):
    return tuple(p.item() if hasattr(p, "item") else p for p in params)


class BD:
    def __init__(self):
        url = _db_url()
        self.nube = bool(url)
        self.lock = threading.Lock()
        if self.nube:
            import psycopg2
            self.raw = psycopg2.connect(url, connect_timeout=15)
            self.raw.autocommit = True
        else:
            self.raw = sqlite3.connect("carniceria.db", check_same_thread=False, isolation_level=None)

    def _sql(self, sql):
        if self.nube:
            sql = (sql.replace("?", "%s")
                      .replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
                      .replace(" REAL", " DOUBLE PRECISION"))
        return sql

    def execute(self, sql, params=()):
        with self.lock:
            cur = self.raw.cursor()
            try:
                cur.execute(self._sql(sql), _limpiar(params))
                return Resultado(cur)
            finally:
                cur.close()

    def executemany(self, sql, filas):
        filas = [_limpiar(f) for f in filas]
        if not filas:
            return
        with self.lock:
            cur = self.raw.cursor()
            try:
                cur.executemany(self._sql(sql), filas)
            finally:
                cur.close()

    def df(self, sql, params=()):
        r = self.execute(sql, params)
        return pd.DataFrame(r.rows, columns=r.cols)

    def vivo(self):
        try:
            self.execute("SELECT 1")
            return True
        except Exception:
            return False

    def commit(self):
        pass  # se guarda automáticamente

    def close(self):
        pass  # la conexión se reutiliza


@st.cache_resource(show_spinner="Conectando a la base de datos…")
def _conexion():
    return BD()


def get_db():
    bd = _conexion()
    if bd.nube and not bd.vivo():
        _conexion.clear()
        bd = _conexion()
    return bd


def leer(sql, conn, params=()):
    return conn.df(sql, params)


def _migrar_desde_archivo(conn):
    """Si la nube está vacía y existe el archivo local antiguo, copia sus datos."""
    if not os.path.exists("carniceria.db"):
        return 0
    if conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0] > 0:
        return 0
    viejo = sqlite3.connect("carniceria.db")
    copiadas = 0
    try:
        for tabla, definicion in TABLAS.items():
            try:
                cols_viejas = [r[1] for r in viejo.execute(f"PRAGMA table_info({tabla})")]
            except Exception:
                continue
            cols = [c.split()[0] for c in definicion.split(", ") if c.split()[0] in cols_viejas]
            if not cols:
                continue
            filas = viejo.execute(f"SELECT {', '.join(cols)} FROM {tabla}").fetchall()
            if not filas:
                continue
            marcas = ",".join("?" * len(cols))
            conn.executemany(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})", filas)
            copiadas += len(filas)
            if "id" in cols:
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {tabla}), 0) + 1, false)"
                )
    finally:
        viejo.close()
    return copiadas


@st.cache_resource(show_spinner=False)
def init():
    conn = get_db()
    for tabla, definicion in TABLAS.items():
        conn.execute(f"CREATE TABLE IF NOT EXISTS {tabla} ({definicion})")

    # Bases antiguas que no tenían la columna fecha_cobro
    try:
        conn.execute("ALTER TABLE pendientes ADD COLUMN fecha_cobro TEXT")
    except Exception:
        pass

    if conn.nube:
        try:
            _migrar_desde_archivo(conn)
        except Exception as e:
            print("No se pudo migrar el archivo local:", e)

    if conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
        datos = [
            ("Lomo Vetado", "Vacuno", 12990, 15, 5),
            ("Asiento", "Vacuno", 8990, 20, 6),
            ("Posta Negra", "Vacuno", 7990, 18, 5),
            ("Posta Rosada", "Vacuno", 7490, 15, 5),
            ("Carne Molida", "Vacuno", 6990, 20, 6),
            ("Chuleta de Cerdo", "Cerdo", 5490, 15, 5),
            ("Costillar de Cerdo", "Cerdo", 4990, 18, 6),
            ("Lomo de Cerdo", "Cerdo", 6490, 10, 4),
            ("Longaniza", "Cerdo", 7990, 8, 3),
            ("Pollo Entero", "Pollo", 2990, 30, 10),
            ("Trutro Entero", "Pollo", 3490, 20, 6),
            ("Pechuga", "Pollo", 4990, 15, 5),
            ("Ala", "Pollo", 2490, 12, 4),
        ]
        conn.executemany(
            "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
            datos
        )
    return True


# ==================== ESTADÍSTICAS ====================
def costos_ultimos(conn):
    """Último precio de compra registrado por producto."""
    df = leer("""
        SELECT c.producto_id AS id, c.precio AS costo
        FROM compras c
        WHERE c.precio > 0
          AND c.id = (SELECT MAX(c2.id) FROM compras c2
                      WHERE c2.producto_id = c.producto_id AND c2.precio > 0)
    """, conn)
    return dict(zip(df["id"], df["costo"]))


def dias_historial(conn):
    """Cuántos días de ventas hay (máx 30), para no subestimar si la app es nueva."""
    r = conn.execute("SELECT MIN(fecha) FROM ventas").fetchone()[0]
    if not r:
        return 30
    try:
        primera = datetime.strptime(r[:10], "%Y-%m-%d").date()
    except ValueError:
        return 30
    return max(1, min(30, (ahora().date() - primera).days + 1))


def estadisticas_productos(conn):
    df = leer("""
        SELECT p.id, p.nombre, p.categoria, p.precio, p.stock, p.minimo,
            COALESCE(SUM(CASE WHEN v.fecha >= ? THEN v.cantidad END), 0) AS kg30,
            COALESCE(SUM(CASE WHEN v.fecha >= ? THEN v.cantidad END), 0) AS kg7,
            COALESCE(SUM(CASE WHEN v.fecha >= ? AND v.fecha < ? THEN v.cantidad END), 0) AS kg7ant,
            MAX(v.fecha) AS ultima_venta
        FROM productos p
        LEFT JOIN ventas v ON v.producto_id = p.id
        GROUP BY p.id
    """, conn, params=(hace(29), hace(6), hace(13), hace(6)))
    dh = dias_historial(conn)
    df["prom_dia"] = df["kg30"] / dh
    df["dias_stock"] = df["stock"] / df["prom_dia"].where(df["prom_dia"] > 0)
    df["tendencia"] = (df["kg7"] - df["kg7ant"]) / df["kg7ant"].where(df["kg7ant"] > 0) * 100
    df["costo"] = df["id"].map(costos_ultimos(conn))
    return df, dh


def txt_dias(d):
    return "sin ventas" if pd.isna(d) else f"{d:.0f}"


def txt_tend(t):
    return "—" if pd.isna(t) else f"{t:+.0f}%"


# ==================== ESTILOS ====================
st.set_page_config(page_title="Carnicería", page_icon="🥩", layout="wide")
init()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stButton > button {
    height: 72px !important;
    font-size: 18px !important;
    font-weight: 700 !important;
    border-radius: 16px !important;
    background: linear-gradient(135deg, #27ae60, #1e8449) !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(39,174,96,0.3);
    transition: all 0.2s ease;
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(39,174,96,0.4);
}

div[data-testid="column"] .stButton > button {
    height: 68px !important;
    font-size: 15px !important;
    border-radius: 14px !important;
}

.big-total {
    font-size: 2.2rem;
    font-weight: 800;
    color: #27ae60;
    margin: 12px 0;
}
.ticket-card {
    background: #f8f9fa;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 12px;
    border-left: 5px solid #27ae60;
    color: #222;
}

/* ---------- TECLADO NUMÉRICO COMPACTO ---------- */
.st-key-teclado {
    max-width: 280px;
    margin: 0 auto;
    gap: 0.45rem !important;
}
.st-key-teclado [data-testid="stVerticalBlock"] {
    gap: 0.45rem !important;
}
.st-key-teclado [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.45rem !important;
}
.st-key-teclado [data-testid="stColumn"],
.st-key-teclado [data-testid="column"] {
    min-width: 0 !important;
    width: auto !important;
    flex: 1 1 0 !important;
}
div.st-key-teclado .stButton > button,
div.st-key-teclado div[data-testid="stColumn"] .stButton > button,
div.st-key-teclado div[data-testid="column"] .stButton > button {
    height: 48px !important;
    min-height: 48px !important;
    padding: 0 !important;
    font-size: 22px !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    background: #ffffff !important;
    color: #222 !important;
    border: 1px solid #d5d8dc !important;
    box-shadow: none !important;
}
div.st-key-teclado .stButton > button:hover,
div.st-key-teclado div[data-testid="stColumn"] .stButton > button:hover {
    background: #eef1f3 !important;
    transform: none !important;
}
.kg-display {
    text-align: center;
    font-size: 2rem;
    font-weight: 800;
    color: #27ae60;
    border: 2px solid #27ae60;
    border-radius: 12px;
    padding: 6px 0;
    margin-bottom: 4px;
}
</style>
""", unsafe_allow_html=True)

# ==================== SELECCIÓN DE MODO ====================
if "modo" not in st.session_state:
    st.session_state.modo = None

if st.session_state.modo is None:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("## 🥩 Bienvenido a la Carnicería")
    st.markdown("### ¿Quién va a usar el sistema?")
    st.markdown("<br>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔪  CARNICERO\n\nArmar pedidos", width="stretch"):
            st.session_state.modo = "carnicero"
            st.session_state.ticket = []
            st.session_state.cantidad_str = ""
            st.session_state.prod_sel = None
            st.rerun()
    with col2:
        if st.button("💵  CAJA\n\nCobrar y gestionar", width="stretch"):
            st.session_state.modo = "caja"
            st.rerun()
    st.stop()

# Botón cambiar modo
st.sidebar.markdown("### 🔄 Cambiar modo")
if st.sidebar.button("Volver al inicio", width="stretch"):
    st.session_state.modo = None
    st.rerun()

conn = get_db()
if conn.nube:
    st.sidebar.success("☁️ Datos guardados en la nube")
else:
    st.sidebar.warning("⚠️ Guardando solo en este servidor (sin nube)")

# ============================================================
#                         CARNICERO
# ============================================================
if st.session_state.modo == "carnicero":
    st.markdown("## 🔪 Modo Carnicero")
    st.caption("Elige producto → marca kilos → envía a caja")

    if "ticket" not in st.session_state:
        st.session_state.ticket = []
    if "cantidad_str" not in st.session_state:
        st.session_state.cantidad_str = ""
    if "prod_sel" not in st.session_state:
        st.session_state.prod_sel = None

    prods = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    # Productos
    st.markdown("### 1️⃣ Elige el producto")
    cats = {"Vacuno": "🥩", "Cerdo": "🐷", "Pollo": "🐔", "Otros": "📦"}

    for cat, icon in cats.items():
        lista = [p for p in prods if p["categoria"] == cat]
        if not lista:
            continue
        st.markdown(f"**{icon} {cat}**")
        cols = st.columns(4)
        for i, p in enumerate(lista):
            with cols[i % 4]:
                activo = st.session_state.prod_sel and st.session_state.prod_sel["id"] == p["id"]
                label = f"{'✅ ' if activo else ''}{p['nombre']}\n${p['precio']:,.0f}"
                if st.button(label, key=f"p{p['id']}", width="stretch"):
                    st.session_state.prod_sel = dict(p)
                    st.session_state.cantidad_str = ""
                    st.rerun()

    st.markdown("---")

    # Kilos
    st.markdown("### 2️⃣ Marca los kilos")
    if st.session_state.prod_sel:
        st.success(f"Producto: **{st.session_state.prod_sel['nombre']}**  ·  ${st.session_state.prod_sel['precio']:,.0f}/kg")
    else:
        st.warning("Primero elige un producto arriba")

    cantidad_mostrar = st.session_state.cantidad_str or "0"

    # Teclado numérico compacto (tipo teléfono)
    with st.container(key="teclado"):
        st.markdown(f"<div class='kg-display'>{cantidad_mostrar} kg</div>", unsafe_allow_html=True)
        teclas = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [".", "0", "⌫"]]
        for fila in teclas:
            cols = st.columns(3, gap="small")
            for i, t in enumerate(fila):
                with cols[i]:
                    if st.button(t, key=f"k{t}", width="stretch"):
                        actual = st.session_state.cantidad_str
                        if t == "⌫":
                            st.session_state.cantidad_str = actual[:-1]
                        elif t == "." and "." in actual:
                            pass
                        elif len(actual) < 6:
                            st.session_state.cantidad_str = ("0." if (t == "." and not actual) else actual + t)
                        st.rerun()

    # Vista previa del subtotal
    if st.session_state.prod_sel and st.session_state.cantidad_str:
        try:
            prev = float(st.session_state.cantidad_str) * st.session_state.prod_sel["precio"]
            st.caption(f"Subtotal: **{plata(prev)}**")
        except ValueError:
            pass

    if st.button("➕  AGREGAR AL TICKET", width="stretch"):
        if not st.session_state.prod_sel:
            st.error("Elige un producto")
        elif not st.session_state.cantidad_str:
            st.error("Ingresa los kilos")
        else:
            try:
                cant = float(st.session_state.cantidad_str)
                if cant <= 0:
                    st.error("Cantidad inválida")
                else:
                    p = st.session_state.prod_sel
                    subtotal = round(cant * p["precio"])
                    st.session_state.ticket.append({
                        "id": p["id"],
                        "nombre": p["nombre"],
                        "precio": p["precio"],
                        "cantidad": cant,
                        "subtotal": subtotal
                    })
                    st.session_state.prod_sel = None
                    st.session_state.cantidad_str = ""
                    st.rerun()
            except ValueError:
                st.error("Cantidad inválida")

    st.markdown("---")

    # Ticket
    st.markdown("### 🛒 Ticket")
    if not st.session_state.ticket:
        st.info("Todavía no hay productos")
    else:
        total = 0
        for i, item in enumerate(st.session_state.ticket):
            cols = st.columns([5, 1])
            with cols[0]:
                st.markdown(
                    f"**{item['nombre']}**  ·  {item['cantidad']:.2f} kg  ×  ${item['precio']:,.0f}  =  **${item['subtotal']:,.0f}**"
                )
            with cols[1]:
                if st.button("❌", key=f"qt{i}"):
                    st.session_state.ticket.pop(i)
                    st.rerun()
            total += item["subtotal"]

        st.markdown(f"<div class='big-total'>TOTAL: ${total:,.0f}</div>", unsafe_allow_html=True)

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📤  ENVIAR A CAJA", width="stretch"):
                fecha = ahora().strftime("%Y-%m-%d %H:%M")
                conn.execute(
                    "INSERT INTO pendientes (items, total, fecha, estado) VALUES (?,?,?,?)",
                    (json.dumps(st.session_state.ticket), total, fecha, "pendiente")
                )
                conn.commit()
                st.session_state.ticket = []
                st.success("✅ Enviado a caja")
                st.balloons()
                st.rerun()
        with col_b:
            if st.button("🗑️  Cancelar", width="stretch"):
                st.session_state.ticket = []
                st.rerun()

# ============================================================
#                           CAJA
# ============================================================
elif st.session_state.modo == "caja":
    st.markdown("## 💵 Modo Caja")

    menu = st.sidebar.radio("Menú", [
        "🧾 Cobrar",
        "🏠 Resumen",
        "📦 Productos",
        "📥 Compras",
        "📋 Pedidos",
        "💡 Precios",
        "🧾 Cierre de Caja",
        "📊 Análisis"
    ], label_visibility="collapsed")

    # ----- COBRAR -----
    if menu == "🧾 Cobrar":
        st.markdown("### 🧾 Tickets pendientes")
        pendientes = conn.execute(
            "SELECT * FROM pendientes WHERE estado='pendiente' ORDER BY id ASC"
        ).fetchall()

        if not pendientes:
            st.success("✅ No hay tickets pendientes")
        else:
            for pend in pendientes:
                items = json.loads(pend["items"])
                st.markdown(f"""
                <div class="ticket-card">
                    <strong>Ticket #{pend['id']}</strong> &nbsp;·&nbsp; {pend['fecha']}
                </div>
                """, unsafe_allow_html=True)

                for it in items:
                    st.write(f"• **{it['nombre']}** — {it['cantidad']:.2f} kg × ${it['precio']:,.0f} = ${it['subtotal']:,.0f}")

                st.markdown(f"<div class='big-total'>TOTAL: ${pend['total']:,.0f}</div>", unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"✅  COBRAR  ${pend['total']:,.0f}", key=f"cob{pend['id']}", width="stretch"):
                        fecha_cobro = ahora().strftime("%Y-%m-%d %H:%M")
                        for it in items:
                            conn.execute(
                                "UPDATE productos SET stock = stock - ? WHERE id=?",
                                (it["cantidad"], it["id"])
                            )
                            conn.execute(
                                "INSERT INTO ventas (producto_id, cantidad, total, fecha) VALUES (?,?,?,?)",
                                (it["id"], it["cantidad"], it["subtotal"], fecha_cobro)
                            )
                        conn.execute(
                            "UPDATE pendientes SET estado='cobrado', fecha_cobro=? WHERE id=?",
                            (fecha_cobro, pend["id"])
                        )
                        conn.commit()
                        st.success(f"Cobrado ${pend['total']:,.0f}")
                        st.rerun()
                with col2:
                    if st.button("❌  Anular", key=f"an{pend['id']}", width="stretch"):
                        conn.execute(
                            "UPDATE pendientes SET estado='anulado', fecha_cobro=? WHERE id=?",
                            (ahora().strftime("%Y-%m-%d %H:%M"), pend["id"])
                        )
                        conn.commit()
                        st.warning("Anulado")
                        st.rerun()
                st.markdown("---")

        # Historial últimas 5 compras de clientes
        st.markdown("### 🕘 Últimas 5 compras")
        ultimas = conn.execute("""
            SELECT * FROM pendientes WHERE estado='cobrado'
            ORDER BY COALESCE(fecha_cobro, fecha) DESC, id DESC LIMIT 5
        """).fetchall()
        if not ultimas:
            st.info("Todavía no hay compras cobradas")
        else:
            for k, v in enumerate(ultimas):
                items = json.loads(v["items"])
                kg = sum(i["cantidad"] for i in items)
                fecha = v["fecha_cobro"] or v["fecha"]
                with st.expander(f"🧾 Ticket {v['id']} · {fecha} · {plata(v['total'])}", expanded=(k == 0)):
                    det = pd.DataFrame([{
                        "Producto": i["nombre"],
                        "Kilos": f"{i['cantidad']:.2f}",
                        "$/kg": plata(i["precio"]),
                        "Subtotal": plata(i["subtotal"]),
                    } for i in items])
                    st.dataframe(det, width="stretch", hide_index=True)
                    st.markdown(f"**Total: {plata(v['total'])}** · {kg:.2f} kg · {len(items)} producto(s)")

    # ----- RESUMEN -----
    elif menu == "🏠 Resumen":
        st.markdown("### 🏠 Resumen del día")
        hoy = hoy_str()
        total = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]
        kilos = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]
        num = conn.execute("SELECT COUNT(*) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]
        pend = conn.execute("SELECT COUNT(*) FROM pendientes WHERE estado='pendiente'").fetchone()[0]
        bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Ventas hoy", f"${total:,.0f}")
        c2.metric("⚖️ Kilos", f"{kilos:.1f}")
        c3.metric("🧾 Nº ventas", num)
        c4.metric("⏳ Pendientes", pend)

        if pend > 0:
            st.warning(f"Hay **{pend}** ticket(s) esperando cobro → ve a **Cobrar**")
        if bajo > 0:
            st.error(f"**{bajo}** producto(s) con stock bajo")
            df = leer("SELECT nombre, stock, minimo FROM productos WHERE stock <= minimo", conn)
            st.dataframe(df, width="stretch", hide_index=True)

    # ----- PRODUCTOS -----
    elif menu == "📦 Productos":
        st.markdown("### 📦 Productos")
        stickers = {"Vacuno": "🥩 VACUNO", "Cerdo": "🐷 CERDO", "Pollo": "🐔 POLLO", "Otros": "📦 OTROS"}
        for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
            df = leer(
                "SELECT nombre, precio, stock, minimo FROM productos WHERE categoria=? ORDER BY nombre",
                conn, params=(cat,)
            )
            if not df.empty:
                st.markdown(f"#### {stickers[cat]}")
                st.dataframe(df, width="stretch", hide_index=True)

        with st.expander("➕ Agregar producto"):
            with st.form("np"):
                n = st.text_input("Nombre")
                cat = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
                precio = st.number_input("Precio $/kg", min_value=0, step=100)
                stock = st.number_input("Stock kg", min_value=0.0, step=0.5)
                minimo = st.number_input("Mínimo", min_value=0.0, value=5.0, step=0.5)
                if st.form_submit_button("💾 Guardar") and n.strip():
                    conn.execute(
                        "INSERT INTO productos (nombre,categoria,precio,stock,minimo) VALUES (?,?,?,?,?)",
                        (n.strip(), cat, precio, stock, minimo)
                    )
                    conn.commit()
                    st.success("Guardado")
                    st.rerun()

    # ----- COMPRAS -----
    elif menu == "📥 Compras":
        st.markdown("### 📥 Registrar compra")
        st.info("Al guardar, el precio de venta se actualiza con **+30% de margen**.")

        if "carrito_c" not in st.session_state:
            st.session_state.carrito_c = []

        prods = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()

        col1, col2 = st.columns([2, 1])
        with col1:
            opts = {f"{p['nombre']} (stock {p['stock']:.1f})": p for p in prods}
            sel = st.selectbox("Producto", list(opts.keys()))
            cant = st.number_input("Kilos que entran", min_value=0.1, step=0.5, value=5.0)
            precio = st.number_input("Precio compra $/kg", min_value=0, step=50)
            if precio > 0:
                st.success(f"Precio venta quedará en **${round(precio*1.3):,.0f}/kg**")

            if st.button("➕ Agregar", width="stretch"):
                p = opts[sel]
                pv = round(precio * 1.3) if precio > 0 else p["precio"]
                st.session_state.carrito_c.append({
                    "id": p["id"], "nombre": p["nombre"], "cantidad": cant,
                    "precio": precio, "subtotal": cant * precio, "pv": pv,
                    "precio_ant": p["precio"]
                })
                st.rerun()

        with col2:
            st.markdown("#### Carrito")
            if not st.session_state.carrito_c:
                st.info("Vacío")
            else:
                total = sum(i["subtotal"] for i in st.session_state.carrito_c)
                for i, item in enumerate(st.session_state.carrito_c):
                    st.write(f"**{item['nombre']}** {item['cantidad']:.1f} kg")
                    if st.button("❌", key=f"qc{i}"):
                        st.session_state.carrito_c.pop(i)
                        st.rerun()
                st.markdown(f"**Total: ${total:,.0f}**")
                if st.button("✅ Guardar compra", width="stretch"):
                    fecha = ahora().strftime("%Y-%m-%d %H:%M")
                    for item in st.session_state.carrito_c:
                        conn.execute(
                            "UPDATE productos SET stock=stock+?, precio=? WHERE id=?",
                            (item["cantidad"], item["pv"], item["id"])
                        )
                        conn.execute(
                            "INSERT INTO compras (producto_id,cantidad,precio,fecha) VALUES (?,?,?,?)",
                            (item["id"], item["cantidad"], item["precio"], fecha)
                        )
                        if item["pv"] != item.get("precio_ant"):
                            conn.execute(
                                "INSERT INTO cambios_precio (producto_id, precio_anterior, precio_nuevo, fecha, motivo) VALUES (?,?,?,?,?)",
                                (item["id"], item.get("precio_ant"), item["pv"], fecha, "Compra (+30%)")
                            )
                    conn.commit()
                    st.session_state.carrito_c = []
                    st.success("Compra guardada")
                    st.rerun()

    # ----- PEDIDOS -----
    elif menu == "📋 Pedidos":
        st.markdown("### 📋 Qué conviene pedir")
        df, dh = estadisticas_productos(conn)

        dias_cubrir = st.slider("¿Para cuántos días quieres que alcance el pedido?", 3, 21, 7)
        st.caption(f"Basado en las ventas de los últimos {dh} días y la tendencia de la última semana.")

        with st.expander("ℹ️ ¿Cómo se calcula?"):
            st.markdown(
                f"- **Vende kg/día**: kilos vendidos en los últimos {dh} días ÷ {dh}.\n"
                "- **Días de stock**: stock actual ÷ venta diaria (cuántos días te alcanza).\n"
                "- **Tendencia 7d**: kilos de esta semana vs la semana anterior. Si sube, se pide más; si baja, menos (tope −30% / +50%).\n"
                f"- **Pedir kg** = venta diaria × {dias_cubrir} días × tendencia + mínimo − stock.\n"
                "- 🔴 Urgente: bajo el mínimo o se acaba en ≤2 días · 🟡 Pronto: no alcanza para los días elegidos · 🟢 Normal: reposición."
            )

        rango = {"🔴 Urgente": 0, "🟡 Pronto": 1, "🟢 Normal": 2}
        total_kg, total_costo, algo = 0.0, 0.0, False

        for cat in CATEGORIAS:
            sub = df[df["categoria"] == cat]
            if sub.empty:
                continue
            st.markdown(f"#### {ICONOS[cat]} {cat}")

            filas = []
            for _, r in sub.iterrows():
                t = r["tendencia"]
                factor = 1 + max(-30, min(50, t)) / 100 if pd.notna(t) else 1
                demanda = r["prom_dia"] * dias_cubrir * factor
                pedir = round(max(0.0, demanda + r["minimo"] - r["stock"]), 1)
                if pedir <= 0:
                    continue

                motivos = []
                if r["stock"] <= 0:
                    motivos.append("Sin stock")
                elif r["stock"] <= r["minimo"]:
                    motivos.append(f"Stock {r['stock']:.1f} kg bajo el mínimo ({r['minimo']:.1f} kg)")
                if pd.notna(r["dias_stock"]) and r["dias_stock"] < dias_cubrir:
                    motivos.append(f"Se acaba en ~{r['dias_stock']:.0f} días")
                if pd.notna(t) and t >= 15:
                    motivos.append(f"Ventas subiendo {t:+.0f}% esta semana")
                elif pd.notna(t) and t <= -15:
                    motivos.append(f"Ventas bajando {t:.0f}% (se pide menos)")
                if r["prom_dia"] > 0:
                    motivos.append(f"Vende {r['prom_dia']:.1f} kg/día")
                else:
                    motivos.append("Sin ventas recientes: solo repone el mínimo")

                if r["stock"] <= r["minimo"] or (pd.notna(r["dias_stock"]) and r["dias_stock"] <= 2):
                    prio = "🔴 Urgente"
                elif pd.notna(r["dias_stock"]) and r["dias_stock"] < dias_cubrir:
                    prio = "🟡 Pronto"
                else:
                    prio = "🟢 Normal"

                costo = pedir * r["costo"] if pd.notna(r["costo"]) else None
                filas.append({
                    "Prioridad": prio,
                    "Producto": r["nombre"],
                    "Stock kg": round(r["stock"], 1),
                    "Vende kg/día": round(r["prom_dia"], 1),
                    "Días de stock": txt_dias(r["dias_stock"]),
                    "Tendencia 7d": txt_tend(t),
                    "Pedir kg": pedir,
                    "Costo aprox.": plata(costo) if costo is not None else "—",
                    "¿Por qué?": " · ".join(motivos),
                    "_rank": rango[prio],
                    "_costo": costo or 0,
                })

            if not filas:
                st.success(f"Stock suficiente para los próximos {dias_cubrir} días")
                continue

            algo = True
            tabla = pd.DataFrame(filas).sort_values(["_rank", "Pedir kg"], ascending=[True, False])
            kg_cat = tabla["Pedir kg"].sum()
            costo_cat = tabla["_costo"].sum()
            total_kg += kg_cat
            total_costo += costo_cat

            c1, c2, c3 = st.columns(3)
            c1.metric("Kg a pedir", f"{kg_cat:.1f}")
            c2.metric("Urgentes", int((tabla["_rank"] == 0).sum()))
            c3.metric("Costo aprox.", plata(costo_cat) if costo_cat else "—")
            st.dataframe(tabla.drop(columns=["_rank", "_costo"]), width="stretch", hide_index=True)

        st.markdown("---")
        if algo:
            c1, c2 = st.columns(2)
            c1.metric("📦 Total a pedir", f"{total_kg:.1f} kg")
            c2.metric("💸 Costo total aprox.", plata(total_costo) if total_costo else "—")
            st.caption("El costo se calcula con el último precio de compra registrado en 📥 Compras.")
        else:
            st.success("✅ No hay que pedir nada por ahora")

    # ----- PRECIOS -----
    elif menu == "💡 Precios":
        st.markdown("### 💡 Precios sugeridos")
        st.caption("Solo se sugiere **bajar 5%** en productos que se están moviendo lento, para rotar el stock antes de que pierda calidad.")

        df, dh = estadisticas_productos(conn)
        ult = leer(
            "SELECT producto_id AS id, MAX(fecha) AS ult_cambio FROM cambios_precio GROUP BY producto_id", conn
        )
        df = df.merge(ult, on="id", how="left")

        with st.expander("ℹ️ ¿Cuándo se sugiere bajar?"):
            st.markdown(
                f"- No tuvo ventas en los últimos {dh} días, **o**\n"
                "- El stock alcanza para **más de 30 días** de venta, **o**\n"
                "- El stock es **más de 3 veces el mínimo**, **o**\n"
                "- Las ventas cayeron **20% o más** esta semana y hay más del doble del mínimo.\n\n"
                "No se sugiere si el stock está bajo el mínimo, si el precio quedaría bajo el costo, "
                "o si ya se bajó hace menos de 7 días (hay que esperar a ver el efecto)."
            )

        hay = False
        for cat in CATEGORIAS:
            sub = df[df["categoria"] == cat]
            if sub.empty:
                continue

            filas = []
            for _, r in sub.iterrows():
                if r["stock"] <= r["minimo"] or r["stock"] <= 0:
                    continue
                motivos = []
                if r["kg30"] == 0:
                    motivos.append(f"Sin ventas en {dh} días")
                elif pd.notna(r["dias_stock"]) and r["dias_stock"] > 30:
                    motivos.append(f"El stock alcanza para {r['dias_stock']:.0f} días")
                if r["minimo"] > 0 and r["stock"] > r["minimo"] * 3:
                    motivos.append(f"Stock {r['stock'] / r['minimo']:.1f} veces el mínimo")
                t = r["tendencia"]
                if pd.notna(t) and t <= -20 and r["stock"] > r["minimo"] * 2:
                    motivos.append(f"Ventas cayendo {t:.0f}% esta semana")
                if not motivos:
                    continue

                sug = int(round(r["precio"] * 0.95, -1))
                dias_desde = None
                if pd.notna(r["ult_cambio"]):
                    try:
                        dias_desde = (ahora().date() - datetime.strptime(str(r["ult_cambio"])[:10], "%Y-%m-%d").date()).days
                    except ValueError:
                        dias_desde = None

                if dias_desde is not None and dias_desde < 7:
                    estado, ok = f"⏸️ Esperar (cambió hace {dias_desde} d)", False
                elif pd.notna(r["costo"]) and sug <= r["costo"]:
                    estado, ok = "⚠️ Quedaría bajo el costo", False
                else:
                    estado, ok = "✅ Conviene bajar", True

                margen = f"{(sug - r['costo']) / sug * 100:.0f}%" if pd.notna(r["costo"]) and sug > 0 else "—"
                filas.append({
                    "Decisión": estado,
                    "Producto": r["nombre"],
                    "Precio actual": plata(r["precio"]),
                    "Precio −5%": plata(sug),
                    "Stock kg": round(r["stock"], 1),
                    "Vende kg/día": round(r["prom_dia"], 1),
                    "Días de stock": txt_dias(r["dias_stock"]),
                    "Tendencia 7d": txt_tend(t),
                    "Margen nuevo": margen,
                    "¿Por qué?": " · ".join(motivos),
                    "_id": int(r["id"]), "_ant": r["precio"], "_sug": sug, "_ok": ok,
                })

            st.markdown(f"#### {ICONOS[cat]} {cat}")
            if not filas:
                st.success("Precios OK, los productos se están vendiendo bien")
                continue

            hay = True
            tabla = pd.DataFrame(filas)
            st.dataframe(tabla.drop(columns=["_id", "_ant", "_sug", "_ok"]), width="stretch", hide_index=True)

            opciones = {f"{f['Producto']} → {plata(f['_sug'])}": f for f in filas if f["_ok"]}
            if opciones:
                elegidos = st.multiselect("Aplicar baja de 5% a:", list(opciones), default=list(opciones), key=f"ms_{cat}")
                if st.button(f"✅ Aplicar en {cat}", key=f"apl_{cat}", width="stretch") and elegidos:
                    fecha = ahora().strftime("%Y-%m-%d %H:%M")
                    for k in elegidos:
                        f = opciones[k]
                        conn.execute("UPDATE productos SET precio=? WHERE id=?", (f["_sug"], f["_id"]))
                        conn.execute(
                            "INSERT INTO cambios_precio (producto_id, precio_anterior, precio_nuevo, fecha, motivo) VALUES (?,?,?,?,?)",
                            (f["_id"], f["_ant"], f["_sug"], fecha, f["¿Por qué?"])
                        )
                    conn.commit()
                    st.success("Precios actualizados")
                    st.rerun()

        if not hay:
            st.success("No hay cambios recomendados")

        with st.expander("🕘 Últimos cambios de precio"):
            hist = leer("""
                SELECT cp.fecha AS "Fecha", p.nombre AS "Producto",
                       cp.precio_anterior AS "Antes", cp.precio_nuevo AS "Ahora", cp.motivo AS "Motivo"
                FROM cambios_precio cp JOIN productos p ON p.id = cp.producto_id
                ORDER BY cp.id DESC LIMIT 10
            """, conn)
            if hist.empty:
                st.info("Sin cambios registrados")
            else:
                st.dataframe(hist, width="stretch", hide_index=True)

    # ----- CIERRE -----
    elif menu == "🧾 Cierre de Caja":
        st.markdown("### 🧾 Cierre de caja")
        hoy = hoy_str()
        total = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]
        kilos = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]
        num = conn.execute("SELECT COUNT(*) FROM ventas WHERE substr(fecha, 1, 10)=?", (hoy,)).fetchone()[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas", f"${total:,.0f}")
        c2.metric("Kilos", f"{kilos:.1f}")
        c3.metric("Tickets", num)

        notas = st.text_input("Notas del día (opcional)")
        if st.button("💾 Guardar cierre", width="stretch"):
            conn.execute("DELETE FROM cierres WHERE fecha=?", (hoy,))
            conn.execute(
                "INSERT INTO cierres (fecha,total,kilos,num,notas) VALUES (?,?,?,?,?)",
                (hoy, total, kilos, num, notas)
            )
            conn.commit()
            st.success("Cierre guardado")

        st.markdown("#### Historial")
        st.dataframe(
            leer("SELECT fecha, total, kilos, num, notas FROM cierres ORDER BY fecha DESC LIMIT 10", conn),
            width="stretch", hide_index=True
        )

    # ----- ANÁLISIS -----
    elif menu == "📊 Análisis":
        st.markdown("### 📊 Análisis del negocio")
        periodos = {"Últimos 7 días": 7, "Últimos 30 días": 30, "Últimos 90 días": 90}
        n = periodos[st.selectbox("Período", list(periodos), index=1)]
        st.caption("Cada número se compara con el período anterior del mismo largo.")

        ini, ini_ant = hace(n - 1), hace(2 * n - 1)
        corte = pd.Timestamp(ini)

        ventas = leer("""
            SELECT v.fecha, v.cantidad, v.total, v.producto_id AS pid, p.nombre, p.categoria
            FROM ventas v JOIN productos p ON p.id = v.producto_id
            WHERE v.fecha >= ?
        """, conn, params=(ini_ant,))
        ventas["dt"] = pd.to_datetime(ventas["fecha"], errors="coerce")
        ventas = ventas.dropna(subset=["dt"])
        costos = costos_ultimos(conn)
        ventas["costo"] = ventas["pid"].map(costos)
        ventas["ganancia"] = ventas["total"] - ventas["cantidad"] * ventas["costo"]
        act = ventas[ventas["dt"] >= corte].copy()
        ant = ventas[ventas["dt"] < corte].copy()

        tickets = leer("""
            SELECT estado, total, COALESCE(fecha_cobro, fecha) AS f FROM pendientes
            WHERE estado IN ('cobrado','anulado') AND COALESCE(fecha_cobro, fecha) >= ?
        """, conn, params=(ini_ant,))
        tickets["dt"] = pd.to_datetime(tickets["f"], errors="coerce")
        tk_act = tickets[(tickets["dt"] >= corte) & (tickets["estado"] == "cobrado")]
        tk_ant = tickets[(tickets["dt"] < corte) & (tickets["estado"] == "cobrado")]
        anulados = int(((tickets["dt"] >= corte) & (tickets["estado"] == "anulado")).sum())

        inv, dh = estadisticas_productos(conn)

        if act.empty:
            st.info("Aún no hay ventas en este período")
        else:
            def var(a, b):
                return f"{(a - b) / b * 100:+.0f}%" if b else None

            V, Va = act["total"].sum(), ant["total"].sum()
            K, Ka = act["cantidad"].sum(), ant["cantidad"].sum()
            T, Ta = len(tk_act), len(tk_ant)
            prom = V / T if T else 0
            prom_a = Va / Ta if Ta else 0
            pkg = V / K if K else 0
            pkg_a = Va / Ka if Ka else 0
            con_costo = act["costo"].notna()
            G = act.loc[con_costo, "ganancia"].sum()
            base = act.loc[con_costo, "total"].sum()
            margen = G / base * 100 if base else None

            # --- Indicadores ---
            r1 = st.columns(3)
            r1[0].metric("💰 Ventas", plata(V), var(V, Va))
            r1[1].metric("⚖️ Kilos", f"{K:.1f}", var(K, Ka))
            r1[2].metric("🧾 Tickets", T, var(T, Ta))
            r2 = st.columns(3)
            r2[0].metric("🎯 Ticket promedio", plata(prom), var(prom, prom_a))
            r2[1].metric("💲 Precio prom./kg", plata(pkg), var(pkg, pkg_a))
            r2[2].metric("📈 Ganancia estimada", plata(G) if base else "—",
                         f"margen {margen:.0f}%" if margen is not None else None, delta_color="off")
            if base and base < V:
                st.caption(f"Ganancia calculada sobre el {base / V * 100:.0f}% de las ventas "
                           "(solo productos con precio de compra registrado).")

            # --- Datos para gráficos y conclusiones ---
            idx = pd.date_range(corte, pd.Timestamp(hoy_str()), freq="D")
            por_dia = act.groupby(act["dt"].dt.normalize())["total"].sum().reindex(idx, fill_value=0)
            nombres_dia = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            sem = por_dia.groupby(por_dia.index.dayofweek).mean()
            horas = act.groupby(act["dt"].dt.hour)["total"].sum()

            prod = (act.groupby(["nombre", "categoria"])
                    .agg(ventas=("total", "sum"), kilos=("cantidad", "sum"))
                    .reset_index().sort_values("ventas", ascending=False))
            prod_ant = ant.groupby("nombre")["total"].sum()
            gp = act[con_costo].groupby("nombre").agg(g=("ganancia", "sum"), b=("total", "sum"))

            cat_act = act.groupby("categoria").agg(ventas=("total", "sum"), kilos=("cantidad", "sum"))
            cat_ant = ant.groupby("categoria")["total"].sum()
            gc = act[con_costo].groupby("categoria").agg(g=("ganancia", "sum"), b=("total", "sum"))

            vendidos = set(act["pid"])
            sin_mov = inv[(~inv["id"].isin(vendidos)) & (inv["stock"] > 0)]
            bajo = inv[inv["stock"] <= inv["minimo"]]

            # --- Conclusiones ---
            st.markdown("#### 🧠 Conclusiones para decidir")
            ideas = []
            if Va:
                cambio = (V - Va) / Va * 100
                ideas.append(f"Las ventas {'subieron' if cambio >= 0 else 'bajaron'} **{abs(cambio):.0f}%** frente al período anterior.")
            if sem.max() > 0:
                mejor, peor = int(sem.idxmax()), int(sem.idxmin())
                ideas.append(f"Tu mejor día es el **{nombres_dia[mejor]}** (promedio {plata(sem.max())}) y el más flojo el "
                             f"**{nombres_dia[peor]}** ({plata(sem.min())}). Ten más stock y apoyo el {nombres_dia[mejor].lower()}; "
                             f"usa el {nombres_dia[peor].lower()} para ofertas.")
            if not horas.empty:
                h = int(horas.idxmax())
                ideas.append(f"La hora de más venta es **{h:02d}:00–{h + 1:02d}:00** ({horas.max() / V * 100:.0f}% de las ventas).")
            if not prod.empty:
                top = prod.iloc[0]
                top3 = prod.head(3)["ventas"].sum() / V * 100
                ideas.append(f"El producto estrella es **{top['nombre']}** ({top['ventas'] / V * 100:.0f}% de las ventas). "
                             f"Los 3 primeros suman el **{top3:.0f}%**: nunca deben faltar.")
            if len(cat_act) and not cat_ant.empty:
                crec = {c: (cat_act.loc[c, 'ventas'] - cat_ant.get(c, 0)) / cat_ant.get(c, 0) * 100
                        for c in cat_act.index if cat_ant.get(c, 0) > 0}
                if crec:
                    cmax = max(crec, key=crec.get)
                    cmin = min(crec, key=crec.get)
                    if crec[cmax] > 0:
                        ideas.append(f"**{cmax}** es la sección que más crece ({crec[cmax]:+.0f}%).")
                    if crec[cmin] < 0:
                        ideas.append(f"**{cmin}** es la sección que más cae ({crec[cmin]:+.0f}%): revisa precio y calidad.")
            margen_bajo = gp[(gp["b"] > 0) & (gp["g"] / gp["b"] < 0.2)]
            if not margen_bajo.empty:
                ideas.append(f"Margen bajo (<20%) en: **{', '.join(margen_bajo.index)}**. Revisa costo o precio.")
            if not sin_mov.empty:
                plata_parada = (sin_mov["stock"] * sin_mov["precio"]).sum()
                ideas.append(f"**{len(sin_mov)}** producto(s) sin ventas en el período, con {plata(plata_parada)} en stock parado → mira 💡 Precios.")
            if not bajo.empty:
                ideas.append(f"**{len(bajo)}** producto(s) bajo el stock mínimo → mira 📋 Pedidos.")
            if anulados and (T + anulados):
                ideas.append(f"Se anularon **{anulados}** ticket(s) ({anulados / (T + anulados) * 100:.0f}% del total).")
            for i in ideas:
                st.markdown(f"- {i}")

            # --- Ventas por día ---
            st.markdown("#### 📅 Ventas por día")
            st.bar_chart(por_dia.to_frame("Ventas $"))
            st.caption(f"Promedio diario: {plata(por_dia.mean())} · Mejor día: {plata(por_dia.max())}")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🗓️ Promedio por día de la semana")
                sem_g = sem.copy()
                sem_g.index = [f"{i + 1} {nombres_dia[i][:3]}" for i in sem_g.index]
                st.bar_chart(sem_g.to_frame("Promedio $"))
            with c2:
                st.markdown("#### ⏰ Ventas por hora")
                horas_g = horas.copy()
                horas_g.index = [f"{h:02d}h" for h in horas_g.index]
                st.bar_chart(horas_g.to_frame("Ventas $"))

            # --- Por sección ---
            st.markdown("#### 🥩🐷🐔 Por sección")
            filas = []
            for c in cat_act.sort_values("ventas", ascending=False).index:
                v = cat_act.loc[c, "ventas"]
                filas.append({
                    "Sección": f"{ICONOS.get(c, '📦')} {c}",
                    "Ventas": plata(v),
                    "% del total": f"{v / V * 100:.0f}%",
                    "Kilos": round(cat_act.loc[c, "kilos"], 1),
                    "vs anterior": txt_tend((v - cat_ant.get(c, 0)) / cat_ant.get(c, 0) * 100) if cat_ant.get(c, 0) else "—",
                    "Margen": f"{gc.loc[c, 'g'] / gc.loc[c, 'b'] * 100:.0f}%" if c in gc.index and gc.loc[c, "b"] else "—",
                })
            st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)

            # --- Productos ---
            st.markdown("#### 🏆 Productos más vendidos")
            st.bar_chart(prod.head(8).set_index("nombre")[["ventas"]].rename(columns={"ventas": "Ventas $"}))
            filas = []
            for _, r in prod.head(10).iterrows():
                a = prod_ant.get(r["nombre"], 0)
                filas.append({
                    "Producto": r["nombre"],
                    "Sección": r["categoria"],
                    "Ventas": plata(r["ventas"]),
                    "% del total": f"{r['ventas'] / V * 100:.0f}%",
                    "Kilos": round(r["kilos"], 1),
                    "vs anterior": txt_tend((r["ventas"] - a) / a * 100) if a else "nuevo",
                    "Margen": f"{gp.loc[r['nombre'], 'g'] / gp.loc[r['nombre'], 'b'] * 100:.0f}%"
                              if r["nombre"] in gp.index and gp.loc[r["nombre"], "b"] else "—",
                })
            st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)

        # --- Inventario ---
        st.markdown("#### 📦 Inventario")
        valor_venta = (inv["stock"].clip(lower=0) * inv["precio"]).sum()
        valor_costo = (inv["stock"].clip(lower=0) * inv["costo"]).sum()
        c1, c2 = st.columns(2)
        c1.metric("Stock a precio venta", plata(valor_venta))
        c2.metric("Stock a costo", plata(valor_costo) if valor_costo else "—")
        c3, c4 = st.columns(2)
        c3.metric("Bajo el mínimo", int((inv["stock"] <= inv["minimo"]).sum()))
        c4.metric("Sin ventas en el período", int(((~inv["id"].isin(set(act["pid"]))) & (inv["stock"] > 0)).sum()))

        cobertura = inv[["categoria", "nombre", "stock", "prom_dia", "dias_stock"]].copy()
        cobertura["Días de stock"] = cobertura["dias_stock"].apply(txt_dias)
        cobertura = cobertura.sort_values("dias_stock", na_position="last")
        st.dataframe(
            cobertura.rename(columns={"categoria": "Sección", "nombre": "Producto", "stock": "Stock kg",
                                      "prom_dia": "Vende kg/día"})
                     .drop(columns=["dias_stock"])
                     .round({"Stock kg": 1, "Vende kg/día": 1}),
            width="stretch", hide_index=True
        )
        st.caption(f"Días de stock = cuántos días alcanza el stock al ritmo de venta de los últimos {dh} días.")

conn.close()
