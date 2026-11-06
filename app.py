import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import json

# ==================== BASE DE DATOS ====================
def get_db():
    conn = sqlite3.connect("carniceria.db")
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT, categoria TEXT, precio REAL, stock REAL, minimo REAL)""")

    c.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER, cantidad REAL, total REAL, fecha TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER, cantidad REAL, precio REAL, fecha TEXT, proveedor_id INTEGER)""")

    c.execute("""CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT, telefono TEXT, notas TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS cierres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT, total REAL, kilos REAL, num INTEGER, notas TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS pendientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        items TEXT, total REAL, fecha TEXT, estado TEXT DEFAULT 'pendiente')""")

    try:
        c.execute("ALTER TABLE compras ADD COLUMN proveedor_id INTEGER")
    except Exception:
        pass

    if c.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0:
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
        c.executemany(
            "INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)",
            datos
        )

    if c.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO proveedores (nombre, telefono, notas) VALUES (?,?,?)",
            [
                ("Frigorífico Central", "912345678", "Vacuno fijo"),
                ("Carnes del Sur", "987654321", "Cerdo principal"),
                ("Avícola Los Andes", "945678123", "Pollo"),
            ]
        )

    conn.commit()
    conn.close()

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
        if st.button("🔪  CARNICERO\n\nArmar pedidos", use_container_width=True):
            st.session_state.modo = "carnicero"
            st.session_state.ticket = []
            st.session_state.cantidad_str = ""
            st.session_state.prod_sel = None
            st.rerun()
    with col2:
        if st.button("💵  CAJA\n\nCobrar y gestionar", use_container_width=True):
            st.session_state.modo = "caja"
            st.rerun()
    st.stop()

# Botón cambiar modo
st.sidebar.markdown("### 🔄 Cambiar modo")
if st.sidebar.button("Volver al inicio", use_container_width=True):
    st.session_state.modo = None
    st.rerun()

