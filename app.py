import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

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

# Estilos: botones grandes, color y letra gruesa
st.markdown("""
<style>
.stButton > button {
    height: 70px !important;
    font-size: 20px !important;
    font-weight: 800 !important;
    border-radius: 14px !important;
    background-color: #27ae60 !important;
    color: white !important;
    border: none !important;
}
.stButton > button:hover {
    background-color: #1e8449 !important;
    color: white !important;
}
div[data-testid="stSidebar"] .stButton > button {
    background-color: #2c3e50 !important;
}
</style>
""", unsafe_allow_html=True)

st.title("🥩 Sistema de Gestión - Carnicería")

menu = st.sidebar.radio("MENÚ", [
    "🏠 Inicio",
    "📦 Productos",
    "💰 Vender",
    "📥 Comprar",
    "📋 Pedidos",
    "💡 Precios",
    "🚚 Proveedores",
    "🧾 Cierre de Caja",
    "🧮 Simulador",
    "📊 Análisis",
    "📈 Comparativo"
], label_visibility="collapsed")

conn = get_db()

# ---------- INICIO ----------
if menu == "🏠 Inicio":
    st.header("Panel Principal")

    total = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0]
    bajo = conn.execute("SELECT COUNT(*) FROM productos WHERE stock <= minimo").fetchone()[0]
    hoy = datetime.now().strftime("%Y-%m-%d")
    ventas_hoy = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
    inv = conn.execute("SELECT COALESCE(SUM(stock*precio),0) FROM productos").fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Productos", total)
    c2.metric("⚠️ Stock bajo", bajo)
    c3.metric("Ventas hoy", f"${ventas_hoy:,.0f}")
    c4.metric("Inventario $", f"${inv:,.0f}")

    st.subheader("🔔 Alertas")
    alertas = []

    df_bajo = pd.read_sql("SELECT nombre, stock, minimo FROM productos WHERE stock <= minimo", conn)
    for _, r in df_bajo.iterrows():
        alertas.append(f"🔴 Stock bajo: **{r['nombre']}** ({r['stock']:.1f} kg)")

    # Rotación basada en 30 días
    df_rot = pd.read_sql("""
        SELECT p.nombre, p.stock, p.minimo, COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p
        LEFT JOIN ventas v ON p.id = v.producto_id AND v.fecha >= date('now','-30 days')
        GROUP BY p.id
    """, conn)
    for _, r in df_rot.iterrows():
        if r["vend"] > 0:
            dias = r["stock"] / (r["vend"] / 30)
            if dias > 45 and r["stock"] > r["minimo"]:
                alertas.append(f"🟠 Baja rotación: **{r['nombre']}** (~{dias:.0f} días de stock)")

    if alertas:
        for a in alertas:
            st.warning(a)
    else:
        st.success("✅ Sin alertas")

    st.subheader("Stock bajo")
    if df_bajo.empty:
        st.success("Todo en orden")
    else:
        st.dataframe(df_bajo, use_container_width=True, hide_index=True)

    st.subheader("Costo de inventario por categoría")
    df_inv = pd.read_sql(
        "SELECT categoria, ROUND(SUM(stock*precio),0) as valor FROM productos GROUP BY categoria",
        conn
    )
    st.dataframe(df_inv, use_container_width=True, hide_index=True)

