import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:
    import psycopg
except Exception:
    psycopg = None

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
SQLITE_PATH = DATA_DIR / "cajapos.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")

app = FastAPI(title="CajaPOS", version="2.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

class ProductIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: int = Field(gt=0)

class SaleItemIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

class SaleIn(BaseModel):
    customer: str = Field(default="Cliente", max_length=120)
    attendant: str = Field(default="Vendedor", max_length=120)
    payment_method: str = Field(default="Efectivo")
    payment: int = Field(default=0, ge=0)
    items: list[SaleItemIn]

class PendingIn(BaseModel):
    customer: str = Field(default="Cliente", max_length=120)
    attendant: str = Field(default="Vendedor", max_length=120)
    items: list[SaleItemIn]

class AdminIn(BaseModel):
    password: str

class OpenCashIn(BaseModel):
    password: str
    attendant: str = Field(default="Administrador", max_length=120)
    opening_amount: int = Field(default=0, ge=0)

class CloseCashIn(BaseModel):
    password: str
    closing_amount: int = Field(default=0, ge=0)


def pg_conn():
    if not psycopg:
        raise RuntimeError("psycopg no está instalado en este servidor")
    return psycopg.connect(DATABASE_URL)


def db_execute(sql, params=(), fetch=False):
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if fetch else None
            conn.commit()
            return rows
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return rows


def table_columns(table):
    if USE_POSTGRES:
        rows = db_execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,), True)
        return {r[0] for r in rows}
    rows = db_execute(f"PRAGMA table_info({table})", fetch=True)
    return {r[1] for r in rows}