conn = get_db()

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
                if st.button(label, key=f"p{p['id']}", use_container_width=True):
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
    st.markdown(f"<div class='big-total'>{cantidad_mostrar} kg</div>", unsafe_allow_html=True)

    # Teclado
    teclas = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], [".", "0", "⌫"]]
    for fila in teclas:
        cols = st.columns(3)
        for i, t in enumerate(fila):
            with cols[i]:
                if st.button(t, key=f"k{t}", use_container_width=True):
                    if t == "⌫":
                        st.session_state.cantidad_str = st.session_state.cantidad_str[:-1]
                    else:
                        st.session_state.cantidad_str += t
                    st.rerun()

    if st.button("➕  AGREGAR AL TICKET", use_container_width=True):
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
            if st.button("📤  ENVIAR A CAJA", use_container_width=True):
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
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
            if st.button("🗑️  Cancelar", use_container_width=True):
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
        "🚚 Proveedores",
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
                    if st.button(f"✅  COBRAR  ${pend['total']:,.0f}", key=f"cob{pend['id']}", use_container_width=True):
                        for it in items:
                            conn.execute(
                                "UPDATE productos SET stock = stock - ? WHERE id=?",
                                (it["cantidad"], it["id"])
                            )
                            conn.execute(
                                "INSERT INTO ventas (producto_id, cantidad, total, fecha) VALUES (?,?,?,?)",
                                (it["id"], it["cantidad"], it["subtotal"], pend["fecha"])
                            )
                        conn.execute(
                            "UPDATE pendientes SET estado='cobrado' WHERE id=?",
                            (pend["id"],)
                        )
                        conn.commit()
                        st.success(f"Cobrado ${pend['total']:,.0f}")
                        st.rerun()
                with col2:
                    if st.button("❌  Anular", key=f"an{pend['id']}", use_container_width=True):
                        conn.execute(
                            "UPDATE pendientes SET estado='anulado' WHERE id=?",
                            (pend["id"],)
                        )
                        conn.commit()
                        st.warning("Anulado")
                        st.rerun()
                st.markdown("---")

    # ----- RESUMEN -----
    elif menu == "🏠 Resumen":
        st.markdown("### 🏠 Resumen del día")
        hoy = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        kilos = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        num = conn.execute("SELECT COUNT(*) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
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
            df = pd.read_sql("SELECT nombre, stock, minimo FROM productos WHERE stock <= minimo", conn)
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ----- PRODUCTOS -----
    elif menu == "📦 Productos":
        st.markdown("### 📦 Productos")
        stickers = {"Vacuno": "🥩 VACUNO", "Cerdo": "🐷 CERDO", "Pollo": "🐔 POLLO", "Otros": "📦 OTROS"}
        for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
            df = pd.read_sql(
                "SELECT nombre, precio, stock, minimo FROM productos WHERE categoria=? ORDER BY nombre",
                conn, params=(cat,)
            )
            if not df.empty:
                st.markdown(f"#### {stickers[cat]}")
                st.dataframe(df, use_container_width=True, hide_index=True)

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
        proveeds = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()

        col1, col2 = st.columns([2, 1])
        with col1:
            opts = {f"{p['nombre']} (stock {p['stock']:.1f})": p for p in prods}
            sel = st.selectbox("Producto", list(opts.keys()))
            prov_opts = {"Sin proveedor": None}
            prov_opts.update({p["nombre"]: p["id"] for p in proveeds})
            prov = st.selectbox("Proveedor", list(prov_opts.keys()))
            cant = st.number_input("Kilos que entran", min_value=0.1, step=0.5, value=5.0)
            precio = st.number_input("Precio compra $/kg", min_value=0, step=50)
            if precio > 0:
                st.success(f"Precio venta quedará en **${round(precio*1.3):,.0f}/kg**")

            if st.button("➕ Agregar", use_container_width=True):
                p = opts[sel]
                pv = round(precio * 1.3) if precio > 0 else p["precio"]
                st.session_state.carrito_c.append({
                    "id": p["id"], "nombre": p["nombre"], "cantidad": cant,
                    "precio": precio, "subtotal": cant * precio, "pv": pv,
                    "prov": prov_opts[prov]
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
                if st.button("✅ Guardar compra", use_container_width=True):
                    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                    for item in st.session_state.carrito_c:
                        conn.execute(
                            "UPDATE productos SET stock=stock+?, precio=? WHERE id=?",
                            (item["cantidad"], item["pv"], item["id"])
                        )
                        conn.execute(
                            "INSERT INTO compras (producto_id,cantidad,precio,fecha,proveedor_id) VALUES (?,?,?,?,?)",
                            (item["id"], item["cantidad"], item["precio"], fecha, item["prov"])
                        )
                    conn.commit()
                    st.session_state.carrito_c = []
                    st.success("Compra guardada")
                    st.rerun()

    # ----- PEDIDOS -----
    elif menu == "📋 Pedidos":
        st.markdown("### 📋 Qué conviene pedir")
        st.caption("Basado en ventas de los últimos 30 días")
        df = pd.read_sql("""
            SELECT p.categoria, p.nombre, p.stock, p.minimo,
                   COALESCE(SUM(v.cantidad),0) as vendido
            FROM productos p
            LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-30 days')
            GROUP BY p.id
        """, conn)
        df["sugerido"] = (df["vendido"] + df["minimo"] - df["stock"]).clip(lower=0).round(1)
        necesita = df[df["sugerido"] > 0].sort_values("sugerido", ascending=False)
        if necesita.empty:
            st.success("✅ No hay que pedir nada por ahora")
        else:
            st.dataframe(
                necesita[["categoria", "nombre", "stock", "vendido", "sugerido"]].rename(columns={
                    "categoria": "Categoría", "nombre": "Producto",
                    "stock": "Stock", "vendido": "Vendió 30d", "sugerido": "Pedir (kg)"
                }),
                use_container_width=True, hide_index=True
            )
            st.metric("Total a pedir", f"{necesita['sugerido'].sum():.1f} kg")

    # ----- PRECIOS -----
    elif menu == "💡 Precios":
        st.markdown("### 💡 Ajustes de precio sugeridos")
        df = pd.read_sql("""
            SELECT p.id, p.nombre, p.precio, p.stock, p.minimo,
                   COALESCE(SUM(v.cantidad),0) as vend
            FROM productos p
            LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-30 days')
            GROUP BY p.id
        """, conn)
        hay = False
        for _, r in df.iterrows():
            dias = r["stock"] / (r["vend"] / 30) if r["vend"] > 0 else 999
            if dias > 45 or r["stock"] > r["minimo"] * 3:
                sug, acc = round(r["precio"] * 0.90), "Bajar 10%"
            elif dias > 30:
                sug, acc = round(r["precio"] * 0.95), "Bajar 5%"
            elif dias < 10 and r["stock"] <= r["minimo"]:
                sug, acc = round(r["precio"] * 1.05), "Subir 5%"
            else:
                continue
            hay = True
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{r['nombre']}**  ${r['precio']:,.0f} → **${sug:,.0f}** ({acc})")
            with col2:
                if st.button("Aplicar", key=f"ap{r['id']}"):
                    conn.execute("UPDATE productos SET precio=? WHERE id=?", (sug, int(r["id"])))
                    conn.commit()
                    st.rerun()
        if not hay:
            st.success("No hay cambios recomendados")

    # ----- PROVEEDORES -----
    elif menu == "🚚 Proveedores":
        st.markdown("### 🚚 Proveedores")
        with st.expander("➕ Nuevo proveedor"):
            with st.form("npv"):
                n = st.text_input("Nombre")
                t = st.text_input("Teléfono")
                no = st.text_input("Notas")
                if st.form_submit_button("Guardar") and n.strip():
                    conn.execute("INSERT INTO proveedores (nombre,telefono,notas) VALUES (?,?,?)", (n, t, no))
                    conn.commit()
                    st.rerun()
        st.dataframe(
            pd.read_sql("SELECT nombre, telefono, notas FROM proveedores", conn),
            use_container_width=True, hide_index=True
        )

    # ----- CIERRE -----
    elif menu == "🧾 Cierre de Caja":
        st.markdown("### 🧾 Cierre de caja")
        hoy = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        kilos = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        num = conn.execute("SELECT COUNT(*) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]

        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas", f"${total:,.0f}")
        c2.metric("Kilos", f"{kilos:.1f}")
        c3.metric("Tickets", num)

        notas = st.text_input("Notas del día (opcional)")
        if st.button("💾 Guardar cierre", use_container_width=True):
            conn.execute("DELETE FROM cierres WHERE fecha=?", (hoy,))
            conn.execute(
                "INSERT INTO cierres (fecha,total,kilos,num,notas) VALUES (?,?,?,?,?)",
                (hoy, total, kilos, num, notas)
            )
            conn.commit()
            st.success("Cierre guardado")

        st.markdown("#### Historial")
        st.dataframe(
            pd.read_sql("SELECT fecha, total, kilos, num, notas FROM cierres ORDER BY fecha DESC LIMIT 10", conn),
            use_container_width=True, hide_index=True
        )

    # ----- ANÁLISIS -----
    elif menu == "📊 Análisis":
        st.markdown("### 📊 Análisis últimos 30 días")
        tV = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-30 days')").fetchone()[0]
        kV = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE fecha >= date('now','-30 days')").fetchone()[0]
        c1, c2 = st.columns(2)
        c1.metric("Ventas", f"${tV:,.0f}")
        c2.metric("Kilos", f"{kV:.1f}")

        top = pd.read_sql("""
            SELECT p.nombre, ROUND(SUM(v.cantidad),1) as kg
            FROM ventas v JOIN productos p ON v.producto_id=p.id
            WHERE v.fecha >= date('now','-30 days')
            GROUP BY v.producto_id ORDER BY kg DESC LIMIT 8
        """, conn)
        if not top.empty:
            st.markdown("#### Más vendidos")
            st.bar_chart(top.set_index("nombre"))
        else:
            st.info("Aún no hay ventas en los últimos 30 días")

conn.close()
