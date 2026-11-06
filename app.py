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

    # Cola de ventas pendientes (carnicero → cajera)
    c.execute("""CREATE TABLE IF NOT EXISTS pendientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        items TEXT,
        total REAL,
        fecha TEXT,
        estado TEXT DEFAULT 'pendiente')""")

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

# ==================== APP ====================
st.set_page_config(page_title="Carnicería", page_icon="🥩", layout="wide")
init()

st.markdown("""
<style>
.stButton > button {
    height: 70px !important;
    font-size: 18px !important;
    font-weight: 800 !important;
    border-radius: 12px !important;
    background-color: #27ae60 !important;
    color: white !important;
    border: none !important;
}
.stButton > button:hover {
    background-color: #1e8449 !important;
}
div[data-testid="column"] .stButton > button {
    height: 65px !important;
    font-size: 16px !important;
}
</style>
""", unsafe_allow_html=True)

# Elegir modo
if "modo" not in st.session_state:
    st.session_state.modo = None

if st.session_state.modo is None:
    st.title("🥩 Sistema de Gestión - Carnicería")
    st.markdown("### ¿Quién está usando el sistema?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔪 MODO CARNICERO\n(Solo ventas)", use_container_width=True):
            st.session_state.modo = "carnicero"
            st.session_state.ticket = []
            st.session_state.cantidad_str = ""
            st.session_state.prod_sel = None
            st.rerun()
    with col2:
        if st.button("💵 MODO CAJA\n(Cobrar + gestión)", use_container_width=True):
            st.session_state.modo = "caja"
            st.rerun()
    st.stop()

# Botón para cambiar de modo
if st.sidebar.button("🔄 Cambiar de modo"):
    st.session_state.modo = None
    st.rerun()

conn = get_db()

# ============================================================
#                    MODO CARNICERO
# ============================================================
if st.session_state.modo == "carnicero":
    st.title("🔪 Modo Carnicero")

    if "ticket" not in st.session_state:
        st.session_state.ticket = []
    if "cantidad_str" not in st.session_state:
        st.session_state.cantidad_str = ""
    if "prod_sel" not in st.session_state:
        st.session_state.prod_sel = None

    prods = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    # --- Productos por categoría (botones grandes) ---
    st.subheader("1. Elige el producto")
    cats = {"Vacuno": "🥩", "Cerdo": "🐷", "Pollo": "🐔", "Otros": "📦"}
    for cat, icon in cats.items():
        lista = [p for p in prods if p["categoria"] == cat]
        if not lista:
            continue
        st.markdown(f"**{icon} {cat}**")
        cols = st.columns(4)
        for i, p in enumerate(lista):
            with cols[i % 4]:
                label = f"{p['nombre']}\n${p['precio']:,.0f}/kg"
                if st.button(label, key=f"p{p['id']}", use_container_width=True):
                    st.session_state.prod_sel = dict(p)
                    st.session_state.cantidad_str = ""
                    st.rerun()

    # --- Teclado numérico ---
    st.subheader("2. Ingresa los kilos")
    if st.session_state.prod_sel:
        st.info(f"Producto: **{st.session_state.prod_sel['nombre']}** — ${st.session_state.prod_sel['precio']:,.0f}/kg")
    else:
        st.warning("Primero elige un producto")

    st.markdown(f"### Cantidad: **{st.session_state.cantidad_str or '0'}** kg")

    # Teclado
    teclas = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        [".", "0", "⌫"]
    ]
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

    # Agregar al ticket
    if st.button("➕ AGREGAR AL TICKET", use_container_width=True):
        if not st.session_state.prod_sel:
            st.error("Elige un producto")
        elif not st.session_state.cantidad_str:
            st.error("Ingresa la cantidad")
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
                    st.success("Agregado al ticket")
                    st.rerun()
            except ValueError:
                st.error("Cantidad inválida")

    # --- Ticket actual ---
    st.subheader("🛒 Ticket actual")
    if not st.session_state.ticket:
        st.info("Sin productos aún")
    else:
        total = 0
        for i, item in enumerate(st.session_state.ticket):
            st.write(f"**{item['nombre']}** — {item['cantidad']:.2f} kg × ${item['precio']:,.0f} = **${item['subtotal']:,.0f}**")
            if st.button("❌ Quitar", key=f"qt{i}"):
                st.session_state.ticket.pop(i)
                st.rerun()
            total += item["subtotal"]
        st.markdown(f"## TOTAL: ${total:,.0f}")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📤 ENVIAR A CAJA", use_container_width=True, type="primary"):
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn.execute(
                    "INSERT INTO pendientes (items, total, fecha, estado) VALUES (?,?,?,?)",
                    (json.dumps(st.session_state.ticket), total, fecha, "pendiente")
                )
                conn.commit()
                st.session_state.ticket = []
                st.success("✅ Enviado a caja")
                st.rerun()
        with col_b:
            if st.button("🗑️ Cancelar ticket", use_container_width=True):
                st.session_state.ticket = []
                st.rerun()

