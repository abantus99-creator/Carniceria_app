import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import qrcode
from io import BytesIO

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
        producto_id INTEGER, cantidad REAL, total REAL, fecha TEXT, cliente_id INTEGER)""")

    c.execute("""CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER, cantidad REAL, precio REAL, fecha TEXT, proveedor_id INTEGER)""")

    c.execute("""CREATE TABLE IF NOT EXISTS mermas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER, cantidad REAL, motivo TEXT, costo REAL, fecha TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS proveedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT, telefono TEXT, notas TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT, telefono TEXT, saldo REAL DEFAULT 0)""")

    c.execute("""CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER, nombre TEXT, cantidad REAL, lote TEXT, caducidad TEXT, fecha TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS cierres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT, total REAL, kilos REAL, num INTEGER, notas TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS config (
        clave TEXT PRIMARY KEY, valor TEXT)""")

    # Datos iniciales
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
        c.executemany("INSERT INTO productos (nombre, categoria, precio, stock, minimo) VALUES (?,?,?,?,?)", datos)

    if c.execute("SELECT COUNT(*) FROM proveedores").fetchone()[0] == 0:
        c.executemany("INSERT INTO proveedores (nombre, telefono, notas) VALUES (?,?,?)", [
            ("Frigorífico Central", "912345678", "Vacuno fijo"),
            ("Carnes del Sur", "987654321", "Cerdo principal"),
            ("Avícola Los Andes", "945678123", "Pollo"),
        ])

    conn.commit()
    conn.close()

def generar_qr(texto):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def get_meta():
    conn = get_db()
    row = conn.execute("SELECT valor FROM config WHERE clave='meta_dia'").fetchone()
    conn.close()
    return float(row["valor"]) if row else 0

def set_meta(valor):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO config (clave, valor) VALUES ('meta_dia', ?)", (str(valor),))
    conn.commit()
    conn.close()

# ==================== APP ====================
st.set_page_config(page_title="Carnicería", page_icon="🥩", layout="wide")
init()

st.markdown("""
<style>
.stButton > button { height: 52px; font-size: 16px !important; font-weight: bold; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("🥩 Sistema Completo - Carnicería")

menu = st.sidebar.radio("MENÚ", [
    "🏠 Inicio",
    "📦 Productos",
    "💰 Vender",
    "📥 Comprar",
    "📋 Pedidos",
    "💡 Precios",
    "⚠️ Mermas",
    "📅 Lotes / Caducidad",
    "🚚 Proveedores",
    "👥 Clientes / Fiados",
    "🧾 Cierre de Caja",
    "🎯 Metas",
    "🧮 Simulador",
    "📊 Análisis",
    "📈 Comparativo",
    "📱 QR",
    "⬇️ Exportar"
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

    # Baja rotación
    df_rot = pd.read_sql("""
        SELECT p.nombre, p.stock, p.minimo, COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-90 days')
        GROUP BY p.id
    """, conn)
    for _, r in df_rot.iterrows():
        if r["vend"] > 0:
            dias = r["stock"] / (r["vend"] / 90)
            if dias > 45 and r["stock"] > r["minimo"]:
                alertas.append(f"🟠 Baja rotación: **{r['nombre']}** (~{dias:.0f} días de stock)")

    # Por vencer
    df_venc = pd.read_sql("SELECT nombre, caducidad FROM lotes WHERE caducidad IS NOT NULL AND caducidad != '' AND date(caducidad) <= date('now','+7 days') AND date(caducidad) >= date('now')", conn)
    for _, r in df_venc.iterrows():
        alertas.append(f"🟡 Por vencer: **{r['nombre']}** ({r['caducidad']})")

    # Fiados
    df_fiado = pd.read_sql("SELECT nombre, saldo FROM clientes WHERE saldo > 0", conn)
    for _, r in df_fiado.iterrows():
        alertas.append(f"💳 Fiado: **{r['nombre']}** debe ${r['saldo']:,.0f}")

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
    df_inv = pd.read_sql("SELECT categoria, ROUND(SUM(stock*precio),0) as valor FROM productos GROUP BY categoria", conn)
    st.dataframe(df_inv, use_container_width=True, hide_index=True)

# ---------- PRODUCTOS ----------
elif menu == "📦 Productos":
    st.header("📦 Productos")
    for cat in ["Vacuno", "Cerdo", "Pollo", "Otros"]:
        df = pd.read_sql("SELECT id, nombre, precio, stock, minimo FROM productos WHERE categoria=? ORDER BY nombre", conn, params=(cat,))
        if not df.empty:
            st.subheader(f"🔹 {cat}")
            st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("➕ Agregar producto"):
        with st.form("nuevo_prod"):
            n = st.text_input("Nombre")
            cat = st.selectbox("Categoría", ["Vacuno", "Cerdo", "Pollo", "Otros"])
            precio = st.number_input("Precio $/kg", min_value=0, step=100)
            stock = st.number_input("Stock kg", min_value=0.0, step=0.5)
            minimo = st.number_input("Mínimo", min_value=0.0, value=5.0, step=0.5)
            if st.form_submit_button("💾 Guardar") and n.strip():
                conn.execute("INSERT INTO productos (nombre,categoria,precio,stock,minimo) VALUES (?,?,?,?,?)",
                             (n.strip(), cat, precio, stock, minimo))
                conn.commit()
                st.success("Guardado")
                st.rerun()

    st.subheader("🗑️ Eliminar")
    prods = conn.execute("SELECT id, nombre, categoria FROM productos ORDER BY categoria, nombre").fetchall()
    if prods:
        opts = {f"{p['categoria']} - {p['nombre']}": p["id"] for p in prods}
        sel = st.selectbox("Producto", list(opts.keys()))
        if st.button("🗑️ Eliminar", type="primary"):
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
    clientes = conn.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()

    col1, col2 = st.columns([2, 1])
    with col1:
        opts = {f"{p['categoria']} | {p['nombre']} | Stock: {p['stock']:.1f} | ${p['precio']:,.0f}": p for p in prods}
        sel = st.selectbox("Producto", list(opts.keys()))
        cant = st.number_input("Cantidad (kg)", min_value=0.1, step=0.1, value=1.0)
        cli_opts = {"Mostrador / Contado": None}
        cli_opts.update({f"{c['nombre']} (debe ${c['saldo']:,.0f})": c["id"] for c in clientes})
        cli = st.selectbox("Cliente", list(cli_opts.keys()))

        if st.button("➕ Agregar al carrito", use_container_width=True):
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
                        "id": p["id"], "nombre": p["nombre"], "precio": p["precio"],
                        "cantidad": cant, "subtotal": cant * p["precio"]
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
                cli_id = cli_opts[cli]
                for item in st.session_state.carrito:
                    conn.execute("UPDATE productos SET stock = stock - ? WHERE id=?", (item["cantidad"], item["id"]))
                    conn.execute("INSERT INTO ventas (producto_id,cantidad,total,fecha,cliente_id) VALUES (?,?,?,?,?)",
                                 (item["id"], item["cantidad"], item["subtotal"], fecha, cli_id))
                if cli_id:
                    conn.execute("UPDATE clientes SET saldo = saldo + ? WHERE id=?", (total, cli_id))
                conn.commit()
                st.session_state.carrito = []
                st.success(f"Venta registrada: ${total:,.0f}")
                st.rerun()

            if st.button("🗑️ Vaciar", use_container_width=True):
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
        lote = st.text_input("Nº Lote (opcional)")
        caduc = st.date_input("Caducidad (opcional)", value=None)

        if precio > 0:
            st.success(f"💡 Precio venta se actualizará a **${round(precio*1.30):,.0f}/kg** (+30%)")

        if st.button("➕ Agregar", use_container_width=True):
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
                    "prov": prov_opts[prov], "lote": lote,
                    "caduc": str(caduc) if caduc else ""
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
                    conn.execute("UPDATE productos SET stock=stock+?, precio=? WHERE id=?",
                                 (item["cantidad"], item["pv"], item["id"]))
                    conn.execute("INSERT INTO compras (producto_id,cantidad,precio,fecha,proveedor_id) VALUES (?,?,?,?,?)",
                                 (item["id"], item["cantidad"], item["precio"], fecha, item["prov"]))
                    if item["lote"] or item["caduc"]:
                        conn.execute("INSERT INTO lotes (producto_id,nombre,cantidad,lote,caducidad,fecha) VALUES (?,?,?,?,?,?)",
                                     (item["id"], item["nombre"], item["cantidad"], item["lote"], item["caduc"], fecha))
                conn.commit()
                st.session_state.carrito_c = []
                st.success(f"Compra registrada ${total:,.0f} — Precios actualizados")
                st.rerun()

            if st.button("🗑️ Vaciar", use_container_width=True):
                st.session_state.carrito_c = []
                st.rerun()

# ---------- PEDIDOS ----------
elif menu == "📋 Pedidos":
    st.header("📋 Pedidos Sugeridos (90 días → 30 días)")
    df = pd.read_sql("""
        SELECT p.categoria, p.nombre, p.stock, p.minimo,
               COALESCE(SUM(v.cantidad),0) as vendido_90d
        FROM productos p
        LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-90 days')
        GROUP BY p.id ORDER BY p.categoria, p.nombre
    """, conn)
    df["proy_30d"] = (df["vendido_90d"] / 90 * 30).round(1)
    df["sugerido"] = (df["proy_30d"] + df["minimo"] - df["stock"]).clip(lower=0).round(1)
    necesita = df[df["sugerido"] > 0].sort_values("sugerido", ascending=False)
    if necesita.empty:
        st.success("✅ No hay que pedir")
    else:
        st.dataframe(necesita[["categoria", "nombre", "stock", "vendido_90d", "proy_30d", "sugerido"]],
                     use_container_width=True, hide_index=True)
        st.metric("Total kg sugeridos", f"{necesita['sugerido'].sum():.1f}")

# ---------- PRECIOS ----------
elif menu == "💡 Precios":
    st.header("💡 Sugerencias de Precios")
    df = pd.read_sql("""
        SELECT p.id, p.nombre, p.categoria, p.precio, p.stock, p.minimo,
               COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p
        LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-90 days')
        GROUP BY p.id
    """, conn)

    for _, r in df.iterrows():
        dias = r["stock"] / (r["vend"] / 90) if r["vend"] > 0 else 999
        if dias > 45 or r["stock"] > r["minimo"] * 3:
            sug, acc, prio = round(r["precio"] * 0.90), "Bajar -10%", "Alta"
        elif dias > 30:
            sug, acc, prio = round(r["precio"] * 0.95), "Bajar -5%", "Media"
        elif dias < 10 and r["stock"] <= r["minimo"]:
            sug, acc, prio = round(r["precio"] * 1.05), "Subir +5%", "Oportunidad"
        else:
            continue

        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{r['categoria']} − {r['nombre']}** ({prio})")
            st.caption(f"Stock: {r['stock']:.1f} kg | Días: {dias if dias < 999 else 'Sin ventas'}")
            st.write(f"${r['precio']:,.0f} → **${sug:,.0f}** ({acc})")
        with col2:
            if st.button("✅ Aplicar", key=f"ap{r['id']}"):
                conn.execute("UPDATE productos SET precio=? WHERE id=?", (sug, r["id"]))
                conn.commit()
                st.success("Actualizado")
                st.rerun()
        st.divider()

# ---------- MERMAS ----------
elif menu == "⚠️ Mermas":
    st.header("⚠️ Mermas")
    prods = conn.execute("SELECT id, nombre FROM productos ORDER BY nombre").fetchall()
    opts = {p["nombre"]: p["id"] for p in prods}
    with st.form("merma"):
        sel = st.selectbox("Producto", list(opts.keys()))
        cant = st.number_input("Kg perdidos", min_value=0.1, step=0.1, value=1.0)
        motivo = st.text_input("Motivo", placeholder="Vencimiento, recorte...")
        if st.form_submit_button("Registrar Merma"):
            p = conn.execute("SELECT precio, stock FROM productos WHERE id=?", (opts[sel],)).fetchone()
            if cant > p["stock"]:
                st.error("Supera el stock")
            else:
                costo = round(cant * p["precio"])
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                conn.execute("UPDATE productos SET stock=stock-? WHERE id=?", (cant, opts[sel]))
                conn.execute("INSERT INTO mermas (producto_id,cantidad,motivo,costo,fecha) VALUES (?,?,?,?,?)",
                             (opts[sel], cant, motivo or "—", costo, fecha))
                conn.commit()
                st.success("Merma registrada")
                st.rerun()

    df = pd.read_sql("SELECT fecha, producto_id, cantidad, motivo, costo FROM mermas ORDER BY fecha DESC LIMIT 20", conn)
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.metric("Costo total mermas", f"${df['costo'].sum():,.0f}")

# ---------- LOTES ----------
elif menu == "📅 Lotes / Caducidad":
    st.header("📅 Lotes y Caducidad")
    df = pd.read_sql("SELECT nombre, lote, cantidad, caducidad, fecha FROM lotes ORDER BY caducidad ASC", conn)
    if df.empty:
        st.info("Sin lotes. Agrégalos al registrar compras.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- PROVEEDORES ----------
elif menu == "🚚 Proveedores":
    st.header("🚚 Proveedores")
    with st.expander("➕ Nuevo proveedor"):
        with st.form("np"):
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono")
            no = st.text_input("Notas")
            if st.form_submit_button("Guardar") and n.strip():
                conn.execute("INSERT INTO proveedores (nombre,telefono,notas) VALUES (?,?,?)", (n, t, no))
                conn.commit()
                st.success("Guardado")
                st.rerun()

    st.dataframe(pd.read_sql("SELECT nombre, telefono, notas FROM proveedores", conn), use_container_width=True, hide_index=True)

    st.subheader("Historial de precios de compra")
    df = pd.read_sql("""
        SELECT c.fecha, p.nombre, c.precio, c.cantidad
        FROM compras c JOIN productos p ON c.producto_id=p.id
        ORDER BY c.fecha DESC LIMIT 20
    """, conn)
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------- CLIENTES ----------
elif menu == "👥 Clientes / Fiados":
    st.header("👥 Clientes y Fiados")
    with st.expander("➕ Nuevo cliente"):
        with st.form("nc"):
            n = st.text_input("Nombre")
            t = st.text_input("Teléfono")
            if st.form_submit_button("Guardar") and n.strip():
                conn.execute("INSERT INTO clientes (nombre,telefono,saldo) VALUES (?,?,0)", (n, t))
                conn.commit()
                st.success("Guardado")
                st.rerun()

    st.dataframe(pd.read_sql("SELECT nombre, telefono, saldo FROM clientes", conn), use_container_width=True, hide_index=True)

    st.subheader("Registrar pago de fiado")
    clis = conn.execute("SELECT id, nombre, saldo FROM clientes WHERE saldo > 0").fetchall()
    if clis:
        opts = {f"{c['nombre']} (debe ${c['saldo']:,.0f})": c["id"] for c in clis}
        sel = st.selectbox("Cliente", list(opts.keys()))
        monto = st.number_input("Monto pagado", min_value=0, step=1000)
        if st.button("Registrar pago"):
            conn.execute("UPDATE clientes SET saldo = MAX(0, saldo - ?) WHERE id=?", (monto, opts[sel]))
            conn.commit()
            st.success("Pago registrado")
            st.rerun()

# ---------- CIERRE ----------
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

    notas = st.text_input("Notas del día")
    if st.button("💾 Guardar cierre"):
        conn.execute("DELETE FROM cierres WHERE fecha=?", (hoy,))
        conn.execute("INSERT INTO cierres (fecha,total,kilos,num,notas) VALUES (?,?,?,?,?)",
                     (hoy, total, kilos, num, notas))
        conn.commit()
        st.success("Cierre guardado")

    st.subheader("Historial")
    st.dataframe(pd.read_sql("SELECT * FROM cierres ORDER BY fecha DESC LIMIT 15", conn),
                 use_container_width=True, hide_index=True)

# ---------- METAS ----------
elif menu == "🎯 Metas":
    st.header("🎯 Meta de Venta Diaria")
    meta = get_meta()
    nueva = st.number_input("Meta del día ($)", min_value=0, value=int(meta), step=5000)
    if st.button("Guardar meta"):
        set_meta(nueva)
        st.success("Meta guardada")
        st.rerun()

    hoy = datetime.now().strftime("%Y-%m-%d")
    actual = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE date(fecha)=?", (hoy,)).fetchone()[0]
    pct = min(100, round(actual / meta * 100)) if meta > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Meta", f"${meta:,.0f}")
    c2.metric("Vendido", f"${actual:,.0f}")
    c3.metric("Avance", f"{pct}%")
    st.progress(pct / 100)
    if pct >= 100:
        st.success("🎉 ¡Meta cumplida!")
    else:
        st.info(f"Faltan ${max(0, meta - actual):,.0f}")

# ---------- SIMULADOR ----------
elif menu == "🧮 Simulador":
    st.header("🧮 Simulador de Precios")
    prods = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    opts = {p["nombre"]: p for p in prods}
    sel = st.selectbox("Producto", list(opts.keys()))
    p = opts[sel]
    nuevo = st.number_input("Nuevo precio $/kg", min_value=0, value=int(p["precio"]), step=50)
    extra = st.number_input("Kg extras que venderías al mes", min_value=0.0, step=1.0)

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

# ---------- ANÁLISIS ----------
elif menu == "📊 Análisis":
    st.header("📊 Análisis")
    tV = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas").fetchone()[0]
    kV = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM ventas").fetchone()[0]
    tC = conn.execute("SELECT COALESCE(SUM(cantidad*precio),0) FROM compras").fetchone()[0]
    kC = conn.execute("SELECT COALESCE(SUM(cantidad),0) FROM compras").fetchone()[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Ventas", f"${tV:,.0f}")
    c2.metric("Kilos Vendidos", f"{kV:.1f}")
    c3.metric("Total Compras", f"${tC:,.0f}")
    c4.metric("Kilos Comprados", f"{kC:.1f}")

    st.subheader("⭐ Estrellas vs 🐌 Problemas")
    df = pd.read_sql("""
        SELECT p.nombre, p.stock, COALESCE(SUM(v.cantidad),0) as vend
        FROM productos p LEFT JOIN ventas v ON p.id=v.producto_id AND v.fecha >= date('now','-90 days')
        GROUP BY p.id
    """, conn)
    col1, col2 = st.columns(2)
    with col1:
        st.write("Más vendidos")
        st.dataframe(df.nlargest(5, "vend")[["nombre", "vend"]], use_container_width=True, hide_index=True)
    with col2:
        st.write("Menos rotación (con stock)")
        st.dataframe(df[df["stock"] > 0].nsmallest(5, "vend")[["nombre", "vend", "stock"]],
                     use_container_width=True, hide_index=True)

    st.subheader("Más vendidos (kg)")
    top = pd.read_sql("""
        SELECT p.nombre, ROUND(SUM(v.cantidad),1) as kg
        FROM ventas v JOIN productos p ON v.producto_id=p.id
        GROUP BY v.producto_id ORDER BY kg DESC LIMIT 8
    """, conn)
    if not top.empty:
        st.bar_chart(top.set_index("nombre"))

    st.subheader("Margen real")
    margen = pd.read_sql("""
        SELECT p.nombre, p.precio as venta,
               (SELECT precio FROM compras WHERE producto_id=p.id ORDER BY fecha DESC LIMIT 1) as costo
        FROM productos p
    """, conn)
    margen = margen.dropna()
    if not margen.empty:
        margen["margen_%"] = ((margen["venta"] - margen["costo"]) / margen["venta"] * 100).round(1)
        st.dataframe(margen, use_container_width=True, hide_index=True)

# ---------- COMPARATIVO ----------
elif menu == "📈 Comparativo":
    st.header("📈 Comparativo de Períodos")
    esta_sem = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-7 days')").fetchone()[0]
    sem_ant = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE fecha >= date('now','-14 days') AND fecha < date('now','-7 days')").fetchone()[0]
    este_mes = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now')").fetchone()[0]
    mes_ant = conn.execute("SELECT COALESCE(SUM(total),0) FROM ventas WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now','-1 month')").fetchone()[0]

    def var(a, b):
        return "—" if b == 0 else f"{((a-b)/b*100):+.1f}%"

    st.write(f"**Últimos 7 días:** ${esta_sem:,.0f}  |  **7 anteriores:** ${sem_ant:,.0f}  |  Var: {var(esta_sem, sem_ant)}")
    st.write(f"**Este mes:** ${este_mes:,.0f}  |  **Mes pasado:** ${mes_ant:,.0f}  |  Var: {var(este_mes, mes_ant)}")

# ---------- QR ----------
elif menu == "📱 QR":
    st.header("📱 Generar QR")
    prods = conn.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    opts = {f"{p['nombre']} (${p['precio']:,.0f}/kg)": p for p in prods}
    sel = st.selectbox("Producto", list(opts.keys()))
    p = opts[sel]
    peso = st.number_input("Peso (kg)", min_value=0.1, step=0.1, value=1.0)
    total = round(peso * p["precio"])
    st.write(f"**Total: ${total:,.0f}**")

    if st.button("📱 Generar QR", use_container_width=True):
        texto = f"""CARNICERÍA
Producto: {p['nombre']}
Categoría: {p['categoria']}
Peso: {peso:.2f} kg
Precio: ${p['precio']:,.0f}/kg
Total: ${total:,.0f}
Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}"""
        img = generar_qr(texto)
        st.image(img, width=250)
        st.code(texto)
        st.download_button("⬇️ Descargar QR", data=img, file_name=f"qr_{p['nombre'].replace(' ','_')}.png", mime="image/png")

# ---------- EXPORTAR ----------
elif menu == "⬇️ Exportar":
    st.header("⬇️ Exportar a Excel")

    if st.button("📦 Productos"):
        df = pd.read_sql("SELECT * FROM productos", conn)
        st.download_button("Descargar", df.to_csv(index=False).encode(), "productos.csv", "text/csv")

    if st.button("💰 Ventas"):
        df = pd.read_sql("SELECT * FROM ventas", conn)
        st.download_button("Descargar", df.to_csv(index=False).encode(), "ventas.csv", "text/csv")

    if st.button("📥 Compras"):
        df = pd.read_sql("SELECT * FROM compras", conn)
        st.download_button("Descargar", df.to_csv(index=False).encode(), "compras.csv", "text/csv")

    if st.button("⚠️ Mermas"):
        df = pd.read_sql("SELECT * FROM mermas", conn)
        st.download_button("Descargar", df.to_csv(index=False).encode(), "mermas.csv", "text/csv")

conn.close()