# ---------- PRODUCTOS ----------
elif menu == "📦 Productos":
    st.header("📦 Productos")

    # Stickers por categoría
    stickers = {
        "Vacuno": "🥩 VACUNO",
        "Cerdo": "🐷 CERDO",
        "Pollo": "🐔 POLLO",
        "Otros": "📦 OTROS"
    }

    for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
        df = pd.read_sql(
            "SELECT id, nombre, precio, stock, minimo FROM productos WHERE categoria=? ORDER BY nombre",
            conn, params=(cat,)
        )
        if not df.empty:
            st.markdown(f"### {stickers.get(cat, cat)}")
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.write("")

    with st.expander("➕ Agregar producto"):
        with st.form("nuevo_prod"):
            n = st.text_input("Nombre")
            cat = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
            precio = st.number_input("Precio $/kg", min_value=0, step=100)
            stock = st.number_input("Stock kg", min_value=0.0, step=0.5)
            minimo = st.number_input("Mínimo", min_value=0.0, value=5.0, step=0.5)
            if st.form_submit_button("💾 GUARDAR PRODUCTO") and n.strip():
                conn.execute(
                    "INSERT INTO productos (nombre,categoria,precio,stock,minimo) VALUES (?,?,?,?,?)",
                    (n.strip(), cat, precio, stock, minimo)
                )
                conn.commit()
                st.success("Guardado")
                st.rerun()

    st.subheader("🗑️ Eliminar producto")
    prods = conn.execute("SELECT id, nombre, categoria FROM productos ORDER BY categoria, nombre").fetchall()
    if prods:
        opts = {f"{p['categoria']} - {p['nombre']}": p["id"] for p in prods}
        sel = st.selectbox("Producto", list(opts.keys()))
        if st.button("🗑️ ELIMINAR", type="primary"):
            conn.execute("DELETE FROM productos WHERE id=?", (opts[sel],))
            conn.commit()
            st.success("Eliminado")
            st.rerun()

# ---------- VENDER ----------
elif menu == "💰 Vender":
    st.header("💰 Venta (varios productos)")
    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    prods = conn.execute("SELECT * FROM productos ORDER BY categoria, nombre").fetchall()

    col1, col2 = st.columns([2, 1])

    with col1:
        opts = {
            f"{p['categoria']} | {p['nombre']} | Stock: {p['stock']:.1f} | ${p['precio']:,.0f}": p
            for p in prods
        }
        sel = st.selectbox("Producto", list(opts.keys()))
        cant = st.number_input("Cantidad (kg)", min_value=0.1, step=0.1, value=1.0)

        if st.button("➕ AGREGAR AL CARRITO", use_container_width=True):
            p = opts[sel]
            if cant > p["stock"]:
                st.error(f"Stock insuficiente ({p['stock']:.1f} kg)")
            else:
                found = False
                for item in st.session_state.carrito:
                    if item["id"] == p["id"]:
                        item["cantidad"] += cant
                        item["subtotal"] = item["cantidad"] * item["precio"]
                        found = True
                        break
                if not found:
                    st.session_state.carrito.append({
                        "id": p["id"],
                        "nombre": p["nombre"],
                        "precio": p["precio"],
                        "cantidad": cant,
                        "subtotal": cant * p["precio"]
                    })
                st.success("Agregado")
                st.rerun()

    with col2:
        st.subheader("🛒 Carrito")
        if not st.session_state.carrito:
            st.info("Vacío")
        else:
            total = 0
            for i, item in enumerate(st.session_state.carrito):
                st.write(f"**{item['nombre']}** — {item['cantidad']:.2f} kg × ${item['precio']:,.0f} = **${item['subtotal']:,.0f}**")
                if st.button("❌", key=f"qv{i}"):
                    st.session_state.carrito.pop(i)
                    st.rerun()
                total += item["subtotal"]
            st.markdown(f"### TOTAL: ${total:,.0f}")

            if st.button("✅ FINALIZAR VENTA", use_container_width=True, type="primary"):
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                for item in st.session_state.carrito:
                    conn.execute(
                        "UPDATE productos SET stock = stock - ? WHERE id=?",
                        (item["cantidad"], item["id"])
                    )
                    conn.execute(
                        "INSERT INTO ventas (producto_id, cantidad, total, fecha) VALUES (?,?,?,?)",
                        (item["id"], item["cantidad"], item["subtotal"], fecha)
                    )
                conn.commit()
                st.session_state.carrito = []
                st.success(f"Venta registrada: ${total:,.0f}")
                st.rerun()

            if st.button("🗑️ VACIAR", use_container_width=True):
                st.session_state.carrito = []
                st.rerun()