# ============================================================
#                      MODO CAJA
# ============================================================
elif st.session_state.modo == "caja":
    st.title("💵 Modo Caja")

    menu = st.sidebar.radio("MENÚ CAJA", [
        "🧾 Cobrar pendientes",
        "🏠 Inicio",
        "📦 Productos",
        "📥 Comprar",
        "📋 Pedidos",
        "💡 Precios",
        "🚚 Proveedores",
        "🧾 Cierre de Caja",
        "🧮 Simulador",
        "📊 Análisis",
        "📈 Comparativo"
    ], label_visibility="collapsed")

    # ----- COBRAR PENDIENTES -----
    if menu == "🧾 Cobrar pendientes":
        st.header("🧾 Ventas pendientes del carnicero")

        pendientes = conn.execute(
            "SELECT * FROM pendientes WHERE estado='pendiente' ORDER BY id DESC"
        ).fetchall()

        if not pendientes:
            st.success("✅ No hay ventas pendientes")
        else:
            for pend in pendientes:
                items = json.loads(pend["items"])
                with st.container():
                    st.markdown(f"### Ticket #{pend['id']} — {pend['fecha']}")
                    for it in items:
                        st.write(f"• {it['nombre']}: {it['cantidad']:.2f} kg × ${it['precio']:,.0f} = ${it['subtotal']:,.0f}")
                    st.markdown(f"## TOTAL: ${pend['total']:,.0f}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"✅ COBRAR ${pend['total']:,.0f}", key=f"cob{pend['id']}", use_container_width=True):
                            # Registrar venta y descontar stock
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
                        if st.button("❌ Anular", key=f"an{pend['id']}", use_container_width=True):
                            conn.execute(
                                "UPDATE pendientes SET estado='anulado' WHERE id=?",
                                (pend["id"],)
                            )
                            conn.commit()
                            st.warning("Ticket anulado")
                            st.rerun()
                    st.divider()

    # ----- INICIO -----
    elif menu == "🏠 Inicio":
        st.header("Panel Principal")
        total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
        bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]
        hoy = datetime.now().strftime("%Y-%m-%d")
        ventas_hoy = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        pend_count = conn.execute("SELECT COUNT(*) FROM pendientes WHERE estado='pendiente'").fetchone()[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Productos", total)
        c2.metric("⚠️ Stock bajo", bajo)
        c3.metric("Ventas hoy", f"${ventas_hoy:,.0f}")
        c4.metric("⏳ Pendientes", pend_count)

        if pend_count > 0:
            st.warning(f"Hay **{pend_count}** ticket(s) esperando cobro")

        df_bajo = pd.read_sql("SELECT nombre, stock, minimo FROM productos WHERE stock <= minimo", conn)
        if not df_bajo.empty:
            st.subheader("Stock bajo")
            st.dataframe(df_bajo, use_container_width=True, hide_index=True)

    # ----- PRODUCTOS -----
    elif menu == "📦 Productos":
        st.header("📦 Productos")
        stickers = {"Vacuno": "🥩 VACUNO", "Cerdo": "🐷 CERDO", "Pollo": "🐔 POLLO", "Otros": "📦 OTROS"}
        for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
            df = pd.read_sql(
                "SELECT id, nombre, precio, stock, minimo FROM productos WHERE categoria=? ORDER BY nombre",
                conn, params=(cat,)
            )
            if not df.empty:
                st.markdown(f"### {stickers[cat]}")
                st.dataframe(df, use_container_width=True, hide_index=True)

        with st.expander("➕ Agregar producto"):
            with st.form("np"):
                n = st.text_input("Nombre")
                cat = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
                precio = st.number_input("Precio $/kg", min_value=0, step=100)
                stock = st.number_input("Stock kg", min_value=0.0, step=0.5)
                minimo = st.number_input("Mínimo", min_value=0.0, value=5.0, step=0.5)
                if st.form_submit_button("💾 GUARDAR") and n.strip():
                    conn.execute(
                        "INSERT INTO productos (nombre,categoria,precio,stock,minimo) VALUES (?,?,?,?,?)",
                        (n.strip(), cat, precio, stock, minimo)
                    )
                    conn.commit()
                    st.success("Guardado")
                    st.rerun()

        st.subheader("🗑️ Eliminar")
        prods = conn.execute("SELECT id, nombre, categoria FROM productos ORDER BY nombre").fetchall()
        if prods:
            opts = {f"{p['categoria']} - {p['nombre']}": p["id"] for p in prods}
            sel = st.selectbox("Producto", list(opts.keys()))
            if st.button("🗑️ ELIMINAR"):
                conn.execute("DELETE FROM productos WHERE id=?", (opts[sel],))
                conn.commit()
                st.success("Eliminado")
                st.rerun()

    # ----- COMPRAR -----
    elif menu == "📥 Comprar":
        st.header("📥 Compra de Mercadería")
        st.info("Al finalizar, el precio de venta se actualiza con **margen del 30%**.")
        if "carrito_c" not in st.session_state:
            st.session_state.carrito_c = []

        prods = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()
        proveeds = conn.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()

        col1, col2 = st.columns([2, 1])
        with col1:
            opts = {f"{p['categoria']} | {p['nombre']} | Stock: {p['stock']:.1f}": p for p in prods}
            sel = st.selectbox("Producto", list(opts.keys()), key="cp")
            prov_opts = {"Sin proveedor": None}
            prov_opts.update({p["nombre"]: p["id"] for p in proveeds})
            prov = st.selectbox("Proveedor", list(prov_opts.keys()))
            cant = st.number_input("Cantidad (kg)", min_value=0.1, step=0.5, value=5.0, key="cc")
            precio = st.number_input("Precio compra $/kg", min_value=0, step=50, key="cpr")
            if precio > 0:
                st.success(f"💡 Precio venta → **${round(precio*1.30):,.0f}/kg**")

            if st.button("➕ AGREGAR", use_container_width=True):
                p = opts[sel]
                pv = round(precio * 1.30) if precio > 0 else p["precio"]
                found = False
                for item in st.session_state.carrito_c:
                    if item["id"] == p["id"]:
                        item["cantidad"] += cant
                        item["precio"] = precio
                        item["subtotal"] = item["cantidad"] * precio
                        item["pv"] = pv
                        found = True
                        break
                if not found:
                    st.session_state.carrito_c.append({
                        "id": p["id"], "nombre": p["nombre"], "cantidad": cant,
                        "precio": precio, "subtotal": cant * precio, "pv": pv,
                        "prov": prov_opts[prov]
                    })
                st.success("Agregado")
                st.rerun()

        with col2:
            st.subheader("🛒 Carrito")
            if not st.session_state.carrito_c:
                st.info("Vacío")
            else:
                total = 0
                for i, item in enumerate(st.session_state.carrito_c):
                    st.write(f"**{item['nombre']}** — {item['cantidad']:.1f} kg")
                    if st.button("❌", key=f"qc{i}"):
                        st.session_state.carrito_c.pop(i)
                        st.rerun()
                    total += item["subtotal"]
                st.markdown(f"### TOTAL: ${total:,.0f}")
                if st.button("✅ FINALIZAR COMPRA", use_container_width=True):
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
                    st.success("Compra registrada")
                    st.rerun()

    # ----- PEDIDOS -----
    elif menu == "📋 Pedidos":
        st.header("📋 Pedidos Sugeridos (30 días)")
        df = pd.read_sql("""
            SELECT p.categoria, p.nombre, p.stock, p.minimo,
                   COALESCE(SUM(v.cantidad),0) as vendido_30d
            FROM productos p
            LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-30 days')
            GROUP BY p.id
        """, conn)
        df["proyeccion"] = df["vendido_30d"].round(1)
        df["sugerido"] = (df["proyeccion"] + df["minimo"] - df["stock"]).clip(lower=0).round(1)
        necesita = df[df["sugerido"] > 0].sort_values("sugerido", ascending=False)
        if necesita.empty:
            st.success("✅ No hay que pedir")
        else:
            st.dataframe(
                necesita[["categoria", "nombre", "stock", "vendido_30d", "proyeccion", "sugerido"]],
                use_container_width=True, hide_index=True
            )
            st.metric("Total kg sugeridos", f"{necesita['sugerido'].sum():.1f}")

    # ----- PRECIOS -----
    elif menu == "💡 Precios":
        st.header("💡 Sugerencias de Precios (30 días)")
        df = pd.read_sql("""
            SELECT p.id, p.nombre, p.categoria, p.precio, p.stock, p.minimo,
                   COALESCE(SUM(v.cantidad),0) as vend
            FROM productos p
            LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-30 days')
            GROUP BY p.id
        """, conn)
        hay = False
        for _, r in df.iterrows():
            dias = r["stock"] / (r["vend"] / 30) if r["vend"] > 0 else 999
            if dias > 45 or r["stock"] > r["minimo"] * 3:
                sug, acc = round(r["precio"] * 0.90), "Bajar -10%"
            elif dias > 30:
                sug, acc = round(r["precio"] * 0.95), "Bajar -5%"
            elif dias < 10 and r["stock"] <= r["minimo"]:
                sug, acc = round(r["precio"] * 1.05), "Subir +5%"
            else:
                continue
            hay = True
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{r['nombre']}** — ${r['precio']:,.0f} → **${sug:,.0f}** ({acc})")
            with col2:
                if st.button("✅", key=f"ap{r['id']}"):
                    conn.execute("UPDATE productos SET precio=? WHERE id=?", (sug, int(r["id"])))
                    conn.commit()
                    st.rerun()
        if not hay:
            st.success("Sin cambios sugeridos")

    # ----- PROVEEDORES -----
    elif menu == "🚚 Proveedores":
        st.header("🚚 Proveedores")
        with st.expander("➕ Nuevo"):
            with st.form("npv"):
                n = st.text_input("Nombre")
                t = st.text_input("Teléfono")
                no = st.text_input("Notas")
                if st.form_submit_button("Guardar") and n.strip():
                    conn.execute("INSERT INTO proveedores (nombre,telefono,notas) VALUES (?,?,?)", (n, t, no))
                    conn.commit()
                    st.rerun()
        st.dataframe(pd.read_sql("SELECT nombre, telefono, notas FROM proveedores", conn),
                     use_container_width=True, hide_index=True)

    # ----- CIERRE -----
    elif menu == "🧾 Cierre de Caja":
        st.header("🧾 Cierre de Caja")
        hoy = datetime.now().strftime("%Y-%m-%d")
        total = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        kilos = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        num = conn.execute("SELECT COUNT(*) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas hoy", f"${total:,.0f}")
        c2.metric("Kilos", f"{kilos:.1f}")
        c3.metric("Nº ventas", num)
        notas = st.text_input("Notas")
        if st.button("💾 GUARDAR CIERRE", use_container_width=True):
            conn.execute("DELETE FROM cierres WHERE fecha=?", (hoy,))
            conn.execute("INSERT INTO cierres (fecha,total,kilos,num,notas) VALUES (?,?,?,?,?)",
                         (hoy, total, kilos, num, notas))
            conn.commit()
            st.success("Guardado")
        st.dataframe(pd.read_sql("SELECT * FROM cierres ORDER BY fecha DESC LIMIT 10", conn),
                     use_container_width=True, hide_index=True)

    # ----- SIMULADOR -----
    elif menu == "🧮 Simulador":
        st.header("🧮 Simulador")
        prods = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
        opts = {p["nombre"]: p for p in prods}
        sel = st.selectbox("Producto", list(opts.keys()))
        p = opts[sel]
        nuevo = st.number_input("Nuevo precio", min_value=0, value=int(p["precio"]), step=50)
        extra = st.number_input("Kg extras en 30 días", min_value=0.0, step=1.0)
        vend30 = conn.execute(
            "SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE producto_id=? AND fecha >= date('now','-30 days')",
            (p["id"],)
        ).fetchone()[0]
        dif = (vend30 + extra) * nuevo - vend30 * p["precio"]
        st.write(f"Venta 30 días: **{vend30:.1f} kg**")
        st.write(f"Diferencia estimada: **{'+' if dif>=0 else ''}{dif:,.0f}**")

    # ----- ANÁLISIS -----
    elif menu == "📊 Análisis":
        st.header("📊 Análisis (30 días)")
        tV = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-30 days')").fetchone()[0]
        kV = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE fecha >= date('now','-30 days')").fetchone()[0]
        c1, c2 = st.columns(2)
        c1.metric("Ventas 30 días", f"${tV:,.0f}")
        c2.metric("Kilos", f"{kV:.1f}")
        top = pd.read_sql("""
            SELECT p.nombre, ROUND(SUM(v.cantidad),1) as kg
            FROM ventas v JOIN productos p ON v.producto_id=p.id
            WHERE v.fecha >= date('now','-30 days')
            GROUP BY v.producto_id ORDER BY kg DESC LIMIT 8
        """, conn)
        if not top.empty:
            st.bar_chart(top.set_index("nombre"))

    # ----- COMPARATIVO -----
    elif menu == "📈 Comparativo":
        st.header("📈 Comparativo")
        esta = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-7 days')").fetchone()[0]
        ant = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-14 days') AND fecha < date('now','-7 days')").fetchone()[0]
        st.write(f"Últimos 7 días: **${esta:,.0f}**")
        st.write(f"7 días anteriores: **${ant:,.0f}**")

conn.close()
