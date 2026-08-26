# CajaPOS 2.0

Sistema de caja para ventas, pedidos pendientes y cierre diario.

## Funciones
- Vendedor/atendió y cliente.
- Pago en Efectivo o Nequi.
- Cálculo de vueltos para efectivo.
- Pedidos pendientes: se guardan sin cobrar, se pueden abrir después, agregar productos y cobrar todo junto.
- Caja diaria: abrir/cerrar con contraseña de administrador.
- Los vendedores no ven totales ni cantidad de ventas.
- Administrador puede ver resumen, efectivo, Nequi e historial por fechas.
- Las ventas cerradas quedan archivadas y se pueden consultar meses después.
- Administrador puede borrar ventas.
- Productos protegidos por administración.

## Contraseña local
Por defecto: `1234`.

Para producción configura `ADMIN_PASSWORD` como variable de entorno y usa PostgreSQL mediante `DATABASE_URL`.

## Ejecutar local
```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Abrir: http://127.0.0.1:8000

## Varios dispositivos en la misma Wi-Fi
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Luego usa la IP local del PC, por ejemplo `http://192.168.1.25:8000`.

## Producción
Usar Render Web Service + PostgreSQL y configurar `DATABASE_URL` e `ADMIN_PASSWORD`.