# ---------- COMPRAR ----------
elif menu == "📥 Comprar":
    st.header("📥 Compra de Mercadería")
    st.info("Al finalizar, el precio de venta se actualiza automáticamente con **margen del 30%**.")

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
            st.success(f"💡 Precio venta se actualizará a **${round(precio*1.30):,.0f}/kg** (+30%)")

        if st.button("➕ AGREGAR AL CARRITO", use_container_width=True):
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
                st.write(f"**{item['nombre']}** — {item['cantidad']:.1f} kg × ${item['precio']:,.0f}")
                st.caption(f"→ Venta: ${item['pv']:,.0f}/kg")
                if st.button("❌", key=f"qc{i}"):
                    st.session_state.carrito_c.pop(i)
                    st.rerun()
                total += item["subtotal"]
            st.markdown(f"### TOTAL: ${total:,.0f}")

            if st.button("✅ FINALIZAR COMPRA", use_container_width=True, type="primary"):
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                for item in st.session_state.carrito_c:
                    conn.execute(
                        "UPDATE productos SET stock = stock + ?, precio = ? WHERE id = ?",
                        (item["cantidad"], item["pv"], item["id"])
                    )
                    conn.execute(
                        "INSERT INTO compras (producto_id, cantidad, precio, fecha, proveedor_id) VALUES (?,?,?,?,?)",
                        (item["id"], item["cantidad"], item["precio"], fecha, item["prov"])
                    )
                conn.commit()
                st.session_state.carrito_c = []
                st.success(f"Compra registrada ${total:,.0f} — Precios actualizados")
                st.rerun()

            if st.button("🗑️ VACIAR", use_container_width=True):
                st.session_state.carrito_c = []
                st.rerun()

# ---------- PEDIDOS (basado en 30 días) ----------
elif menu == "📋 Pedidos":
    st.header("📋 Pedidos Sugeridos")
    st.write("Basado en las ventas de los **últimos 30 días**. Calcula cuánto pedir para cubrir los próximos 30 días + stock mínimo.")

    df = pd.read_sql("""
        SELECT p.categoria, p.nombre, p.stock, p.minimo,
               COALESCE(SUM(v.cantidad),0) as vendido_30d
        FROM productos p
        LEFT JOIN ventas v ON p.id = v.producto_id AND v.fecha >= date('now','-30 days')
        GROUP BY p.id
        ORDER BY p.categoria, p.nombre
    """, conn)

    # Proyección: lo que se vendió en 30 días se proyecta para los próximos 30
    df["proyeccion_30d"] = df["vendido_30d"].round(1)
    df["sugerido"] = (df["proyeccion_30d"] + df["minimo"] - df["stock"]).clip(lower=0).round(1)

    necesita = df[df["sugerido"] > 0].sort_values("sugerido", ascending=False)

    if necesita.empty:
        st.success("✅ No hay productos que necesiten reposición")
    else:
        st.dataframe(
            necesita[["categoria", "nombre", "stock", "vendido_30d", "proyeccion_30d", "sugerido"]].rename(columns={
                "categoria": "Categoría",
                "nombre": "Producto",
                "stock": "Stock actual",
                "vendido_30d": "Vendido últimos 30 días",
                "proyeccion_30d": "Proyección próximos 30 días",
                "sugerido": "Sugerido comprar (kg)"
            }),
            use_container_width=True,
            hide_index=True
        )
        st.metric("Total kg sugeridos a comprar", f"{necesita['sugerido'].sum():.1f} kg")

# ---------- PRECIOS (basado en 30 días) ----------
elif menu == "💡 Precios":
    st.header("💡 Sugerencias de Precios")
    st.write("Análisis basado en ventas de los **últimos 30 días**.")

    df = pd.read_sql("""
        SELECT p.id, p.nombre, p.categoria, p.precio, p.stock, p.minimo,
               COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p
        LEFT JOIN ventas v ON p.id = v.producto_id AND v.fecha >= date('now','-30 days')
        GROUP BY p.id
    """, conn)

    hay = False
    for _, r in df.iterrows():
        dias = r["stock"] / (r["vend"] / 30) if r["vend"] > 0 else 999
        if dias > 45 or r["stock"] > r["minimo"] * 3:
            sug, acc, prio = round(r["precio"] * 0.90), "Bajar -10%", "Alta"
        elif dias > 30:
            sug, acc, prio = round(r["precio"] * 0.95), "Bajar -5%", "Media"
        elif dias < 10 and r["stock"] <= r["minimo"]:
            sug, acc, prio = round(r["precio"] * 1.05), "Subir +5%", "Oportunidad"
        else:
            continue

        hay = True
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{r['categoria']} − {r['nombre']}** ({prio})")
            st.caption(f"Stock: {r['stock']:.1f} kg | Días de stock: {dias if dias < 999 else 'Sin ventas'}")
            st.write(f"${r['precio']:,.0f} → **${sug:,.0f}** ({acc})")
        with col2:
            if st.button("✅ APLICAR", key=f"ap{r['id']}"):
                conn.execute("UPDATE productos SET precio=? WHERE id=?", (sug, int(r["id"])))
                conn.commit()
                st.success("Actualizado")
                st.rerun()
        st.divider()

    if not hay:
        st.success("Sin cambios de precio sugeridos")