def init_db():
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS products(
                    id SERIAL PRIMARY KEY, name VARCHAR(120) NOT NULL, price INTEGER NOT NULL CHECK(price>0), active BOOLEAN NOT NULL DEFAULT TRUE)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS cash_registers(
                    id SERIAL PRIMARY KEY, business_date DATE NOT NULL UNIQUE, status VARCHAR(20) NOT NULL,
                    opened_at TIMESTAMPTZ, opened_by VARCHAR(120), opening_amount INTEGER NOT NULL DEFAULT 0,
                    closed_at TIMESTAMPTZ, closed_by VARCHAR(120), closing_amount INTEGER NOT NULL DEFAULT 0)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS sales(
                    id SERIAL PRIMARY KEY, customer VARCHAR(120) NOT NULL, attendant VARCHAR(120) NOT NULL DEFAULT 'Vendedor',
                    total INTEGER NOT NULL, payment INTEGER NOT NULL, change INTEGER NOT NULL,
                    payment_method VARCHAR(20) NOT NULL DEFAULT 'Efectivo', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    register_id INTEGER, archived BOOLEAN NOT NULL DEFAULT FALSE)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS sale_items(
                    id SERIAL PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL, product_name VARCHAR(120) NOT NULL, unit_price INTEGER NOT NULL,
                    quantity INTEGER NOT NULL, subtotal INTEGER NOT NULL)""")
                cur.execute("""CREATE TABLE IF NOT EXISTS pending_orders(
                    id SERIAL PRIMARY KEY, customer VARCHAR(120) NOT NULL, attendant VARCHAR(120) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending')""")
                cur.execute("""CREATE TABLE IF NOT EXISTS pending_items(
                    id SERIAL PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES pending_orders(id) ON DELETE CASCADE,
                    product_id INTEGER NOT NULL, product_name VARCHAR(120) NOT NULL, unit_price INTEGER NOT NULL,
                    quantity INTEGER NOT NULL, subtotal INTEGER NOT NULL)""")
              # Migrate older installations if necessary.
# IF NOT EXISTS evita que Render falle si la columna ya existe.
cur.execute("""
    ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS attendant
    VARCHAR(120) NOT NULL DEFAULT 'Vendedor'
""")

cur.execute("""
    ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS payment_method
    VARCHAR(20) NOT NULL DEFAULT 'Efectivo'
""")

cur.execute("""
    ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS register_id
    INTEGER
""")

cur.execute("""
    ALTER TABLE sales
    ADD COLUMN IF NOT EXISTS archived
    BOOLEAN NOT NULL DEFAULT FALSE
""")
                cur.execute("SELECT COUNT(*) FROM products")
                if cur.fetchone()[0] == 0:
                    seed_products_pg(cur)
                cur.execute("UPDATE products SET active=TRUE WHERE name IN (SELECT name FROM (VALUES ('Banana Split'),('Banana Split premium'),('Bowl de la felicidad'),('Canasta - Gelato'),('Cheesecake'),('Ensalada de frutas'),('Ensalada de frutas con queso'),('Gelatina'),('Oblea Premium'),('Oblea con helado'),('Oblea con queso'),('Quesillo'),('Solterita'),('Solterita Con queso'),('Solterita con queso y fruta'),('canasta soft'),('Topping adicional'),('Gaseosa')) AS v(name))")
            conn.commit()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,price INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS cash_registers(id INTEGER PRIMARY KEY AUTOINCREMENT,business_date TEXT NOT NULL UNIQUE,status TEXT NOT NULL,opened_at TEXT,opened_by TEXT,opening_amount INTEGER NOT NULL DEFAULT 0,closed_at TEXT,closed_by TEXT,closing_amount INTEGER NOT NULL DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY AUTOINCREMENT,customer TEXT NOT NULL,total INTEGER NOT NULL,payment INTEGER NOT NULL,change INTEGER NOT NULL,created_at TEXT NOT NULL,attendant TEXT NOT NULL DEFAULT 'Vendedor',payment_method TEXT NOT NULL DEFAULT 'Efectivo',register_id INTEGER,archived INTEGER NOT NULL DEFAULT 0)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY AUTOINCREMENT,sale_id INTEGER NOT NULL,product_id INTEGER NOT NULL,product_name TEXT NOT NULL,unit_price INTEGER NOT NULL,quantity INTEGER NOT NULL,subtotal INTEGER NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS pending_orders(id INTEGER PRIMARY KEY AUTOINCREMENT,customer TEXT NOT NULL,attendant TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS pending_items(id INTEGER PRIMARY KEY AUTOINCREMENT,order_id INTEGER NOT NULL,product_id INTEGER NOT NULL,product_name TEXT NOT NULL,unit_price INTEGER NOT NULL,quantity INTEGER NOT NULL,subtotal INTEGER NOT NULL)""")
        cols = {r[1] for r in cur.execute("PRAGMA table_info(sales)").fetchall()}
        if "attendant" not in cols: cur.execute("ALTER TABLE sales ADD COLUMN attendant TEXT NOT NULL DEFAULT 'Vendedor'")
        if "payment_method" not in cols: cur.execute("ALTER TABLE sales ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Efectivo'")
        if "register_id" not in cols: cur.execute("ALTER TABLE sales ADD COLUMN register_id INTEGER")
        if "archived" not in cols: cur.execute("ALTER TABLE sales ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] == 0: seed_products_sqlite(cur)
        cur.execute("UPDATE products SET active=1 WHERE name IN ('Banana Split','Banana Split premium','Bowl de la felicidad','Canasta - Gelato','Cheesecake','Ensalada de frutas','Ensalada de frutas con queso','Gelatina','Oblea Premium','Oblea con helado','Oblea con queso','Quesillo','Solterita','Solterita Con queso','Solterita con queso y fruta','canasta soft','Topping adicional','Gaseosa')")
        conn.commit(); conn.close()


def seed_products_pg(cur):
    products = [
        ("Banana Split",13000),("Banana Split premium",15000),("Bowl de la felicidad",20000),("Canasta - Gelato",13000),
        ("Cheesecake",8000),("Cono de helado - Mini",3000),("Cono de helado - Super + 1 topping",5000),("Cono de helado - Canasta + 2 toppings",10000),
        ("Ensalada de frutas",15000),("Ensalada de frutas con queso",17000),("Fresas con crema - Personal",5000),("Fresas con crema - Mediano",10000),
        ("Fresas con crema - Grande",15000),("Gelatina",5000),("Gelato",5000),("Malteada",12000),("Oblea Premium",5000),("Oblea con helado",10000),
        ("Oblea con queso",7000),("Quesillo",7000),("Solterita",3000),("Solterita Con queso",4000),("Solterita con queso y fruta",5000),
        ("Vasito de helado - Artesanal",3000),("Vasito de helado - Mini (5 oz)",5000),("Vasito de helado - Mediano (9 oz)",10000),
        ("Vasito de helado - Grande (12 oz)",15000),("canasta soft",10000),("Topping adicional",2000),("Gaseosa",2000)]
    cur.executemany("INSERT INTO products(name,price,active) VALUES(%s,%s,TRUE)", products)


def seed_products_sqlite(cur):
    products = [
        ("Banana Split",13000),("Banana Split premium",15000),("Bowl de la felicidad",20000),("Canasta - Gelato",13000),("Cheesecake",8000),
        ("Cono de helado - Mini",3000),("Cono de helado - Super + 1 topping",5000),("Cono de helado - Canasta + 2 toppings",10000),
        ("Ensalada de frutas",15000),("Ensalada de frutas con queso",17000),("Fresas con crema - Personal",5000),("Fresas con crema - Mediano",10000),
        ("Fresas con crema - Grande",15000),("Gelatina",5000),("Gelato",5000),("Malteada",12000),("Oblea Premium",5000),("Oblea con helado",10000),
        ("Oblea con queso",7000),("Quesillo",7000),("Solterita",3000),("Solterita Con queso",4000),("Solterita con queso y fruta",5000),
        ("Vasito de helado - Artesanal",3000),("Vasito de helado - Mini (5 oz)",5000),("Vasito de helado - Mediano (9 oz)",10000),
        ("Vasito de helado - Grande (12 oz)",15000),("canasta soft",10000),("Topping adicional",2000),("Gaseosa",2000)]
    cur.executemany("INSERT INTO products(name,price,active) VALUES(?,?,1)", products)


def require_admin(password):
    if password != ADMIN_PASSWORD:
        raise HTTPException(403, "Contraseña de administrador incorrecta.")


def current_register():
    today = date.today().isoformat()
    if USE_POSTGRES:
        rows = db_execute("SELECT id,business_date,status,opened_at,opened_by,opening_amount,closed_at,closed_by,closing_amount FROM cash_registers WHERE business_date=%s", (today,), True)
    else:
        rows = db_execute("SELECT id,business_date,status,opened_at,opened_by,opening_amount,closed_at,closed_by,closing_amount FROM cash_registers WHERE business_date=?", (today,), True)
    if not rows: return None
    r=rows[0]
    return {"id":r[0],"business_date":str(r[1]),"status":r[2],"opened_at":str(r[3]) if r[3] else None,"opened_by":r[4],"opening_amount":r[5],"closed_at":str(r[6]) if r[6] else None,"closed_by":r[7],"closing_amount":r[8]}


init_db()

@app.get("/")
def home(): return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/api/health")
def health(): return {"ok":True}

@app.get("/api/products")
def products():
    if USE_POSTGRES:
        rows=db_execute("SELECT id,name,price FROM products WHERE active=TRUE ORDER BY name", fetch=True)
    else: rows=db_execute("SELECT id,name,price FROM products WHERE active=1 ORDER BY name", fetch=True)
    return [{"id":r[0],"name":r[1],"price":r[2]} for r in rows]

@app.post("/api/products")
def add_product(p:ProductIn):
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO products(name,price,active) VALUES(%s,%s,TRUE) RETURNING id",(p.name.strip(),p.price)); pid=cur.fetchone()[0]
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor(); cur.execute("INSERT INTO products(name,price,active) VALUES(?,?,1)",(p.name.strip(),p.price)); pid=cur.lastrowid; conn.commit(); conn.close()
    return {"id":pid,"name":p.name.strip(),"price":p.price}

@app.delete("/api/products/{product_id}")
def delete_product(product_id:int, password:Optional[str]=None):
    # Product deletion is intentionally protected by admin password.
    require_admin(password or "")
    if USE_POSTGRES: db_execute("UPDATE products SET active=FALSE WHERE id=%s",(product_id,))
    else: db_execute("UPDATE products SET active=0 WHERE id=?",(product_id,))
    return {"ok":True}

@app.get("/api/register")
def register(): return current_register() or {"status":"closed","business_date":date.today().isoformat()}

@app.post("/api/register/open")
def open_register(x:OpenCashIn):
    require_admin(x.password)
    reg=current_register()
    if reg and reg["status"]=="open":
        return reg

    # The administrator may open/close/reopen the same day's register as many
    # times as needed. Reopening keeps the same register id so previously
    # recorded sales remain in the same daily register/history.
    now=datetime.now().isoformat(timespec="seconds"); today=date.today().isoformat()
    if reg and reg["status"]=="closed":
        if USE_POSTGRES:
            with pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE cash_registers
                        SET status='open', opened_at=NOW(), opened_by=%s, opening_amount=%s,
                            closed_at=NULL, closed_by=NULL, closing_amount=0
                        WHERE id=%s
                        RETURNING id
                    """,(x.attendant,x.opening_amount,reg["id"]))
                conn.commit()
        else:
            conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor()
            cur.execute("""
                UPDATE cash_registers
                SET status='open', opened_at=?, opened_by=?, opening_amount=?,
                    closed_at=NULL, closed_by=NULL, closing_amount=0
                WHERE id=?
            """,(now,x.attendant,x.opening_amount,reg["id"]))
            conn.commit(); conn.close()
        return current_register()

    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO cash_registers(business_date,status,opened_at,opened_by,opening_amount) VALUES(%s,'open',NOW(),%s,%s) RETURNING id",(today,x.attendant,x.opening_amount)); rid=cur.fetchone()[0]
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor(); cur.execute("INSERT INTO cash_registers(business_date,status,opened_at,opened_by,opening_amount) VALUES(?,?,?,?,?)",(today,'open',now,x.attendant,x.opening_amount)); rid=cur.lastrowid; conn.commit(); conn.close()
    return current_register()

@app.post("/api/register/close")
def close_register(x:CloseCashIn):
    require_admin(x.password)
    reg=current_register()
    if not reg or reg["status"]!="open": raise HTTPException(400,"La caja no está abierta.")
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COALESCE(SUM(total),0),COUNT(*),COALESCE(SUM(CASE WHEN payment_method='Efectivo' THEN total ELSE 0 END),0),COALESCE(SUM(CASE WHEN payment_method='Nequi' THEN total ELSE 0 END),0) FROM sales WHERE register_id=%s",(reg["id"],)); s=cur.fetchone()
                cur.execute("UPDATE cash_registers SET status='closed',closed_at=NOW(),closed_by=%s,closing_amount=%s WHERE id=%s",("Administrador",x.closing_amount,reg["id"]))
                cur.execute("UPDATE sales SET archived=TRUE WHERE register_id=%s",(reg["id"],))
            conn.commit()
    else:
        rows=db_execute("SELECT COALESCE(SUM(total),0),COUNT(*),COALESCE(SUM(CASE WHEN payment_method='Efectivo' THEN total ELSE 0 END),0),COALESCE(SUM(CASE WHEN payment_method='Nequi' THEN total ELSE 0 END),0) FROM sales WHERE register_id=?",(reg["id"],),True); s=rows[0]
        db_execute("UPDATE cash_registers SET status='closed',closed_at=?,closed_by=?,closing_amount=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),'Administrador',x.closing_amount,reg["id"]))
        db_execute("UPDATE sales SET archived=1 WHERE register_id=?",(reg["id"],))
    return {"ok":True,"date":reg["business_date"],"sales_count":s[1],"total":s[0],"cash_total":s[2],"nequi_total":s[3],"closing_amount":x.closing_amount}

@app.post("/api/admin/check")
def admin_check(x:AdminIn): require_admin(x.password); return {"ok":True}

@app.post("/api/sales")
def create_sale(sale:SaleIn):
    reg=current_register()
    if not reg or reg["status"]!="open": raise HTTPException(400,"La caja está cerrada. Un administrador debe abrirla.")
    if sale.payment_method not in ("Efectivo","Nequi"): raise HTTPException(400,"Método de pago no válido.")
    if not sale.items: raise HTTPException(400,"La venta no tiene productos.")
    ids=[i.product_id for i in sale.items]; ph=",".join(["%s"]*len(ids)) if USE_POSTGRES else ",".join(["?"]*len(ids))
    rows=db_execute(f"SELECT id,name,price FROM products WHERE active={'TRUE' if USE_POSTGRES else '1'} AND id IN ({ph})",ids,True); pm={r[0]:(r[1],r[2]) for r in rows}
    total=0; prepared=[]
    for i in sale.items:
        if i.product_id not in pm: raise HTTPException(400,"Producto no disponible.")
        name,price=pm[i.product_id]; sub=price*i.quantity; total+=sub; prepared.append((i.product_id,name,price,i.quantity,sub))
    if sale.payment_method=="Nequi":
        payment=total
        change=0
    else:
        payment=sale.payment
        if sale.payment<total: raise HTTPException(400,"El dinero recibido es menor que el total.")
        change=sale.payment-total
    customer=sale.customer.strip() or "Cliente"; attendant=sale.attendant.strip() or "Vendedor"; created=datetime.now().isoformat(timespec="seconds")
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO sales(customer,attendant,total,payment,change,payment_method,created_at,register_id,archived) VALUES(%s,%s,%s,%s,%s,%s,NOW(),%s,FALSE) RETURNING id",(customer,attendant,total,payment,change,sale.payment_method,reg["id"])); sid=cur.fetchone()[0]
                cur.executemany("INSERT INTO sale_items(sale_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(%s,%s,%s,%s,%s,%s)",[(sid,)+x for x in prepared])
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor(); cur.execute("INSERT INTO sales(customer,attendant,total,payment,change,payment_method,created_at,register_id,archived) VALUES(?,?,?,?,?,?,?,?,0)",(customer,attendant,total,payment,change,sale.payment_method,created,reg["id"])); sid=cur.lastrowid; cur.executemany("INSERT INTO sale_items(sale_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(?,?,?,?,?,?)",[(sid,)+x for x in prepared]); conn.commit(); conn.close()
    return {"id":sid,"total":total,"payment":payment,"change":change,"payment_method":sale.payment_method}


def pending_build(items):
    ids=[i.product_id for i in items]; ph=",".join(["%s"]*len(ids)) if USE_POSTGRES else ",".join(["?"]*len(ids))
    rows=db_execute(f"SELECT id,name,price FROM products WHERE active={'TRUE' if USE_POSTGRES else '1'} AND id IN ({ph})",ids,True); pm={r[0]:(r[1],r[2]) for r in rows}; total=0; out=[]
    for i in items:
        if i.product_id not in pm: raise HTTPException(400,"Producto no disponible.")
        n,p=pm[i.product_id]; sub=p*i.quantity; total+=sub; out.append((i.product_id,n,p,i.quantity,sub))
    return total,out

@app.post("/api/pending")
def create_pending(x:PendingIn):
    reg=current_register()
    if not reg or reg["status"]!="open": raise HTTPException(400,"La caja está cerrada.")
    if not x.items: raise HTTPException(400,"El pedido no tiene productos.")
    total,prepared=pending_build(x.items); now=datetime.now().isoformat(timespec="seconds"); customer=x.customer.strip() or "Cliente"; attendant=x.attendant.strip() or "Vendedor"
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO pending_orders(customer,attendant,created_at,updated_at,status) VALUES(%s,%s,NOW(),NOW(),'pending') RETURNING id",(customer,attendant)); oid=cur.fetchone()[0]
                cur.executemany("INSERT INTO pending_items(order_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(%s,%s,%s,%s,%s,%s)",[(oid,)+x for x in prepared])
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor(); cur.execute("INSERT INTO pending_orders(customer,attendant,created_at,updated_at,status) VALUES(?,?,?,?,?)",(customer,attendant,now,now,'pending')); oid=cur.lastrowid; cur.executemany("INSERT INTO pending_items(order_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(?,?,?,?,?,?)",[(oid,)+x for x in prepared]); conn.commit(); conn.close()
    return {"id":oid,"total":total}

@app.put("/api/pending/{order_id}")
def update_pending(order_id:int,x:PendingIn):
    reg=current_register()
    if not reg or reg["status"]!="open": raise HTTPException(400,"La caja está cerrada.")
    if not x.items: raise HTTPException(400,"El pedido no tiene productos.")
    detail=pending_detail(order_id)
    total,prepared=pending_build(x.items)
    now=datetime.now().isoformat(timespec="seconds"); customer=x.customer.strip() or detail["customer"]; attendant=x.attendant.strip() or detail["attendant"]
    if USE_POSTGRES:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE pending_orders SET customer=%s,attendant=%s,updated_at=NOW() WHERE id=%s AND status='pending'",(customer,attendant,order_id))
                if cur.rowcount==0: raise HTTPException(404,"Pedido pendiente no encontrado.")
                cur.execute("DELETE FROM pending_items WHERE order_id=%s",(order_id,))
                cur.executemany("INSERT INTO pending_items(order_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(%s,%s,%s,%s,%s,%s)",[(order_id,)+z for z in prepared])
            conn.commit()
    else:
        conn=sqlite3.connect(SQLITE_PATH); cur=conn.cursor(); cur.execute("UPDATE pending_orders SET customer=?,attendant=?,updated_at=? WHERE id=? AND status='pending'",(customer,attendant,now,order_id))
        if cur.rowcount==0: conn.close(); raise HTTPException(404,"Pedido pendiente no encontrado.")
        cur.execute("DELETE FROM pending_items WHERE order_id=?",(order_id,))
        cur.executemany("INSERT INTO pending_items(order_id,product_id,product_name,unit_price,quantity,subtotal) VALUES(?,?,?,?,?,?)",[(order_id,)+z for z in prepared]); conn.commit(); conn.close()
    return {"id":order_id,"total":total}

@app.get("/api/pending")
def pending_list():
    if USE_POSTGRES: orders=db_execute("SELECT id,customer,attendant,created_at,updated_at FROM pending_orders WHERE status='pending' ORDER BY updated_at DESC",fetch=True); items_sql="SELECT order_id,product_name,unit_price,quantity,subtotal FROM pending_items WHERE order_id=%s ORDER BY id"
    else: orders=db_execute("SELECT id,customer,attendant,created_at,updated_at FROM pending_orders WHERE status='pending' ORDER BY updated_at DESC",fetch=True); items_sql="SELECT order_id,product_name,unit_price,quantity,subtotal FROM pending_items WHERE order_id=? ORDER BY id"
    out=[]
    for o in orders:
        items=db_execute(items_sql,(o[0],),True); out.append({"id":o[0],"customer":o[1],"attendant":o[2],"created_at":str(o[3]),"updated_at":str(o[4]),"items":[{"name":r[1],"unit_price":r[2],"quantity":r[3],"subtotal":r[4]} for r in items],"total":sum(r[4] for r in items)})
    return out

@app.get("/api/pending/{order_id}")
def pending_detail(order_id:int):
    if USE_POSTGRES: orders=db_execute("SELECT id,customer,attendant,created_at,updated_at,status FROM pending_orders WHERE id=%s",(order_id,),True); items=db_execute("SELECT product_id,product_name,unit_price,quantity,subtotal FROM pending_items WHERE order_id=%s ORDER BY id",(order_id,),True)
    else: orders=db_execute("SELECT id,customer,attendant,created_at,updated_at,status FROM pending_orders WHERE id=?",(order_id,),True); items=db_execute("SELECT product_id,product_name,unit_price,quantity,subtotal FROM pending_items WHERE order_id=? ORDER BY id",(order_id,),True)
    if not orders: raise HTTPException(404,"Pedido no encontrado.")
    o=orders[0]; return {"id":o[0],"customer":o[1],"attendant":o[2],"items":[{"product_id":r[0],"name":r[1],"unit_price":r[2],"quantity":r[3],"subtotal":r[4]} for r in items],"total":sum(r[4] for r in items)}

@app.delete("/api/pending/{order_id}")
def delete_pending(order_id:int):
    if USE_POSTGRES: db_execute("DELETE FROM pending_orders WHERE id=%s",(order_id,))
    else: db_execute("DELETE FROM pending_orders WHERE id=?",(order_id,))
    return {"ok":True}

@app.post("/api/pending/{order_id}/pay")
def pay_pending(order_id:int,sale:SaleIn):
    detail=pending_detail(order_id)
    if not sale.items:
        raise HTTPException(400,"El pedido no tiene productos.")
    # Use the current cart, so the seller can add more products after reopening a pending order.
    merged=SaleIn(customer=detail["customer"],attendant=sale.attendant or detail["attendant"],payment_method=sale.payment_method,payment=sale.payment,items=sale.items)
    result=create_sale(merged)
    if USE_POSTGRES: db_execute("UPDATE pending_orders SET status='paid',updated_at=NOW() WHERE id=%s",(order_id,))
    else: db_execute("UPDATE pending_orders SET status='paid',updated_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),order_id))
    return result

@app.get("/api/sales/{sale_id}")
def sale_detail(sale_id:int):
    if USE_POSTGRES: sales=db_execute("SELECT id,customer,attendant,total,payment,change,payment_method,created_at FROM sales WHERE id=%s",(sale_id,),True); items=db_execute("SELECT product_name,unit_price,quantity,subtotal FROM sale_items WHERE sale_id=%s ORDER BY id",(sale_id,),True)
    else: sales=db_execute("SELECT id,customer,attendant,total,payment,change,payment_method,created_at FROM sales WHERE id=?",(sale_id,),True); items=db_execute("SELECT product_name,unit_price,quantity,subtotal FROM sale_items WHERE sale_id=? ORDER BY id",(sale_id,),True)
    if not sales: raise HTTPException(404,"Venta no encontrada.")
    s=sales[0]; return {"id":s[0],"customer":s[1],"attendant":s[2],"total":s[3],"payment":s[4],"change":s[5],"payment_method":s[6],"created_at":str(s[7]),"items":[{"name":r[0],"unit_price":r[1],"quantity":r[2],"subtotal":r[3]} for r in items]}

@app.delete("/api/sales/{sale_id}")
def delete_sale(sale_id:int,password:Optional[str]=None):
    require_admin(password or "")
    if USE_POSTGRES: db_execute("DELETE FROM sales WHERE id=%s",(sale_id,))
    else: db_execute("DELETE FROM sales WHERE id=?",(sale_id,))
    return {"ok":True}

@app.get("/api/admin/summary")
def admin_summary(password:str):
    require_admin(password); reg=current_register()
    if not reg: return {"register":None,"sales_count":0,"total":0,"cash_total":0,"nequi_total":0,"dates":[]}
    if USE_POSTGRES: rows=db_execute("SELECT COALESCE(SUM(total),0),COUNT(*),COALESCE(SUM(CASE WHEN payment_method='Efectivo' THEN total ELSE 0 END),0),COALESCE(SUM(CASE WHEN payment_method='Nequi' THEN total ELSE 0 END),0) FROM sales WHERE register_id=%s",(reg['id'],),True)
    else: rows=db_execute("SELECT COALESCE(SUM(total),0),COUNT(*),COALESCE(SUM(CASE WHEN payment_method='Efectivo' THEN total ELSE 0 END),0),COALESCE(SUM(CASE WHEN payment_method='Nequi' THEN total ELSE 0 END),0) FROM sales WHERE register_id=?",(reg['id'],),True)
    return {"register":reg,"sales_count":rows[0][1],"total":rows[0][0],"cash_total":rows[0][2],"nequi_total":rows[0][3]}

@app.get("/api/admin/history")
def admin_history(password:str,start:Optional[str]=None,end:Optional[str]=None):
    require_admin(password); start=start or '2000-01-01'; end=end or date.today().isoformat()
    if USE_POSTGRES:
        rows=db_execute("SELECT id,customer,attendant,total,payment,change,payment_method,created_at,archived FROM sales WHERE created_at::date BETWEEN %s AND %s ORDER BY created_at DESC",(start,end),True)
    else:
        rows=db_execute("SELECT id,customer,attendant,total,payment,change,payment_method,created_at,archived FROM sales WHERE substr(created_at,1,10) BETWEEN ? AND ? ORDER BY created_at DESC",(start,end),True)
    return [{"id":r[0],"customer":r[1],"attendant":r[2],"total":r[3],"payment":r[4],"change":r[5],"payment_method":r[6],"created_at":str(r[7]),"archived":bool(r[8])} for r in rows]