# ---------- PROVEEDORES ----------
elif menu == "🚚 Proveedores":
    st.header("🚚 Proveedores")
    with st.expander("➕ Nuevo proveedor"):
        with st.form("np"):
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono")
            no = st.text_input("Notas")
            if st.form_submit_button("💾 GUARDAR") and n.strip():
                conn.execute(
                    "INSERT INTO proveedores (nombre, telefono, notas) VALUES (?,?,?)",
                    (n, t, no)
                )
                conn.commit()
                st.success("Guardado")
                st.rerun()

    st.dataframe(
        pd.read_sql("SELECT nombre, telefono, notas FROM proveedores", conn),
        use_container_width=True, hide_index=True
    )

    st.subheader("Historial de precios de compra")
    df = pd.read_sql("""
        SELECT c.fecha, p.nombre, c.precio, c.cantidad
        FROM compras c JOIN productos p ON c.producto_id = p.id
        ORDER BY c.fecha DESC LIMIT 20
    """, conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- CIERRE ----------
elif menu == "🧾 Cierre de Caja":
    st.header("🧾 Cierre de Caja")
    hoy = datetime.now().strftime("%Y-%m-%d")
    total = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)
    ).fetchone()[0]
    kilos = conn.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE date(fecha)=?", (hoy,)
    ).fetchone()[0]
    num = conn.execute(
        "SELECT COUNT(*) FROM ventas WHERE date(fecha)=?", (hoy,)
    ).fetchone()[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas hoy", f"${total:,.0f}")
    c2.metric("Kilos", f"{kilos:.1f}")
    c3.metric("Nº ventas", num)

    notas = st.text_input("Notas del día")
    if st.button("💾 GUARDAR CIERRE", use_container_width=True):
        conn.execute("DELETE FROM cierres WHERE fecha=?", (hoy,))
        conn.execute(
            "INSERT INTO cierres (fecha, total, kilos, num, notas) VALUES (?,?,?,?,?)",
            (hoy, total, kilos, num, notas)
        )
        conn.commit()
        st.success("Cierre guardado")

    st.subheader("Historial")
    st.dataframe(
        pd.read_sql("SELECT * FROM cierres ORDER BY fecha DESC LIMIT 15", conn),
        use_container_width=True, hide_index=True
    )

# ---------- SIMULADOR ----------
elif menu == "🧮 Simulador":
    st.header("🧮 Simulador de Precios")
    prods = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    opts = {p["nombre"]: p for p in prods}
    sel = st.selectbox("Producto", list(opts.keys()))
    p = opts[sel]
    nuevo = st.number_input("Nuevo precio $/kg", min_value=0, value=int(p["precio"]), step=50)
    extra = st.number_input("Kg extras que venderías en 30 días", min_value=0.0, step=1.0)

    vend30 = conn.execute("""
        SELECT COALESCE(SUM(cantidad),0) FROM ventas
        WHERE producto_id=? AND fecha >= date('now','-30 days')
    """, (p["id"],)).fetchone()[0]

    ing_act = vend30 * p["precio"]
    ing_nuevo = (vend30 + extra) * nuevo
    dif = ing_nuevo - ing_act

    st.write(f"Venta últimos 30 días: **{vend30:.1f} kg**")
    st.write(f"Ingreso actual estimado: **${ing_act:,.0f}**")
    st.write(f"Ingreso con nuevo precio: **${ing_nuevo:,.0f}**")
    st.write(f"Diferencia: **{'+' if dif >= 0 else ''}{dif:,.0f}**")

# ---------- ANÁLISIS (30 días) ----------
elif menu == "📊 Análisis":
    st.header("📊 Análisis (últimos 30 días)")

    tV = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-30 days')"
    ).fetchone()[0]
    kV = conn.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM ventas WHERE fecha >= date('now','-30 days')"
    ).fetchone()[0]
    tC = conn.execute(
        "SELECT COALESCE(SUM(cantidad*precio),0) FROM compras WHERE fecha >= date('now','-30 days')"
    ).fetchone()[0]
    kC = conn.execute(
        "SELECT COALESCE(SUM(cantidad),0) FROM compras WHERE fecha >= date('now','-30 days')"
    ).fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas 30 días", f"${tV:,.0f}")
    c2.metric("Kilos vendidos", f"{kV:.1f}")
    c3.metric("Compras 30 días", f"${tC:,.0f}")
    c4.metric("Kilos comprados", f"{kC:.1f}")

    st.subheader("⭐ Estrellas vs 🐌 Problemas (30 días)")
    df = pd.read_sql("""
        SELECT p.nombre, p.stock, COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p
        LEFT JOIN ventas v ON p.id = v.producto_id AND v.fecha >= date('now','-30 days')
        GROUP BY p.id
    """, conn)
    col1, col2 = st.columns(2)
    with col1:
        st.write("Más vendidos")
        st.dataframe(df.nlargest(5, "vend")[["nombre", "vend"]], use_container_width=True, hide_index=True)
    with col2:
        st.write("Menos rotación (con stock)")
        st.dataframe(
            df[df["stock"] > 0].nsmallest(5, "vend")[["nombre", "vend", "stock"]],
            use_container_width=True, hide_index=True
        )

    st.subheader("Más vendidos (kg) — últimos 30 días")
    top = pd.read_sql("""
        SELECT p.nombre, ROUND(SUM(v.cantidad),1) as kg
        FROM ventas v JOIN productos p ON v.producto_id = p.id
        WHERE v.fecha >= date('now','-30 days')
        GROUP BY v.producto_id ORDER BY kg DESC LIMIT 8
    """, conn)
    if not top.empty:
        st.bar_chart(top.set_index("nombre"))
    else:
        st.info("Aún no hay ventas en los últimos 30 días")

    st.subheader("Margen real")
    margen = pd.read_sql("""
        SELECT p.nombre, p.precio as venta,
               (SELECT precio FROM compras WHERE producto_id = p.id ORDER BY fecha DESC LIMIT 1) as costo
        FROM productos p
    """, conn)
    margen = margen.dropna()
    if not margen.empty:
        margen["margen_%"] = ((margen["venta"] - margen["costo"]) / margen["venta"] * 100).round(1)
        st.dataframe(margen, use_container_width=True, hide_index=True)

# ---------- COMPARATIVO ----------
elif menu == "📈 Comparativo":
    st.header("📈 Comparativo de Períodos")
    esta_sem = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-7 days')"
    ).fetchone()[0]
    sem_ant = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-14 days') AND fecha < date('now','-7 days')"
    ).fetchone()[0]
    este_mes = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m','now')"
    ).fetchone()[0]
    mes_ant = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM ventas WHERE strftime('%Y-%m', fecha) = strftime('%Y-%m','now','-1 month')"
    ).fetchone()[0]

    def var(a, b):
        return "—" if b == 0 else f"{((a - b) / b * 100):+.1f}%"

    st.write(f"**Últimos 7 días:** ${esta_sem:,.0f}  |  **7 anteriores:** ${sem_ant:,.0f}  |  Var: {var(esta_sem, sem_ant)}")
    st.write(f"**Este mes:** ${este_mes:,.0f}  |  **Mes pasado:** ${mes_ant:,.0f}  |  Var: {var(este_mes, mes_ant)}")

conn.close()
